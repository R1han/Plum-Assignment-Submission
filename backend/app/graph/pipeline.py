"""The claims-processing pipeline as a LangGraph state machine.

    intake -> extract -> verify --(issues)--> finalize (DOCUMENT_ISSUE)
                            \\--(clean)---> adjudicate -> fraud -> finalize

Every node runs inside a resilience wrapper: an unhandled exception is
recorded as a ComponentFailure + ERROR trace step, and the pipeline CONTINUES
with whatever state it has. Failure semantics per node:

  extract      non-critical  proceed with the documents that did extract
  verify       non-critical  proceed unverified (flagged, confidence drops)
  adjudicate   critical      decision becomes MANUAL_REVIEW, never a crash
  fraud        non-critical  skip fraud screen (flagged, confidence drops)

``simulate_component_failure`` on a claim raises inside the fraud node — the
designated non-critical failure point for TC011 — proving the degradation
path end to end.
"""

from __future__ import annotations

import uuid
from functools import wraps

from langgraph.graph import END, START, StateGraph

from app.agents.classifiers import LLMClassifier
from app.agents.document_verification import DocumentVerificationAgent
from app.agents.extraction import ExtractionError, ExtractionService
from app.engine.confidence import compute_confidence
from app.engine.fraud import FraudAgent
from app.engine.rules import AdjudicationResult, RulesEngine
from app.models.claim import ClaimSubmission
from app.models.decision import (
    ClaimOutcome,
    ComponentFailure,
    Decision,
    DecisionStatus,
    OutcomeType,
    TraceStatus,
    TraceStep,
)
from app.models.extraction import consolidate_facts
from app.models.policy import Policy
from app.graph.state import PipelineState


def _step(component, check, status, detail, data=None) -> TraceStep:
    return TraceStep(component=component, check=check, status=status,
                     detail=detail, data=data or {})


