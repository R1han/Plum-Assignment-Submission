"""Output-side domain models: traces, document issues, and decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RejectionReason(str, Enum):
    WAITING_PERIOD = "WAITING_PERIOD"
    PRE_AUTH_MISSING = "PRE_AUTH_MISSING"
    PER_CLAIM_EXCEEDED = "PER_CLAIM_EXCEEDED"
    EXCLUDED_CONDITION = "EXCLUDED_CONDITION"
    EXCLUDED_PROCEDURE = "EXCLUDED_PROCEDURE"
    NOT_COVERED = "NOT_COVERED"
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    POLICY_INACTIVE = "POLICY_INACTIVE"
    BELOW_MINIMUM_AMOUNT = "BELOW_MINIMUM_AMOUNT"
    SUBMISSION_DEADLINE = "SUBMISSION_DEADLINE"
    ANNUAL_LIMIT_EXCEEDED = "ANNUAL_LIMIT_EXCEEDED"


class TraceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    INFO = "INFO"


class TraceStep(BaseModel):
    """One auditable unit of work. The full ordered list of TraceSteps must be
    sufficient to reconstruct why a claim got its decision."""

    component: str
    check: str
    status: TraceStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentIssueCode(str, Enum):
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    WRONG_DOCUMENT_TYPE = "WRONG_DOCUMENT_TYPE"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"
    PATIENT_MISMATCH = "PATIENT_MISMATCH"


class DocumentIssue(BaseModel):
    code: DocumentIssueCode
    message: str  # member-facing, must be specific and actionable
    file_id: str | None = None
    expected: str | None = None
    found: str | None = None


class LineItemVerdict(BaseModel):
    description: str
    amount: float
    covered: bool
    reason: str
    matched_rule: str | None = None


class FinancialBreakdown(BaseModel):
    claimed_amount: float
    covered_amount: float
    network_discount_percent: float = 0.0
    network_discount_amount: float = 0.0
    amount_after_discount: float = 0.0
    copay_percent: float = 0.0
    copay_amount: float = 0.0
    payable_amount: float = 0.0
    currency: str = "INR"
    notes: list[str] = Field(default_factory=list)


class ComponentFailure(BaseModel):
    component: str
    error: str
    impact: str


class Decision(BaseModel):
    status: DecisionStatus
    approved_amount: float = 0.0
    currency: str = "INR"
    reasons: list[str] = Field(default_factory=list)
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    line_items: list[LineItemVerdict] = Field(default_factory=list)
    financial: FinancialBreakdown | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    member_message: str = ""
    fraud_signals: list[str] = Field(default_factory=list)
    manual_review_recommended: bool = False


class OutcomeType(str, Enum):
    DECISION = "DECISION"
    DOCUMENT_ISSUE = "DOCUMENT_ISSUE"


class ClaimOutcome(BaseModel):
    """Top-level pipeline result.

    ``DOCUMENT_ISSUE``: processing stopped before adjudication; ``decision``
    is None and ``document_issues`` tells the member exactly what to fix.
    ``DECISION``: full adjudication ran; ``decision`` is populated.
    """

    claim_id: str
    outcome_type: OutcomeType
    decision: Decision | None = None
    document_issues: list[DocumentIssue] = Field(default_factory=list)
    degraded: bool = False
    component_failures: list[ComponentFailure] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
