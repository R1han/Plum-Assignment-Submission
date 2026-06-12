"""Document extraction layer — one interface, two adapters.

- FixtureAdapter: consumes structured document content supplied directly in
  the submission (the eval harness / test_cases.json path). Deterministic.
- VisionExtractor: sends uploaded images/PDFs to Claude (Sonnet) with a
  structured-output schema and returns the same ExtractedDocument shape.

Input:  DocumentInput (either fixture-shaped or upload-shaped).
Output: ExtractedDocument (type, quality, content, confidence, warnings).
Errors: ExtractionError on unrecoverable extraction failure (missing API key,
        API error after retries, undecodable file). The orchestrator catches
        this per-document and degrades gracefully.
"""

from __future__ import annotations

from anthropic import Anthropic, APIError
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models.claim import (
    DocumentContent,
    DocumentInput,
    DocumentQuality,
    DocumentType,
    LineItem,
)
from app.models.extraction import ExtractedDocument


class ExtractionError(Exception):
    """Raised when a document cannot be extracted at all."""


class _VisionExtractionSchema(BaseModel):
    """Structured output the vision model must return for each document."""

    doc_type: DocumentType = Field(
        description="The document type. UNKNOWN only if truly unidentifiable."
    )
    quality: DocumentQuality = Field(
        description="GOOD if fully readable, PARTIAL if some fields are "
                    "obscured (stamps, folds, blur), UNREADABLE if no reliable "
                    "fields can be extracted."
    )
    patient_name: str | None = None
    doctor_name: str | None = None
    doctor_registration: str | None = Field(
        default=None,
        description="Indian medical registration, e.g. KA/45678/2015 or "
                    "AYUR/KL/2345/2019.",
    )
    hospital_name: str | None = None
    date: str | None = Field(default=None, description="ISO format if possible")
    diagnosis: str | None = None
    treatment: str | None = None
    medicines: list[str] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    total: float | None = None
    confidence: float = Field(
        ge=0, le=1,
        description="Your confidence in the extraction overall.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Anything partially illegible, stamped over, corrected, "
                    "or ambiguous — name the specific field.",
    )


_EXTRACTION_PROMPT = """\
You are extracting structured data from an Indian medical document for an
insurance claim. Documents may be handwritten, photographed at an angle,
stamped over, or use medical shorthand (HTN = Hypertension, T2DM = Type 2
Diabetes Mellitus, Rx = prescription).

Rules:
- Classify the document type and its readability honestly. If you cannot read
  a field, leave it null and add a warning naming the field — do not guess.
- Expand medical shorthand in the diagnosis field.
- For bills, extract every line item with its amount, and the total.
- Amounts are INR. Strip currency symbols and thousands separators.
- Patient and doctor names exactly as printed (keep titles like Dr.).
"""


class FixtureAdapter:
    """Builds ExtractedDocument from fixture-shaped input. Free and exact."""

    SOURCE = "fixture"

    def extract(self, doc: DocumentInput) -> ExtractedDocument:
        if doc.actual_type is None:
            raise ExtractionError(
                f"Document {doc.file_id} has neither fixture metadata nor file data."
            )
        quality = doc.quality or DocumentQuality.GOOD
        content = doc.content or DocumentContent()
        if doc.patient_name_on_doc and not content.patient_name:
            content = content.model_copy(
                update={"patient_name": doc.patient_name_on_doc}
            )
        unreadable = quality == DocumentQuality.UNREADABLE
        return ExtractedDocument(
            file_id=doc.file_id,
            file_name=doc.file_name,
            doc_type=doc.actual_type,
            quality=quality,
            content=DocumentContent() if unreadable else content,
            extraction_confidence=0.0 if unreadable
            else (0.6 if quality == DocumentQuality.PARTIAL else 1.0),
            source=self.SOURCE,
            warnings=["document unreadable; no fields extracted"] if unreadable else [],
        )


class VisionExtractor:
    """Claude-vision extraction for real uploads."""

    SOURCE = "vision"

    def __init__(self, client: Anthropic | None = None, model: str | None = None):
        settings = get_settings()
        if client is None and not settings.anthropic_api_key:
            raise ExtractionError(
                "ANTHROPIC_API_KEY is not configured; cannot extract uploaded "
                "documents. Structured (fixture) submissions still work."
            )
        self.client = client or Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.extraction_model

    def extract(self, doc: DocumentInput) -> ExtractedDocument:
        if not doc.file_data:
            raise ExtractionError(f"Document {doc.file_id} has no file data.")
        media_type = doc.media_type or "image/jpeg"
        if media_type == "application/pdf":
            file_block = {
                "type": "document",
                "source": {"type": "base64", "media_type": media_type,
                           "data": doc.file_data},
            }
        else:
            file_block = {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type,
                           "data": doc.file_data},
            }
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=_EXTRACTION_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        file_block,
                        {"type": "text",
                         "text": "Extract this medical document."},
                    ],
                }],
                output_format=_VisionExtractionSchema,
            )
        except APIError as e:
            raise ExtractionError(
                f"Vision extraction failed for {doc.file_id}: {e}"
            ) from e

        parsed: _VisionExtractionSchema | None = response.parsed_output
        if parsed is None:
            raise ExtractionError(
                f"Vision extraction returned no parsable output for {doc.file_id}."
            )
        content = DocumentContent(
            patient_name=parsed.patient_name,
            doctor_name=parsed.doctor_name,
            doctor_registration=parsed.doctor_registration,
            hospital_name=parsed.hospital_name,
            date=parsed.date,
            diagnosis=parsed.diagnosis,
            treatment=parsed.treatment,
            medicines=parsed.medicines,
            tests_ordered=parsed.tests_ordered,
            line_items=parsed.line_items,
            total=parsed.total,
        )
        return ExtractedDocument(
            file_id=doc.file_id,
            file_name=doc.file_name,
            doc_type=parsed.doc_type,
            quality=parsed.quality,
            content=content,
            extraction_confidence=parsed.confidence,
            source=self.SOURCE,
            warnings=parsed.warnings,
        )


class ExtractionService:
    """Routes each document to the right adapter."""

    COMPONENT = "extraction"

    def __init__(self, vision: VisionExtractor | None = None):
        self.fixture = FixtureAdapter()
        self._vision = vision

    @property
    def vision(self) -> VisionExtractor:
        if self._vision is None:
            self._vision = VisionExtractor()  
        return self._vision

    def extract(self, doc: DocumentInput) -> ExtractedDocument:
        if doc.actual_type is not None:
            return self.fixture.extract(doc)
        return self.vision.extract(doc)
