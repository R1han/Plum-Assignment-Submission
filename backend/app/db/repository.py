"""Claim persistence + history lookups.

Input:  ClaimSubmission / ClaimOutcome pairs.
Output: stored ClaimRecord rows; HistoricalClaim lists for fraud checks.
Errors: sqlalchemy exceptions propagate to the API layer (500).
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ClaimRecord
from app.models.claim import ClaimSubmission, HistoricalClaim
from app.models.decision import ClaimOutcome


def save_outcome(db: Session, claim: ClaimSubmission, outcome: ClaimOutcome) -> ClaimRecord:
    record = ClaimRecord(
        claim_id=outcome.claim_id,
        member_id=claim.member_id,
        claim_category=claim.claim_category.value,
        treatment_date=claim.treatment_date,
        claimed_amount=claim.claimed_amount,
        outcome_type=outcome.outcome_type.value,
        status=outcome.decision.status.value if outcome.decision else None,
        approved_amount=outcome.decision.approved_amount if outcome.decision else 0.0,
        confidence_score=outcome.decision.confidence_score if outcome.decision else None,
        degraded=outcome.degraded,
        outcome_json=json.loads(outcome.model_dump_json()),
        submission_json=json.loads(
            claim.model_dump_json(exclude={"documents": {"__all__": {"file_data"}}})
        ),
    )
    db.add(record)
    db.commit()
    return record


def get_claim(db: Session, claim_id: str) -> ClaimRecord | None:
    return db.get(ClaimRecord, claim_id)


def list_claims(db: Session, limit: int = 100) -> list[ClaimRecord]:
    stmt = select(ClaimRecord).order_by(ClaimRecord.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def member_history(db: Session, member_id: str) -> list[HistoricalClaim]:
    """Prior decided claims for a member, as fraud-check history."""
    stmt = (
        select(ClaimRecord)
        .where(ClaimRecord.member_id == member_id)
        .where(ClaimRecord.outcome_type == "DECISION")
    )
    return [
        HistoricalClaim(
            claim_id=r.claim_id,
            date=r.treatment_date if isinstance(r.treatment_date, date)
            else date.fromisoformat(str(r.treatment_date)),
            amount=r.claimed_amount,
        )
        for r in db.scalars(stmt)
    ]


def merge_history(
    provided: list[HistoricalClaim], stored: list[HistoricalClaim]
) -> list[HistoricalClaim]:
    seen = {h.claim_id for h in provided}
    return provided + [h for h in stored if h.claim_id not in seen]
