"""Input-side domain models: what a claim submission looks like."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    PHARMACY_BILL = "PHARMACY_BILL"
    LAB_REPORT = "LAB_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"
    UNKNOWN = "UNKNOWN"


class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    UNREADABLE = "UNREADABLE"


class LineItem(BaseModel):
    description: str
    amount: float = 0.0


class DocumentContent(BaseModel):
    """Structured content of a document — either extracted by the vision
    model or supplied directly by a test fixture."""

    patient_name: str | None = None
    doctor_name: str | None = None
    doctor_registration: str | None = None
    hospital_name: str | None = None
    date: str | None = None
    diagnosis: str | None = None
    treatment: str | None = None
    medicines: list[str] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)
    test_name: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    total: float | None = None

    model_config = ConfigDict(extra="allow")


class DocumentInput(BaseModel):
    """A single uploaded document.

    Exactly one of two shapes is expected:
    - fixture shape: ``actual_type`` (+ optional ``content``/``quality``) —
      used by the eval harness;
    - upload shape: ``file_data`` (base64) + ``media_type`` — real uploads,
      routed through the vision extractor.
    """

    file_id: str
    file_name: str | None = None
    actual_type: DocumentType | None = None
    quality: DocumentQuality | None = None
    patient_name_on_doc: str | None = None
    content: DocumentContent | None = None
    file_data: str | None = Field(default=None, repr=False)
    media_type: str | None = None


class HistoricalClaim(BaseModel):
    claim_id: str
    date: date
    amount: float
    provider: str | None = None


class ClaimSubmission(BaseModel):
    """The claim intake contract — everything the pipeline needs to run.

    Raises (at the API boundary): pydantic.ValidationError for malformed input.
    """

    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: float = Field(gt=0)
    hospital_name: str | None = None
    pre_auth_reference: str | None = None
    submission_date: date | None = None
    ytd_claims_amount: float = 0.0
    claims_history: list[HistoricalClaim] = Field(default_factory=list)
    documents: list[DocumentInput] = Field(min_length=1)
    simulate_component_failure: bool = False

    @property
    def effective_submission_date(self) -> date:
        return self.submission_date or self.treatment_date