def resilient(component: str, impact: str):
    """Convert node crashes into recorded ComponentFailures + a safe update."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(self, state):
            try:
                return fn(self, state)
            except Exception as e:  # noqa: BLE001 — the whole point
                return {
                    "component_failures": [ComponentFailure(
                        component=component, error=str(e), impact=impact,
                    )],
                    "trace": [_step(
                        component, "component_health", TraceStatus.ERROR,
                        f"{component} failed and was skipped: {e}. Impact: {impact}",
                    )],
                }
        return wrapper
    return decorator


class ClaimsPipeline:
    def __init__(self, policy: Policy, extraction: ExtractionService | None = None,
                 classifier=None):
        self.policy = policy
        self.extraction = extraction or ExtractionService()
        self.verifier = DocumentVerificationAgent(policy)
        self.rules = RulesEngine(policy, classifier or LLMClassifier())
        self.fraud = FraudAgent(policy)
        self.graph = self._build()

    # -- nodes -----------------------------------------------------------
    def intake(self, state):
        claim = state.claim
        return {"trace": [_step(
            "intake", "claim_received", TraceStatus.INFO,
            f"Claim {state.claim_id} received: member {claim.member_id}, "
            f"category {claim.claim_category.value}, amount "
            f"₹{claim.claimed_amount:g}, {len(claim.documents)} document(s), "
            f"treatment date {claim.treatment_date}.",
            {"member_id": claim.member_id,
             "category": claim.claim_category.value,
             "claimed_amount": claim.claimed_amount},
        )]}

    @resilient("extraction", "documents could not be machine-read; manual review needed")
    def extract(self, state):
        docs, trace, failures = [], [], []
        for doc_input in state.claim.documents:
            try:
                extracted = self.extraction.extract(doc_input)
                docs.append(extracted)
                trace.append(_step(
                    "extraction", f"extract_{doc_input.file_id}", TraceStatus.PASS,
                    f"{doc_input.file_id}: {extracted.doc_type.value} "
                    f"({extracted.quality.value}, source={extracted.source}, "
                    f"confidence={extracted.extraction_confidence:g})"
                    + (f"; warnings: {'; '.join(extracted.warnings)}"
                       if extracted.warnings else ""),
                    {"doc_type": extracted.doc_type.value,
                     "quality": extracted.quality.value,
                     "confidence": extracted.extraction_confidence},
                ))
            except ExtractionError as e:
                failures.append(ComponentFailure(
                    component="extraction",
                    error=str(e),
                    impact=f"document {doc_input.file_id} unusable",
                ))
                trace.append(_step(
                    "extraction", f"extract_{doc_input.file_id}",
                    TraceStatus.ERROR, str(e),
                ))
        return {"docs": docs, "trace": trace, "component_failures": failures}

    @resilient("document_verification", "documents accepted unverified")
    def verify(self, state):
        trace: list[TraceStep] = []
        result = self.verifier.verify(state.claim, state.docs, trace)
        return {"verification": result, "trace": trace}

    @resilient("adjudication", "no automated decision possible")
    def adjudicate(self, state):
        trace: list[TraceStep] = []
        facts = consolidate_facts(state.docs)
        result = self.rules.adjudicate(state.claim, facts, trace)
        return {"facts": facts, "adjudication": result, "trace": trace}

    @resilient("fraud_detection", "fraud screening skipped for this claim")
    def fraud_check(self, state):
        if state.claim.simulate_component_failure:
            raise RuntimeError(
                "Simulated component failure (fraud detection) — injected by "
                "the simulate_component_failure flag."
            )
        trace: list[TraceStep] = []
        warnings = [w for d in state.docs for w in d.warnings]
        result = self.fraud.assess(state.claim, warnings, trace)
        return {"fraud": result, "trace": trace}

    def finalize(self, state):
        claim_id = state.claim_id
        failures = state.component_failures
        degraded = bool(failures)

        # Early exit: document issues stop the claim before any decision.
        if state.verification is not None and not state.verification.ok:
            outcome = ClaimOutcome(
                claim_id=claim_id,
                outcome_type=OutcomeType.DOCUMENT_ISSUE,
                document_issues=state.verification.issues,
                degraded=degraded,
                component_failures=failures,
            )
            trace_step = _step(
                "finalize", "outcome", TraceStatus.INFO,
                f"Stopped before adjudication: {len(state.verification.issues)} "
                "document issue(s) returned to the member. No decision made.",
                {"issues": [i.code.value for i in state.verification.issues]},
            )
            return {"outcome": outcome, "trace": [trace_step]}

        adjudication = state.adjudication
        if adjudication is None:
            # Adjudication itself failed — the one critical component.
            adjudication = AdjudicationResult(
                status=DecisionStatus.MANUAL_REVIEW,
                reasons=["Automated adjudication was unavailable; a human "
                         "reviewer must decide this claim."],
                member_message="We could not process your claim automatically. "
                               "It has been sent to our claims team for manual "
                               "review.",
            )

        warnings = [w for d in state.docs for w in d.warnings]
        report = compute_confidence(
            extraction_confidence=(state.facts.extraction_confidence
                                   if state.facts else 0.5),
            classifier_certainty=adjudication.classifier_certainty,
            component_failures=len(failures),
            warning_count=len(warnings),
        )

        status = adjudication.status
        reasons = list(adjudication.reasons)
        fraud_signals: list[str] = []
        manual_review_recommended = degraded

        if state.fraud is not None and state.fraud.route_manual_review and \
                status in (DecisionStatus.APPROVED, DecisionStatus.PARTIAL):
            status = DecisionStatus.MANUAL_REVIEW
            fraud_signals = state.fraud.signals
            reasons.append(
                "Routed to manual review due to fraud signals — not auto-"
                "rejected; a human will verify: " + " | ".join(fraud_signals)
            )
        elif state.fraud is not None and state.fraud.signals:
            fraud_signals = state.fraud.signals

        if degraded:
            reasons.append(
                "Processing was degraded ("
                + "; ".join(f.component for f in failures)
                + " failed); confidence reduced and manual review recommended."
            )

        member_message = adjudication.member_message
        if status == DecisionStatus.MANUAL_REVIEW and \
                adjudication.status != DecisionStatus.MANUAL_REVIEW:
            member_message = (
                "Your claim needs a quick manual check by our team before "
                "payout. No action is needed from you right now."
            )

        decision = Decision(
            status=status,
            approved_amount=(adjudication.financial.payable_amount
                             if adjudication.financial and
                             status in (DecisionStatus.APPROVED,
                                        DecisionStatus.PARTIAL)
                             else 0.0),
            reasons=reasons,
            rejection_reasons=adjudication.rejection_reasons,
            line_items=adjudication.line_items,
            financial=adjudication.financial,
            confidence_score=report.score,
            member_message=member_message,
            fraud_signals=fraud_signals,
            manual_review_recommended=manual_review_recommended,
        )
        outcome = ClaimOutcome(
            claim_id=claim_id,
            outcome_type=OutcomeType.DECISION,
            decision=decision,
            degraded=degraded,
            component_failures=failures,
        )
        trace_step = _step(
            "finalize", "outcome", TraceStatus.INFO,
            f"Decision: {status.value}, approved ₹{decision.approved_amount:g}, "
            f"confidence {report.score:g}"
            + (f" (deductions: {'; '.join(report.deductions)})"
               if report.deductions else " (no deductions)")
            + (". Degraded run — manual review recommended." if degraded else "."),
            {"status": status.value, "confidence": report.score,
             "deductions": report.deductions},
        )
        return {"outcome": outcome, "trace": [trace_step]}

    # -- graph wiring ------------------------------------------------------
    def _route_after_verify(self, state) -> str:
        if state.verification is not None and not state.verification.ok:
            return "finalize"
        return "adjudicate"

    def _build(self):
        g = StateGraph(PipelineState)
        g.add_node("intake", self.intake)
        g.add_node("extract", self.extract)
        g.add_node("verify", self.verify)
        g.add_node("adjudicate", self.adjudicate)
        g.add_node("fraud_check", self.fraud_check)
        g.add_node("finalize", self.finalize)

        g.add_edge(START, "intake")
        g.add_edge("intake", "extract")
        g.add_edge("extract", "verify")
        g.add_conditional_edges("verify", self._route_after_verify,
                                {"finalize": "finalize", "adjudicate": "adjudicate"})
        g.add_edge("adjudicate", "fraud_check")
        g.add_edge("fraud_check", "finalize")
        g.add_edge("finalize", END)
        return g.compile()

    # -- public API ----------------------------------------------------
    def run(self, claim: ClaimSubmission, claim_id: str | None = None) -> ClaimOutcome:
        claim_id = claim_id or f"CLM_{uuid.uuid4().hex[:10].upper()}"
        final_state = self.graph.invoke(
            {"claim_id": claim_id, "claim": claim}
        )
        outcome: ClaimOutcome = final_state["outcome"]
        outcome.trace = final_state["trace"]
        return outcome
