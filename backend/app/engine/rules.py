"""Deterministic adjudication rules engine.

Input:  ClaimSubmission + ClaimFacts + Policy (+ optional Classifier for fuzzy
        text mapping — defaults to pure deterministic matching).
Output: AdjudicationResult with status, reasons, line-item verdicts, financial
        breakdown; every check appends a TraceStep to the supplied trace list.
Errors: never raises on claim data — invalid states become REJECTED /
        MANUAL_REVIEW outcomes with traced reasons.

Check order (first terminal failure wins; later checks are traced SKIPPED):
  1. member eligibility (exists, policy active, treatment after join)
  2. submission rules (minimum amount, deadline)
  3. category coverage
  4. exclusions (diagnosis/treatment level)        -> REJECTED
  5. waiting periods (initial + condition-specific) -> REJECTED
  6. pre-authorization                              -> REJECTED
  7. per-claim limit                                -> REJECTED
  8. line-item screening (procedure lists + exclusions) -> PARTIAL/REJECTED
  9. category sub-limit & annual OPD limit caps
 10. financial computation (network discount FIRST, then co-pay)

Exclusions are checked before waiting periods deliberately: an excluded
condition is permanently out of cover, which dominates a temporary wait.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.engine import matching
from app.engine.financial import compute_payable
from app.models.claim import ClaimSubmission, LineItem
from app.models.decision import (
    DecisionStatus,
    FinancialBreakdown,
    LineItemVerdict,
    RejectionReason,
    TraceStatus,
    TraceStep,
)
from app.models.extraction import ClaimFacts
from app.models.policy import OpdCategory, Policy
from pydantic import BaseModel, Field


class Classifier:
    """Fuzzy-text classification interface. The base implementation is purely
    deterministic; the LLM-backed subclass overrides the *_fallback hooks."""

    def match_exclusion(self, text: str, policy: Policy) -> matching.MatchResult:
        result = matching.match_exclusion(text, policy.exclusions.conditions)
        if not result.matched:
            result = self.exclusion_fallback(text, policy)
        return result

    def match_condition(self, text: str, policy: Policy) -> matching.MatchResult:
        keys = list(policy.waiting_periods.specific_conditions.keys())
        result = matching.match_waiting_condition(text, keys)
        if not result.matched:
            result = self.condition_fallback(text, policy)
        return result

    def match_procedure(
        self, text: str, covered: list[str], excluded: list[str]
    ) -> tuple[str, matching.MatchResult]:
        """Classify a line item as 'covered' / 'excluded' / 'unknown'."""
        ex = matching.match_against_list(text, excluded)
        if ex.matched:
            return "excluded", ex
        cov = matching.match_against_list(text, covered)
        if cov.matched:
            return "covered", cov
        return self.procedure_fallback(text, covered, excluded)

    # Hooks for the LLM tier — deterministic base returns "no match".
    def exclusion_fallback(self, text: str, policy: Policy) -> matching.MatchResult:
        return matching.MatchResult(False)

    def condition_fallback(self, text: str, policy: Policy) -> matching.MatchResult:
        return matching.MatchResult(False)

    def procedure_fallback(
        self, text: str, covered: list[str], excluded: list[str]
    ) -> tuple[str, matching.MatchResult]:
        return "unknown", matching.MatchResult(False)


class AdjudicationResult(BaseModel):
    status: DecisionStatus
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    line_items: list[LineItemVerdict] = Field(default_factory=list)
    financial: FinancialBreakdown | None = None
    member_message: str = ""
    classifier_certainty: str = "exact"  # weakest certainty used on the path


class RulesEngine:
    COMPONENT = "rules_engine"

    def __init__(self, policy: Policy, classifier: Classifier | None = None):
        self.policy = policy
        self.classifier = classifier or Classifier()

    # ------------------------------------------------------------------
    def adjudicate(
        self,
        claim: ClaimSubmission,
        facts: ClaimFacts,
        trace: list[TraceStep],
    ) -> AdjudicationResult:
        category = self.policy.get_category(claim.claim_category.value)
        weakest_certainty = ["exact"]

        checks = [
            self._check_member_eligibility,
            self._check_submission_rules,
            self._check_category_coverage,
            self._check_exclusions,
            self._check_waiting_periods,
            self._check_pre_authorization,
        ]
        for i, check in enumerate(checks):
            result = check(claim, facts, category, trace, weakest_certainty)
            if result is not None:
                self._skip_remaining(checks[i + 1 :], trace,
                                     extra=["per_claim_limit", "line_item_screening"])
                result.classifier_certainty = weakest_certainty[0]
                return result

        # 7. line-item screening
        verdicts = self._screen_line_items(claim, facts, category, trace, weakest_certainty)
        excluded = [v for v in verdicts if not v.covered]
        covered = [v for v in verdicts if v.covered]

        if verdicts and not covered:
            reasons = [f"{v.description}: {v.reason}" for v in excluded]
            self._trace(trace, "line_item_screening", TraceStatus.FAIL,
                        "All billed items are excluded from cover.",
                        {"items": [v.model_dump() for v in excluded]})
            return AdjudicationResult(
                status=DecisionStatus.REJECTED,
                rejection_reasons=[RejectionReason.EXCLUDED_PROCEDURE],
                reasons=reasons,
                line_items=verdicts,
                member_message="None of the billed items are covered: " + "; ".join(reasons),
                classifier_certainty=weakest_certainty[0],
            )

        covered_amount = (
            sum(v.amount for v in covered) if verdicts else claim.claimed_amount
        )

        # 8. per-claim limit on the covered amount. The effective cap is
        # max(global per-claim limit, category sub-limit): TC006 pays ₹8,000
        # under DENTAL's ₹10,000 sub-limit despite the global ₹5,000 limit,
        # while TC008's ₹7,500 consultation claim must reject against ₹5,000.
        per_claim_result = self._check_per_claim_limit(
            claim, facts, category, trace, weakest_certainty,
            covered_amount=covered_amount,
        )
        if per_claim_result is not None:
            per_claim_result.line_items = verdicts
            per_claim_result.classifier_certainty = weakest_certainty[0]
            return per_claim_result

        # 9. caps (sub-limit on primary service lines, annual OPD limit)
        covered_amount, cap_notes = self._apply_caps(
            claim, facts, category, covered_amount, trace
        )

        # 10. financial computation
        is_network = self.policy.is_network_hospital(
            claim.hospital_name or facts.hospital_name
        )
        self._trace(
            trace, "network_hospital", TraceStatus.INFO,
            f"Hospital '{claim.hospital_name or facts.hospital_name or 'unknown'}' "
            f"{'IS' if is_network else 'is NOT'} in the network list.",
            {"network": is_network},
        )
        financial = compute_payable(
            claim.claimed_amount, covered_amount, category, is_network
        )
        financial.notes = cap_notes + financial.notes
        self._trace(
            trace, "financial_computation", TraceStatus.PASS,
            " ".join(financial.notes),
            financial.model_dump(),
        )

        partial = bool(excluded) or covered_amount < min(
            claim.claimed_amount, sum(v.amount for v in verdicts) if verdicts else claim.claimed_amount
        )
        status = DecisionStatus.PARTIAL if partial else DecisionStatus.APPROVED
        reasons = []
        if excluded:
            reasons.extend(f"Not payable — {v.description}: {v.reason}" for v in excluded)
        if covered:
            reasons.append(
                f"Payable items: {', '.join(v.description for v in covered)}."
            )
        reasons.extend(financial.notes)

        message = (
            f"Your claim is {'partially ' if partial else ''}approved for "
            f"₹{financial.payable_amount:g}."
        )
        if excluded:
            message += " Items not covered: " + "; ".join(
                f"{v.description} (₹{v.amount:g}) — {v.reason}" for v in excluded
            )

        return AdjudicationResult(
            status=status,
            reasons=reasons,
            line_items=verdicts,
            financial=financial,
            member_message=message,
            classifier_certainty=weakest_certainty[0],
        )

    # ------------------------------------------------------------------
    # Individual checks. Each returns AdjudicationResult on terminal failure,
    # None to continue.

    def _check_member_eligibility(self, claim, facts, category, trace, certainty):
        member = self.policy.get_member(claim.member_id)
        if member is None:
            self._trace(trace, "member_exists", TraceStatus.FAIL,
                        f"Member {claim.member_id} not found on policy roster.")
            return self._reject(
                RejectionReason.MEMBER_NOT_FOUND,
                f"Member {claim.member_id} is not on the policy {self.policy.policy_id} roster.",
            )
        self._trace(trace, "member_exists", TraceStatus.PASS,
                    f"Member {claim.member_id} ({member.name}) found on roster.")

        holder = self.policy.policy_holder
        if not (holder.policy_start_date <= claim.treatment_date <= holder.policy_end_date) \
                or holder.renewal_status != "ACTIVE":
            self._trace(trace, "policy_active", TraceStatus.FAIL,
                        f"Treatment date {claim.treatment_date} outside active policy "
                        f"period {holder.policy_start_date}..{holder.policy_end_date}.")
            return self._reject(
                RejectionReason.POLICY_INACTIVE,
                f"The policy is not active on the treatment date {claim.treatment_date}.",
            )
        self._trace(trace, "policy_active", TraceStatus.PASS,
                    f"Treatment date {claim.treatment_date} within policy period.")

        join_date = self.policy.member_join_date(claim.member_id)
        if join_date and claim.treatment_date < join_date:
            self._trace(trace, "treatment_after_join", TraceStatus.FAIL,
                        f"Treatment {claim.treatment_date} precedes join date {join_date}.")
            return self._reject(
                RejectionReason.POLICY_INACTIVE,
                f"Treatment on {claim.treatment_date} predates cover start ({join_date}).",
            )
        return None

    def _check_submission_rules(self, claim, facts, category, trace, certainty):
        rules = self.policy.submission_rules
        if claim.claimed_amount < rules.minimum_claim_amount:
            self._trace(trace, "minimum_claim_amount", TraceStatus.FAIL,
                        f"Claimed ₹{claim.claimed_amount:g} is below the minimum "
                        f"claim amount ₹{rules.minimum_claim_amount:g}.")
            return self._reject(
                RejectionReason.BELOW_MINIMUM_AMOUNT,
                f"Claims below ₹{rules.minimum_claim_amount:g} are not accepted "
                f"(you claimed ₹{claim.claimed_amount:g}).",
            )
        self._trace(trace, "minimum_claim_amount", TraceStatus.PASS,
                    f"Claimed ₹{claim.claimed_amount:g} ≥ minimum ₹{rules.minimum_claim_amount:g}.")

        days = (claim.effective_submission_date - claim.treatment_date).days
        if days > rules.deadline_days_from_treatment:
            self._trace(trace, "submission_deadline", TraceStatus.FAIL,
                        f"Submitted {days} days after treatment; deadline is "
                        f"{rules.deadline_days_from_treatment} days.")
            return self._reject(
                RejectionReason.SUBMISSION_DEADLINE,
                f"Claims must be submitted within {rules.deadline_days_from_treatment} "
                f"days of treatment; this one came {days} days after.",
            )
        self._trace(trace, "submission_deadline", TraceStatus.PASS,
                    f"Submitted {days} days after treatment (limit "
                    f"{rules.deadline_days_from_treatment}).")
        return None

    def _check_category_coverage(self, claim, facts, category: OpdCategory | None, trace, certainty):
        if category is None or not category.covered:
            self._trace(trace, "category_covered", TraceStatus.FAIL,
                        f"Category {claim.claim_category.value} is not covered.")
            return self._reject(
                RejectionReason.NOT_COVERED,
                f"{claim.claim_category.value} treatments are not covered by this policy.",
            )
        self._trace(trace, "category_covered", TraceStatus.PASS,
                    f"Category {claim.claim_category.value} is covered "
                    f"(sub-limit ₹{category.sub_limit:g}, co-pay {category.copay_percent:g}%).")

        if category.requires_registered_practitioner and not facts.doctor_registration:
            self._trace(trace, "registered_practitioner", TraceStatus.FAIL,
                        "Policy requires a registered practitioner; no registration "
                        "number found on the prescription.")
            return self._reject(
                RejectionReason.NOT_COVERED,
                "This category requires treatment by a registered practitioner; "
                "no practitioner registration number was found on your documents.",
            )
        if category.requires_registered_practitioner:
            self._trace(trace, "registered_practitioner", TraceStatus.PASS,
                        f"Practitioner registration {facts.doctor_registration} present.")
        return None

    def _check_exclusions(self, claim, facts, category, trace, certainty):
        # Claim-level exclusion looks at diagnosis/treatment only. Line items
        # are screened individually later so a single excluded item produces a
        # PARTIAL decision (TC006) rather than rejecting the whole claim.
        texts = [t for t in [facts.diagnosis, facts.treatment] if t]
        for text in texts:
            result = self.classifier.match_exclusion(text, self.policy)
            if result.matched:
                self._bump_certainty(certainty, result.certainty)
                self._trace(trace, "exclusions", TraceStatus.FAIL,
                            f"'{text}' matches policy exclusion '{result.rule}'.",
                            {"matched_text": text, "exclusion": result.rule,
                             "certainty": result.certainty})
                return self._reject(
                    RejectionReason.EXCLUDED_CONDITION,
                    f"'{text}' falls under the policy exclusion '{result.rule}' "
                    "and is not covered.",
                )
        self._trace(trace, "exclusions", TraceStatus.PASS,
                    "No policy exclusion matched the diagnosis, treatment, or billed items.",
                    {"texts_checked": texts})
        return None

    def _check_waiting_periods(self, claim, facts, category, trace, certainty):
        wp = self.policy.waiting_periods
        join_date = self.policy.member_join_date(claim.member_id)
        if join_date is None:
            self._trace(trace, "waiting_periods", TraceStatus.ERROR,
                        "No join date available; cannot evaluate waiting periods.")
            return None

        days_covered = (claim.treatment_date - join_date).days
        if days_covered < wp.initial_waiting_period_days:
            eligible_from = join_date + timedelta(days=wp.initial_waiting_period_days)
            self._trace(trace, "initial_waiting_period", TraceStatus.FAIL,
                        f"Only {days_covered} days since cover start {join_date}; "
                        f"initial waiting period is {wp.initial_waiting_period_days} days.")
            return self._reject(
                RejectionReason.WAITING_PERIOD,
                f"Your cover started on {join_date} and has an initial "
                f"{wp.initial_waiting_period_days}-day waiting period. You are "
                f"eligible to claim from {eligible_from}.",
            )
        self._trace(trace, "initial_waiting_period", TraceStatus.PASS,
                    f"{days_covered} days since cover start ≥ "
                    f"{wp.initial_waiting_period_days}-day initial wait.")

        diagnosis_text = " ; ".join(
            t for t in [facts.diagnosis, facts.treatment] if t
        )
        result = self.classifier.match_condition(diagnosis_text, self.policy)
        if result.matched:
            self._bump_certainty(certainty, result.certainty)
            wait_days = wp.specific_conditions[result.rule]
            if days_covered < wait_days:
                eligible_from = join_date + timedelta(days=wait_days)
                self._trace(trace, "condition_waiting_period", TraceStatus.FAIL,
                            f"Diagnosis '{facts.diagnosis}' maps to condition "
                            f"'{result.rule}' ({wait_days}-day wait); member covered "
                            f"only {days_covered} days (joined {join_date}).",
                            {"condition": result.rule, "wait_days": wait_days,
                             "days_covered": days_covered,
                             "eligible_from": str(eligible_from)})
                return self._reject(
                    RejectionReason.WAITING_PERIOD,
                    f"Claims for {result.rule.replace('_', ' ')} have a "
                    f"{wait_days}-day waiting period. Your cover started on "
                    f"{join_date}, so you will be eligible for "
                    f"{result.rule.replace('_', ' ')}-related claims from "
                    f"{eligible_from}.",
                )
            self._trace(trace, "condition_waiting_period", TraceStatus.PASS,
                        f"Condition '{result.rule}' wait ({wait_days} days) satisfied "
                        f"({days_covered} days covered).")
        else:
            self._trace(trace, "condition_waiting_period", TraceStatus.PASS,
                        "Diagnosis does not map to any condition-specific waiting period.")
        return None

    def _check_pre_authorization(self, claim, facts, category, trace, certainty):
        if claim.pre_auth_reference:
            self._trace(trace, "pre_authorization", TraceStatus.PASS,
                        f"Pre-authorization reference {claim.pre_auth_reference} supplied.")
            return None

        high_value_tests = category.high_value_tests_requiring_pre_auth
        threshold = category.pre_auth_threshold
        if not high_value_tests or threshold is None:
            self._trace(trace, "pre_authorization", TraceStatus.PASS,
                        "No pre-authorization requirement applies to this category.")
            return None

        texts = list(facts.tests) + [li.description for li in facts.line_items]
        for text in texts:
            hit = matching.contains_any(text, high_value_tests)
            if hit and claim.claimed_amount > threshold:
                self._trace(trace, "pre_authorization", TraceStatus.FAIL,
                            f"'{text}' is a high-value test ({hit}) at "
                            f"₹{claim.claimed_amount:g} > ₹{threshold:g} threshold, "
                            "and no pre-authorization was obtained.",
                            {"test": text, "threshold": threshold,
                             "claimed": claim.claimed_amount})
                return self._reject(
                    RejectionReason.PRE_AUTH_MISSING,
                    f"A {hit} above ₹{threshold:g} requires pre-authorization, which "
                    "was not obtained. To resubmit: request pre-authorization from "
                    "your insurer (valid "
                    f"{self.policy.pre_authorization.validity_days} days), then "
                    "submit this claim again quoting the pre-authorization number.",
                )
        self._trace(trace, "pre_authorization", TraceStatus.PASS,
                    "No high-value test requiring pre-authorization found, or amount "
                    "below threshold.")
        return None

    def _check_per_claim_limit(self, claim, facts, category, trace, certainty,
                               covered_amount: float | None = None):
        amount = covered_amount if covered_amount is not None else claim.claimed_amount
        limit = max(self.policy.coverage.per_claim_limit, category.sub_limit)
        if amount > limit:
            self._trace(trace, "per_claim_limit", TraceStatus.FAIL,
                        f"Payable amount ₹{amount:g} exceeds the per-claim limit "
                        f"₹{limit:g} (global ₹{self.policy.coverage.per_claim_limit:g}, "
                        f"category sub-limit ₹{category.sub_limit:g}).",
                        {"amount": amount, "limit": limit,
                         "claimed": claim.claimed_amount})
            return self._reject(
                RejectionReason.PER_CLAIM_EXCEEDED,
                f"The claimed amount ₹{claim.claimed_amount:g} exceeds the per-claim "
                f"limit of ₹{limit:g} under your policy.",
            )
        self._trace(trace, "per_claim_limit", TraceStatus.PASS,
                    f"Payable ₹{amount:g} ≤ per-claim limit ₹{limit:g}.")
        return None

    # ------------------------------------------------------------------
    def _screen_line_items(self, claim, facts, category: OpdCategory, trace, certainty) -> list[LineItemVerdict]:
        if not facts.line_items:
            self._trace(trace, "line_item_screening", TraceStatus.INFO,
                        "No itemized bill lines; claim adjudicated at claim level.")
            return []

        covered_list = category.covered_procedures + category.covered_items
        excluded_list = (
            category.excluded_procedures
            + category.excluded_items
            + self.policy.exclusions.dental_exclusions
            + self.policy.exclusions.vision_exclusions
        )
        verdicts: list[LineItemVerdict] = []
        for item in facts.line_items:
            verdict = self._screen_item(item, covered_list, excluded_list, certainty)
            verdicts.append(verdict)
            self._trace(
                trace, "line_item_screening",
                TraceStatus.PASS if verdict.covered else TraceStatus.FAIL,
                f"{item.description} (₹{item.amount:g}): "
                f"{'covered' if verdict.covered else 'NOT covered'} — {verdict.reason}",
                verdict.model_dump(),
            )
        return verdicts

    def _screen_item(self, item: LineItem, covered_list, excluded_list, certainty) -> LineItemVerdict:
        # Global exclusions apply to every category.
        ex = self.classifier.match_exclusion(item.description, self.policy)
        if ex.matched:
            self._bump_certainty(certainty, ex.certainty)
            return LineItemVerdict(
                description=item.description, amount=item.amount, covered=False,
                reason=f"matches policy exclusion '{ex.rule}'", matched_rule=ex.rule,
            )
        if covered_list or excluded_list:
            kind, m = self.classifier.match_procedure(
                item.description, covered_list, excluded_list
            )
            self._bump_certainty(certainty, m.certainty if m.matched else "keyword")
            if kind == "excluded":
                return LineItemVerdict(
                    description=item.description, amount=item.amount, covered=False,
                    reason=f"listed as excluded: '{m.rule}'", matched_rule=m.rule,
                )
            if kind == "covered":
                return LineItemVerdict(
                    description=item.description, amount=item.amount, covered=True,
                    reason=f"listed as covered: '{m.rule}'", matched_rule=m.rule,
                )
            # Unknown procedure in a list-governed category: default to covered
            # but flag — conservative payout decisions belong to ops, not code.
            return LineItemVerdict(
                description=item.description, amount=item.amount, covered=True,
                reason="not on any list; covered by default (flagged)",
            )
        return LineItemVerdict(
            description=item.description, amount=item.amount, covered=True,
            reason="no procedure restrictions for this category",
        )

    def _apply_caps(self, claim, facts, category: OpdCategory, covered_amount: float, trace):
        notes: list[str] = []
        # Category sub-limit: applied to the category's primary-service lines
        # (e.g. consultation fees), not the whole claim — TC010 approves ₹3,240
        # on a ₹4,500 consultation claim against a ₹2,000 sub-limit, which pins
        # this interpretation. Documented assumption in ARCHITECTURE.md.
        primary_keyword = claim.claim_category.value.replace("_", " ").lower().split()[0]
        primary_total = sum(
            li.amount for li in facts.line_items
            if primary_keyword in li.description.lower()
        )
        if primary_total > category.sub_limit:
            over = primary_total - category.sub_limit
            covered_amount = max(covered_amount - over, 0.0)
            notes.append(
                f"{claim.claim_category.value.title()} service charges "
                f"₹{primary_total:g} exceed the category sub-limit "
                f"₹{category.sub_limit:g}; ₹{over:g} not payable."
            )
            self._trace(trace, "category_sub_limit", TraceStatus.FAIL,
                        notes[-1], {"primary_total": primary_total,
                                    "sub_limit": category.sub_limit})
        else:
            self._trace(trace, "category_sub_limit", TraceStatus.PASS,
                        f"Primary service charges within category sub-limit "
                        f"₹{category.sub_limit:g}.")

        annual_limit = self.policy.coverage.annual_opd_limit
        remaining = annual_limit - claim.ytd_claims_amount
        if covered_amount > remaining:
            capped = max(remaining, 0.0)
            notes.append(
                f"Annual OPD limit ₹{annual_limit:g}: ₹{claim.ytd_claims_amount:g} "
                f"already used; payable capped at ₹{capped:g}."
            )
            self._trace(trace, "annual_opd_limit", TraceStatus.FAIL, notes[-1],
                        {"ytd": claim.ytd_claims_amount, "annual_limit": annual_limit})
            covered_amount = capped
        else:
            self._trace(trace, "annual_opd_limit", TraceStatus.PASS,
                        f"YTD ₹{claim.ytd_claims_amount:g} + this claim within the "
                        f"annual OPD limit ₹{annual_limit:g}.")
        return covered_amount, notes

    # ------------------------------------------------------------------
    def _reject(self, reason: RejectionReason, message: str) -> AdjudicationResult:
        return AdjudicationResult(
            status=DecisionStatus.REJECTED,
            rejection_reasons=[reason],
            reasons=[message],
            member_message=message,
        )

    def _skip_remaining(self, remaining_checks, trace, extra: list[str] | None = None):
        names = [c.__name__.removeprefix("_check_") for c in remaining_checks]
        names.extend(extra or [])
        for name in names:
            self._trace(trace, name, TraceStatus.SKIPPED,
                        "Skipped: claim already terminally rejected by an earlier check.")

    def _trace(self, trace: list[TraceStep], check: str, status: TraceStatus,
               detail: str, data: dict | None = None):
        trace.append(TraceStep(
            component=self.COMPONENT, check=check, status=status,
            detail=detail, data=data or {},
        ))

    @staticmethod
    def _bump_certainty(holder: list[str], certainty: str):
        order = {"exact": 0, "keyword": 1, "llm": 2, "none": 3}
        if order.get(certainty, 3) > order.get(holder[0], 0):
            holder[0] = certainty
