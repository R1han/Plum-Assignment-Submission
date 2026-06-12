"""Eval harness: runs the 12 official test cases through the real pipeline.

The pipeline runs with the deterministic classifier tier only (no LLM calls),
so the eval is reproducible offline. All 12 cases resolve deterministically —
the LLM tier exists for messier real-world text than the fixtures contain.

Input:  data/test_cases.json
Output: list[CaseResult] — outcome + per-expectation check results.
Errors: a pipeline crash on any case is itself a FAILED check (the assignment
        requires no-crash behavior), not a harness error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.engine.rules import Classifier
from app.graph.pipeline import ClaimsPipeline
from app.models.claim import ClaimSubmission
from app.models.decision import ClaimOutcome, OutcomeType
from app.policy.loader import load_policy

DATA = Path(__file__).resolve().parent.parent / "data" / "test_cases.json"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class CaseResult:
    case_id: str
    case_name: str
    outcome: ClaimOutcome | None
    checks: list[Check] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


def _issue_text(outcome: ClaimOutcome) -> str:
    return " ".join(i.message for i in outcome.document_issues).lower()


def _decision_text(outcome: ClaimOutcome) -> str:
    d = outcome.decision
    return (d.member_message + " " + " ".join(d.reasons)).lower() if d else ""


def evaluate_case(case: dict, outcome: ClaimOutcome) -> list[Check]:
    checks: list[Check] = []
    expected = case["expected"]
    d = outcome.decision

    if expected.get("decision") is None and "decision" in expected:
        ok = outcome.outcome_type == OutcomeType.DOCUMENT_ISSUE and d is None
        checks.append(Check(
            "stops before decision", ok,
            f"outcome_type={outcome.outcome_type.value}, decision="
            f"{d.status.value if d else None}"))
    elif "decision" in expected:
        ok = d is not None and d.status.value == expected["decision"]
        checks.append(Check(
            f"decision == {expected['decision']}", ok,
            f"got {d.status.value if d else 'no decision'}"))

    if "approved_amount" in expected and d is not None:
        ok = d.approved_amount == expected["approved_amount"]
        checks.append(Check(
            f"approved_amount == {expected['approved_amount']}", ok,
            f"got {d.approved_amount}"))

    if "rejection_reasons" in expected and d is not None:
        produced = {r.value for r in d.rejection_reasons}
        wanted = set(expected["rejection_reasons"])
        ok = wanted <= produced
        checks.append(Check(
            f"rejection_reasons include {sorted(wanted)}", ok,
            f"got {sorted(produced)}"))

    if "confidence_score" in expected and d is not None:
        spec = expected["confidence_score"]  
        threshold = float(spec.split()[-1])
        ok = d.confidence_score > threshold
        checks.append(Check(
            f"confidence {spec}", ok, f"got {d.confidence_score}"))

    extra = _EXTRA_CHECKS.get(case["case_id"])
    if extra:
        checks.extend(extra(outcome))
    return checks


def _tc001(outcome):
    text = _issue_text(outcome)
    return [
        Check("names uploaded doc type (prescription)",
              "prescription" in text, text[:200]),
        Check("names required doc type (hospital bill)",
              "hospital bill" in text, text[:200]),
    ]


def _tc002(outcome):
    text = _issue_text(outcome)
    issues = outcome.document_issues
    return [
        Check("identifies the unreadable pharmacy bill",
              any(i.code.value == "UNREADABLE_DOCUMENT" and i.file_id == "F004"
                  for i in issues),
              f"issues={[(i.code.value, i.file_id) for i in issues]}"),
        Check("asks for re-upload, not rejection",
              "re-upload" in text and "reject" not in text, text[:200]),
    ]


def _tc003(outcome):
    text = " ".join(i.message for i in outcome.document_issues)
    return [
        Check("surfaces both patient names",
              "Rajesh Kumar" in text and "Arjun Mehta" in text, text[:200]),
    ]


def _tc005(outcome):
    text = _decision_text(outcome)
    return [Check("states the eligibility date (2024-11-30)",
                  "2024-11-30" in text, text[:200])]


def _tc006(outcome):
    d = outcome.decision
    verdicts = {v.description: v for v in d.line_items}
    rc = verdicts.get("Root Canal Treatment")
    tw = verdicts.get("Teeth Whitening")
    return [
        Check("itemizes approved vs rejected lines",
              rc is not None and tw is not None and rc.covered and not tw.covered,
              f"verdicts={[(v.description, v.covered) for v in d.line_items]}"),
        Check("line-level rejection reason present",
              tw is not None and bool(tw.reason), tw.reason if tw else "missing"),
    ]


def _tc007(outcome):
    text = _decision_text(outcome)
    return [
        Check("explains pre-auth was required and missing",
              "pre-authorization" in text, text[:250]),
        Check("tells the member how to resubmit",
              "resubmit" in text, text[:250]),
    ]


def _tc008(outcome):
    text = _decision_text(outcome).replace(",", "")
    return [Check("states limit and claimed amount",
                  "5000" in text and "7500" in text, text[:200])]


def _tc009(outcome):
    d = outcome.decision
    return [
        Check("flags the same-day pattern",
              any("claims" in s and "2024-10-30" in s for s in d.fraud_signals),
              f"signals={d.fraud_signals}"),
        Check("routes to manual review, not auto-reject",
              d.status.value == "MANUAL_REVIEW" and not d.rejection_reasons,
              f"status={d.status.value}"),
        Check("specific signals included in output",
              bool(d.fraud_signals), f"{len(d.fraud_signals)} signal(s)"),
    ]


def _tc010(outcome):
    f = outcome.decision.financial
    return [
        Check("network discount applied before co-pay",
              f.network_discount_amount == 900 and f.amount_after_discount == 3600
              and f.copay_amount == 360,
              f"discount={f.network_discount_amount}, after={f.amount_after_discount}, "
              f"copay={f.copay_amount}"),
        Check("breakdown shown in decision output",
              bool(f.notes), " | ".join(f.notes)),
    ]


def _tc011(outcome):
    d = outcome.decision
    return [
        Check("did not crash / no 500", True, "pipeline completed"),
        Check("failure visible in output",
              outcome.degraded and bool(outcome.component_failures),
              f"failures={[f.component for f in outcome.component_failures]}"),
        Check("confidence below clean-run level (0.95)",
              d.confidence_score < 0.95, f"got {d.confidence_score}"),
        Check("manual review recommended",
              d.manual_review_recommended, str(d.manual_review_recommended)),
    ]


_EXTRA_CHECKS = {
    "TC001": _tc001, "TC002": _tc002, "TC003": _tc003, "TC005": _tc005,
    "TC006": _tc006, "TC007": _tc007, "TC008": _tc008, "TC009": _tc009,
    "TC010": _tc010, "TC011": _tc011,
}


def load_cases() -> list[dict]:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)["test_cases"]


def run_all() -> list[CaseResult]:
    pipeline = ClaimsPipeline(load_policy(), classifier=Classifier())
    results = []
    for case in load_cases():
        try:
            claim = ClaimSubmission.model_validate(case["input"])
            outcome = pipeline.run(claim, claim_id=case["case_id"])
            results.append(CaseResult(
                case_id=case["case_id"], case_name=case["case_name"],
                outcome=outcome, checks=evaluate_case(case, outcome),
            ))
        except Exception as e:  
            results.append(CaseResult(
                case_id=case["case_id"], case_name=case["case_name"],
                outcome=None, error=f"{type(e).__name__}: {e}",
            ))
    return results
