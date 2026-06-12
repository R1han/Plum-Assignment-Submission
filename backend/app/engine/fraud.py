"""Fraud signal detection.

Input:  ClaimSubmission (+ claims history) + extraction warnings + Policy
        fraud thresholds.
Output: FraudAssessment — signals found and whether the claim must be routed
        to MANUAL_REVIEW instead of auto-deciding.
Errors: never raises on claim data.

Fraud never auto-rejects: a flagged claim that would otherwise be approved is
routed to a human (TC009 pins this).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.claim import ClaimSubmission
from app.models.decision import TraceStatus, TraceStep
from app.models.policy import Policy

_ALTERATION_KEYWORDS = ("alteration", "correction", "crossed out", "rewritten", "duplicate stamp")


class FraudAssessment(BaseModel):
    flagged: bool = False
    route_manual_review: bool = False
    signals: list[str] = Field(default_factory=list)


class FraudAgent:
    COMPONENT = "fraud_detection"

    def __init__(self, policy: Policy):
        self.policy = policy

    def assess(
        self,
        claim: ClaimSubmission,
        extraction_warnings: list[str],
        trace: list[TraceStep],
    ) -> FraudAssessment:
        t = self.policy.fraud_thresholds
        signals: list[str] = []
        route = False

        # Same-day claim frequency
        same_day = [h for h in claim.claims_history if h.date == claim.treatment_date]
        if len(same_day) >= t.same_day_claims_limit:
            providers = sorted({h.provider for h in same_day if h.provider})
            signals.append(
                f"{len(same_day) + 1} claims from this member on "
                f"{claim.treatment_date} (limit {t.same_day_claims_limit}); "
                f"prior claims today: "
                + ", ".join(f"{h.claim_id} ₹{h.amount:g}" for h in same_day)
                + (f"; providers: {', '.join(providers)}" if providers else "")
            )
            route = True

        # Monthly claim frequency
        month_claims = [
            h for h in claim.claims_history
            if (h.date.year, h.date.month)
            == (claim.treatment_date.year, claim.treatment_date.month)
        ]
        if len(month_claims) >= t.monthly_claims_limit:
            signals.append(
                f"{len(month_claims) + 1} claims in "
                f"{claim.treatment_date.strftime('%B %Y')} "
                f"(limit {t.monthly_claims_limit})."
            )
            route = True

        # High-value claim
        if claim.claimed_amount > t.auto_manual_review_above:
            signals.append(
                f"Claimed ₹{claim.claimed_amount:g} exceeds the automatic "
                f"manual-review threshold ₹{t.auto_manual_review_above:g}."
            )
            route = True

        # Document alteration markers surfaced by extraction
        altered = [
            w for w in extraction_warnings
            if any(k in w.lower() for k in _ALTERATION_KEYWORDS)
        ]
        if altered:
            signals.append(
                "Document alteration markers found during extraction: "
                + "; ".join(altered)
            )
            route = True

        if signals:
            self._trace(trace, TraceStatus.FAIL,
                        "Fraud signals detected; routing to manual review: "
                        + " | ".join(signals),
                        {"signals": signals})
        else:
            self._trace(trace, TraceStatus.PASS,
                        "No fraud signals: same-day, monthly, high-value, and "
                        "document-alteration checks all clear.")

        return FraudAssessment(
            flagged=bool(signals), route_manual_review=route, signals=signals
        )

    def _trace(self, trace, status, detail, data=None):
        trace.append(TraceStep(
            component=self.COMPONENT, check="fraud_signals", status=status,
            detail=detail, data=data or {},
        ))
