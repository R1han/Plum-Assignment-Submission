"""Document verification tests pinned to TC001, TC002, TC003."""

from datetime import date

import pytest

from app.agents.document_verification import DocumentVerificationAgent, names_match
from app.models.claim import ClaimCategory, ClaimSubmission, DocumentContent, DocumentInput
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
    # Message must name the uploaded type AND the required type — not generic.
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
    # Must not read as a claim rejection
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
    # Both names must be surfaced to the member.
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
    assert names_match("Rajesh", "Rajesh Kumar")  # subset tolerated
    assert not names_match("Rajesh Kumar", "Arjun Mehta")
    assert names_match(None, "Rajesh Kumar")  # missing name is not a mismatch
