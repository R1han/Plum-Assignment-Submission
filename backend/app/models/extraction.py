"""Models produced by the extraction layer and consumed by the rules engine."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.claim import DocumentContent, DocumentQuality, DocumentType, LineItem


class ExtractedDocument(BaseModel):
    """A document after type classification + content extraction.

    ``source`` records which adapter produced it: "fixture" (structured test
    input) or "vision" (Claude vision extraction on an upload).
    """

    file_id: str
    file_name: str | None = None
    doc_type: DocumentType
    quality: DocumentQuality = DocumentQuality.GOOD
    content: DocumentContent = Field(default_factory=DocumentContent)
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "fixture"
    warnings: list[str] = Field(default_factory=list)


class ClaimFacts(BaseModel):
    """Consolidated view across all extracted documents — the single input the
    rules engine adjudicates against."""

    patient_names: list[str] = Field(default_factory=list)
    diagnosis: str | None = None
    treatment: str | None = None
    doctor_name: str | None = None
    doctor_registration: str | None = None
    hospital_name: str | None = None
    medicines: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    bill_total: float | None = None
    extraction_confidence: float = 1.0


def consolidate_facts(docs: list[ExtractedDocument]) -> ClaimFacts:
    """Merge extracted documents into ClaimFacts. Bills win for financial
    fields; prescriptions win for clinical fields."""
    facts = ClaimFacts()
    confidences: list[float] = []
    for doc in docs:
        c = doc.content
        confidences.append(doc.extraction_confidence)
        if c.patient_name and c.patient_name not in facts.patient_names:
            facts.patient_names.append(c.patient_name)
        facts.diagnosis = facts.diagnosis or c.diagnosis
        facts.treatment = facts.treatment or c.treatment
        facts.doctor_name = facts.doctor_name or c.doctor_name
        facts.doctor_registration = facts.doctor_registration or c.doctor_registration
        facts.hospital_name = facts.hospital_name or c.hospital_name
        for med in c.medicines:
            if med not in facts.medicines:
                facts.medicines.append(med)
        for test in c.tests_ordered:
            if test not in facts.tests:
                facts.tests.append(test)
        if c.test_name and c.test_name not in facts.tests:
            facts.tests.append(c.test_name)
        if doc.doc_type.value.endswith("BILL"):
            facts.line_items.extend(c.line_items)
            if c.total is not None:
                facts.bill_total = c.total
    if confidences:
        facts.extraction_confidence = round(min(confidences), 3)
    return facts
