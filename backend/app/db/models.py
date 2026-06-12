from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ClaimRecord(Base):
    """One processed claim: summary columns for listing/filtering, full
    outcome (decision + trace) as JSON for the review UI."""

    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String, primary_key=True)
    member_id: Mapped[str] = mapped_column(String, index=True)
    claim_category: Mapped[str] = mapped_column(String)
    treatment_date: Mapped[object] = mapped_column(Date)
    claimed_amount: Mapped[float] = mapped_column(Float)
    outcome_type: Mapped[str] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_amount: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_json: Mapped[dict] = mapped_column(JSON)
    submission_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
