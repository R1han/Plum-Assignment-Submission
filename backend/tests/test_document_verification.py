"""Document verification tests pinned to TC001, TC002, TC003."""

from datetime import date

import pytest

from app.agents.document_verification import DocumentVerificationAgent, names_match
from app.models.claim import (
    ClaimCategory,
    ClaimSubmission,
    DocumentContent,
    DocumentInput,
    LineItem,
)
from app.models.decision import DocumentIssueCode
from app.models.extraction import ExtractedDocument
from app.policy.loader import load_policy


@pytest.fixture(scope="module")
def agent():
    return DocumentVerificationAgent(load_policy())


def make_claim(**overrides) -> ClaimSubmission:
    base = dict(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        documents=[DocumentInput(file_id="F0", actual_type="PRESCRIPTION")],
    )
    base.update(overrides)
    return ClaimSubmission(**base)


def doc(file_id, doc_type, *, quality="GOOD", patient=None, file_name=None):
    return ExtractedDocument(
        file_id=file_id,
        file_name=file_name,
        doc_type=doc_type,
        quality=quality,
        content=DocumentContent(patient_name=patient),
    )


def test_tc001_wrong_document_type(agent):
    """Two prescriptions for a consultation claim that needs Rx + bill."""
    claim = make_claim()
    docs = [
        doc("F001", "PRESCRIPTION", file_name="dr_sharma_prescription.jpg"),
        doc("F002", "PRESCRIPTION", file_name="another_prescription.jpg"),
    ]
    trace = []
    result = agent.verify(claim, docs, trace)
    assert not result.ok
    issue = result.issues[0]
    assert issue.code == DocumentIssueCode.MISSING_DOCUMENT
    assert "prescription" in issue.message.lower()
    assert "hospital bill" in issue.message.lower()
    assert "2 prescriptions" in issue.message.lower()


