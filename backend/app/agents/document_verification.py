"""Document verification agent — the early gate (TC001–TC003).

Input:  ClaimSubmission + list[ExtractedDocument] + Policy.
Output: VerificationResult; ``ok=False`` means the pipeline must stop before
        adjudication and return the member-facing issues.
Errors: never raises on claim data; structural problems become issues.

Checks, in order:
  1. required document types present for the claim category
  2. every required document is readable (quality != UNREADABLE)
  3. all documents belong to the same patient
  4. the patient on the documents is the member (or a covered dependent)

Issue messages are member-facing and must be specific: they name the document
type that was uploaded, the one that is needed, and the exact file to fix.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.models.claim import ClaimSubmission, DocumentQuality
from app.models.decision import (
    DocumentIssue,
    DocumentIssueCode,
    TraceStatus,
    TraceStep,
)
from app.models.extraction import ExtractedDocument
from app.models.policy import Policy

_TITLES = {"mr", "mrs", "ms", "dr", "smt", "shri", "master", "baby"}

MIN_USABLE_CONFIDENCE = 0.6

_AMOUNT_WARNING_FRAGMENTS = (
    "amount", "total", "subtotal", "price", "figure", "₹", "rs.",
)


def _name_tokens(name: str) -> frozenset[str]:
    tokens = re.sub(r"[^a-z\s]", " ", name.lower()).split()
    return frozenset(t for t in tokens if t not in _TITLES)


def names_match(a: str | None, b: str | None) -> bool:
    """Tolerant person-name comparison: token-set equality or containment
    ('Rajesh Kumar' matches 'Mr. Rajesh Kumar', not 'Arjun Mehta')."""
    if not a or not b:
        return True  
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return True
    return ta == tb or ta <= tb or tb <= ta


def _human(doc_type: str, plural: bool = False) -> str:
    label = doc_type.replace("_", " ").lower()
    return label + ("s" if plural else "")


class VerificationResult(BaseModel):
    ok: bool
    issues: list[DocumentIssue] = Field(default_factory=list)
    patient_name: str | None = None  


class DocumentVerificationAgent:
    COMPONENT = "document_verification"

    def __init__(self, policy: Policy):
        self.policy = policy

    def verify(
        self,
        claim: ClaimSubmission,
        docs: list[ExtractedDocument],
        trace: list[TraceStep],
    ) -> VerificationResult:
        issues: list[DocumentIssue] = []
        issues += self._check_required_types(claim, docs, trace)
        issues += self._check_readability(claim, docs, trace)
        patient_name = None
        if not issues:
            name_issues, patient_name = self._check_patient_consistency(
                claim, docs, trace
            )
            issues += name_issues
        return VerificationResult(
            ok=not issues, issues=issues, patient_name=patient_name
        )

    def _check_required_types(self, claim, docs, trace) -> list[DocumentIssue]:
        requirement = self.policy.get_document_requirement(claim.claim_category.value)
        if requirement is None:
            self._trace(trace, "required_documents", TraceStatus.ERROR,
                        f"No document requirements configured for "
                        f"{claim.claim_category.value}; cannot verify.")
            return []

        present = [d.doc_type.value for d in docs]
        missing = [t for t in requirement.required if t not in present]
        if not missing:
            self._trace(trace, "required_documents", TraceStatus.PASS,
                        f"All required documents present for "
                        f"{claim.claim_category.value}: "
                        f"{', '.join(requirement.required)}.",
                        {"required": requirement.required, "uploaded": present})
            return []

        uploaded_summary = self._summarize_uploads(present)
        issues = []
        for miss in missing:
            message = (
                f"Your {claim.claim_category.value.lower()} claim requires "
                f"{self._requirement_phrase(requirement.required)}. "
                f"You uploaded {uploaded_summary}, but no {_human(miss)} was "
                f"included. Please upload the {_human(miss)} for your treatment "
                f"on {claim.treatment_date} and resubmit."
            )
            issues.append(DocumentIssue(
                code=DocumentIssueCode.MISSING_DOCUMENT,
                message=message,
                expected=miss,
                found=", ".join(present),
            ))
        self._trace(trace, "required_documents", TraceStatus.FAIL,
                    f"Missing required document(s): {', '.join(missing)}. "
                    f"Uploaded: {uploaded_summary}.",
                    {"required": requirement.required, "uploaded": present,
                     "missing": missing})
        return issues

    def _check_readability(self, claim, docs, trace) -> list[DocumentIssue]:
        issues = []
        for doc in docs:
            reason = self._unusable_reason(doc)
            if reason is None:
                continue
            label = _human(doc.doc_type.value)
            message = (
                f"The {label} you uploaded "
                f"({doc.file_name or doc.file_id}) could not be read reliably "
                f"— {reason}. Please take a clear, well-lit photo of the "
                f"{label} and re-upload just that document. The rest of your "
                f"claim is fine and will be processed once we can read it."
            )
            issues.append(DocumentIssue(
                code=DocumentIssueCode.UNREADABLE_DOCUMENT,
                message=message,
                file_id=doc.file_id,
                expected=f"readable {label}",
                found=reason,
            ))
            self._trace(trace, "document_readability", TraceStatus.FAIL,
                        f"Document {doc.file_id} ({doc.doc_type.value}) is not "
                        f"usable: {reason}.",
                        {"file_id": doc.file_id, "doc_type": doc.doc_type.value,
                         "quality": doc.quality.value,
                         "extraction_confidence": doc.extraction_confidence,
                         "warnings": doc.warnings})
        if not issues:
            self._trace(trace, "document_readability", TraceStatus.PASS,
                        "All documents are readable and their material fields "
                        "were extracted with usable confidence.")
        return issues

    @staticmethod
    def _unusable_reason(doc) -> str | None:
        """A document is unusable if it is unreadable outright, if extraction
        confidence is below the usability floor, or — for bills — if the
        amounts that would back the payout are themselves unreliable. The
        vision model's PARTIAL label is not trusted on its own (a 'partially
        readable' bill whose totals are guesses must not drive a payout)."""
        if doc.quality == DocumentQuality.UNREADABLE:
            return "the image is too blurry or unclear"
        if doc.extraction_confidence < MIN_USABLE_CONFIDENCE:
            return (f"the image quality is too low to extract it with "
                    f"confidence (extraction confidence "
                    f"{doc.extraction_confidence:g})")
        if doc.source == "vision" and doc.doc_type.value.endswith("BILL"):
            c = doc.content
            if c.total is None and not c.line_items:
                return "no billed amounts could be read from it"
            if doc.quality == DocumentQuality.PARTIAL and any(
                frag in w.lower()
                for w in doc.warnings
                for frag in _AMOUNT_WARNING_FRAGMENTS
            ):
                return ("the billed amounts are blurry or unclear, and a "
                        "claim cannot be paid against amounts we cannot "
                        "verify")
        return None

    def _check_patient_consistency(self, claim, docs, trace):
        named = [
            (d, d.content.patient_name)
            for d in docs if d.content.patient_name
        ]
        issues: list[DocumentIssue] = []

        for i in range(len(named)):
            for j in range(i + 1, len(named)):
                (doc_a, name_a), (doc_b, name_b) = named[i], named[j]
                if not names_match(name_a, name_b):
                    message = (
                        f"The documents you uploaded belong to different "
                        f"patients: the {_human(doc_a.doc_type.value)} "
                        f"({doc_a.file_name or doc_a.file_id}) is for "
                        f"'{name_a}', but the {_human(doc_b.doc_type.value)} "
                        f"({doc_b.file_name or doc_b.file_id}) is for "
                        f"'{name_b}'. All documents in one claim must belong "
                        f"to the same patient. Please check your files and "
                        f"re-upload the correct documents."
                    )
                    issues.append(DocumentIssue(
                        code=DocumentIssueCode.PATIENT_MISMATCH,
                        message=message,
                        file_id=doc_b.file_id,
                        expected=name_a,
                        found=name_b,
                    ))
                    self._trace(trace, "patient_consistency", TraceStatus.FAIL,
                                f"Patient mismatch: '{name_a}' on "
                                f"{doc_a.file_id} vs '{name_b}' on {doc_b.file_id}.",
                                {"names": [name_a, name_b],
                                 "files": [doc_a.file_id, doc_b.file_id]})
        if issues:
            return issues, None

        consensus = named[0][1] if named else None

        if consensus:
            member = self.policy.get_member(claim.member_id)
            allowed = []
            if member:
                allowed.append(member.name)
                for dep_id in member.dependents:
                    dep = self.policy.get_member(dep_id)
                    if dep:
                        allowed.append(dep.name)
            if member and not any(names_match(consensus, n) for n in allowed):
                message = (
                    f"The documents are for '{consensus}', but this claim was "
                    f"submitted for {member.name} ({claim.member_id}). Covered "
                    f"patients on this membership: {', '.join(allowed)}. If "
                    f"you meant to claim for a dependent, make sure they are "
                    f"registered; otherwise upload documents for the right "
                    f"patient."
                )
                issues.append(DocumentIssue(
                    code=DocumentIssueCode.PATIENT_MISMATCH,
                    message=message,
                    expected=member.name,
                    found=consensus,
                ))
                self._trace(trace, "patient_on_roster", TraceStatus.FAIL,
                            f"Patient '{consensus}' is not the member or a "
                            f"covered dependent of {claim.member_id}.",
                            {"patient": consensus, "allowed": allowed})
                return issues, None
            self._trace(trace, "patient_on_roster", TraceStatus.PASS,
                        f"Patient '{consensus}' matches the membership of "
                        f"{claim.member_id}.")

        self._trace(trace, "patient_consistency", TraceStatus.PASS,
                    "All documents belong to the same patient."
                    + (f" Patient: {consensus}." if consensus else ""))
        return issues, consensus

    @staticmethod
    def _summarize_uploads(present: list[str]) -> str:
        if not present:
            return "no documents"
        counts: dict[str, int] = {}
        for p in present:
            counts[p] = counts.get(p, 0) + 1
        return ", ".join(
            f"{n} {_human(t, plural=n > 1)}" for t, n in counts.items()
        )

    @staticmethod
    def _requirement_phrase(required: list[str]) -> str:
        labels = [f"a {_human(t)}" for t in required]
        if len(labels) == 1:
            return labels[0]
        return "both " + " and ".join(labels) if len(labels) == 2 else ", ".join(labels)

    def _trace(self, trace, check, status, detail, data=None):
        trace.append(TraceStep(
            component=self.COMPONENT, check=check, status=status,
            detail=detail, data=data or {},
        ))