def test_tc002_unreadable_document(agent):
    """Valid Rx + unreadable pharmacy bill -> ask re-upload, don't reject."""
    claim = make_claim(member_id="EMP004", claim_category=ClaimCategory.PHARMACY,
                       treatment_date=date(2024, 10, 25), claimed_amount=800)
    docs = [
        doc("F003", "PRESCRIPTION", patient="Sneha Reddy"),
        doc("F004", "PHARMACY_BILL", quality="UNREADABLE",
            file_name="blurry_bill.jpg"),
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    issue = result.issues[0]
    assert issue.code == DocumentIssueCode.UNREADABLE_DOCUMENT
    assert issue.file_id == "F004"
    assert "re-upload" in issue.message.lower()
    assert "reject" not in issue.message.lower()


def test_tc003_documents_belong_to_different_patients(agent):
    claim = make_claim()
    docs = [
        doc("F005", "PRESCRIPTION", patient="Rajesh Kumar",
            file_name="prescription_rajesh.jpg"),
        doc("F006", "HOSPITAL_BILL", patient="Arjun Mehta",
            file_name="bill_arjun.jpg"),
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    issue = result.issues[0]
    assert issue.code == DocumentIssueCode.PATIENT_MISMATCH
    assert "Rajesh Kumar" in issue.message
    assert "Arjun Mehta" in issue.message


def test_clean_documents_pass(agent):
    claim = make_claim()
    docs = [
        doc("F007", "PRESCRIPTION", patient="Rajesh Kumar"),
        doc("F008", "HOSPITAL_BILL", patient="Rajesh Kumar"),
    ]
    trace = []
    result = agent.verify(claim, docs, trace)
    assert result.ok
    assert result.patient_name == "Rajesh Kumar"
    assert any(s.check == "required_documents" and s.status.value == "PASS"
               for s in trace)


def test_dependent_patient_allowed(agent):
    """EMP001's dependent (Sunita Kumar, DEP001) can be the patient."""
    claim = make_claim()
    docs = [
        doc("F1", "PRESCRIPTION", patient="Sunita Kumar"),
        doc("F2", "HOSPITAL_BILL", patient="Sunita Kumar"),
    ]
    result = agent.verify(claim, docs, [])
    assert result.ok


def test_non_member_patient_flagged(agent):
    claim = make_claim()
    docs = [
        doc("F1", "PRESCRIPTION", patient="Arjun Mehta"),
        doc("F2", "HOSPITAL_BILL", patient="Arjun Mehta"),
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    assert result.issues[0].code == DocumentIssueCode.PATIENT_MISMATCH


def test_names_match_tolerance():
    assert names_match("Rajesh Kumar", "Mr. Rajesh Kumar")
    assert names_match("RAJESH KUMAR", "rajesh kumar")
    assert names_match("Rajesh", "Rajesh Kumar") 
    assert not names_match("Rajesh Kumar", "Arjun Mehta")
    assert names_match(None, "Rajesh Kumar")  


def edoc(file_id, doc_type, *, quality="GOOD", confidence=1.0, warnings=None,
         content=None):
    return ExtractedDocument(
        file_id=file_id, doc_type=doc_type, quality=quality,
        extraction_confidence=confidence, warnings=warnings or [],
        content=content or DocumentContent(), source="vision",
    )


def test_low_confidence_partial_bill_blocked(agent):
    """A vision-extracted bill labeled PARTIAL but with low extraction
    confidence must be treated as unreadable (live TC002 equivalent)."""
    claim = make_claim(member_id="EMP004", claim_category=ClaimCategory.PHARMACY,
                       treatment_date=date(2024, 10, 25), claimed_amount=800)
    docs = [
        edoc("UP001", "PRESCRIPTION", content=DocumentContent(patient_name="Sneha Reddy")),
        edoc("UP002", "PHARMACY_BILL", quality="PARTIAL", confidence=0.55,
             warnings=["Exact amounts for line items are blurry"],
             content=DocumentContent(total=800)),
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    issue = result.issues[0]
    assert issue.code == DocumentIssueCode.UNREADABLE_DOCUMENT
    assert issue.file_id == "UP002"
    assert "re-upload" in issue.message.lower()


def test_partial_bill_with_unreliable_amounts_blocked(agent):
    """Even at decent confidence, a PARTIAL bill whose warnings flag the
    amounts cannot back a payout."""
    claim = make_claim(member_id="EMP004", claim_category=ClaimCategory.PHARMACY,
                       treatment_date=date(2024, 10, 25), claimed_amount=800)
    docs = [
        edoc("UP001", "PRESCRIPTION", content=DocumentContent(patient_name="Sneha Reddy")),
        edoc("UP002", "PHARMACY_BILL", quality="PARTIAL", confidence=0.75,
             warnings=["Subtotal and total amounts are partially illegible"],
             content=DocumentContent(total=800)),
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    assert result.issues[0].code == DocumentIssueCode.UNREADABLE_DOCUMENT


def test_bill_with_no_amounts_blocked(agent):
    claim = make_claim()
    docs = [
        edoc("UP001", "PRESCRIPTION", content=DocumentContent(patient_name="Rajesh Kumar")),
        edoc("UP002", "HOSPITAL_BILL",
             content=DocumentContent(patient_name="Rajesh Kumar")),  # no total/items
    ]
    result = agent.verify(claim, docs, [])
    assert not result.ok
    assert result.issues[0].code == DocumentIssueCode.UNREADABLE_DOCUMENT


def test_partial_bill_with_reliable_amounts_passes(agent):
    """PARTIAL is fine when only secondary fields are obscured — the amounts
    are intact, so the claim can proceed."""
    claim = make_claim()
    docs = [
        edoc("UP001", "PRESCRIPTION", content=DocumentContent(patient_name="Rajesh Kumar")),
        edoc("UP002", "HOSPITAL_BILL", quality="PARTIAL", confidence=0.8,
             warnings=["GSTIN partially obscured by stamp"],
             content=DocumentContent(
                 patient_name="Rajesh Kumar", total=1500,
                 line_items=[LineItem(description="Consultation Fee", amount=1500)],
             )),
    ]
    result = agent.verify(claim, docs, [])
    assert result.ok
