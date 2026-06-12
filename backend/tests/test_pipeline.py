"""End-to-end pipeline tests (offline: fixture documents, no LLM calls)."""

from datetime import date

import pytest

from app.engine.rules import Classifier
from app.graph.pipeline import ClaimsPipeline
from app.models.claim import ClaimSubmission
from app.models.decision import DecisionStatus, DocumentIssueCode, OutcomeType
from app.policy.loader import load_policy


@pytest.fixture(scope="module")
def pipeline():
    # Deterministic classifier only — offline by construction.
    return ClaimsPipeline(load_policy(), classifier=Classifier())


def submit(pipeline, **kwargs):
    return pipeline.run(ClaimSubmission(**kwargs))


def test_tc001_stops_before_decision(pipeline):
    outcome = submit(
        pipeline,
        member_id="EMP001", policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION", treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        documents=[
            {"file_id": "F001", "file_name": "dr_sharma_prescription.jpg",
             "actual_type": "PRESCRIPTION"},
            {"file_id": "F002", "file_name": "another_prescription.jpg",
             "actual_type": "PRESCRIPTION"},
        ],
    )
    assert outcome.outcome_type == OutcomeType.DOCUMENT_ISSUE
    assert outcome.decision is None
    assert outcome.document_issues[0].code == DocumentIssueCode.MISSING_DOCUMENT
    msg = outcome.document_issues[0].message.lower()
    assert "prescription" in msg and "hospital bill" in msg
    # Adjudication must never have run
    assert not any(s.component == "rules_engine" for s in outcome.trace)


def test_tc004_end_to_end_approval(pipeline):
    outcome = submit(
        pipeline,
        member_id="EMP001", policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION", treatment_date=date(2024, 11, 1),
        claimed_amount=1500, ytd_claims_amount=5000,
        documents=[
            {"file_id": "F007", "actual_type": "PRESCRIPTION", "content": {
                "doctor_name": "Dr. Arun Sharma",
                "doctor_registration": "KA/45678/2015",
                "patient_name": "Rajesh Kumar", "date": "2024-11-01",
                "diagnosis": "Viral Fever",
                "medicines": ["Paracetamol 650mg", "Vitamin C 500mg"],
            }},
            {"file_id": "F008", "actual_type": "HOSPITAL_BILL", "content": {
                "hospital_name": "City Clinic, Bengaluru",
                "patient_name": "Rajesh Kumar", "date": "2024-11-01",
                "line_items": [
                    {"description": "Consultation Fee", "amount": 1000},
                    {"description": "CBC Test", "amount": 300},
                    {"description": "Dengue NS1 Test", "amount": 200},
                ],
                "total": 1500,
            }},
        ],
    )
    assert outcome.outcome_type == OutcomeType.DECISION
    d = outcome.decision
    assert d.status == DecisionStatus.APPROVED
    assert d.approved_amount == 1350
    assert d.confidence_score > 0.85
    assert not outcome.degraded
    # Trace must cover every stage
    components = {s.component for s in outcome.trace}
    assert {"intake", "extraction", "document_verification",
            "rules_engine", "fraud_detection", "finalize"} <= components


def test_tc009_fraud_routes_to_manual_review(pipeline):
    outcome = submit(
        pipeline,
        member_id="EMP008", policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION", treatment_date=date(2024, 10, 30),
        claimed_amount=4800,
        claims_history=[
            {"claim_id": "CLM_0081", "date": "2024-10-30", "amount": 1200,
             "provider": "City Clinic A"},
            {"claim_id": "CLM_0082", "date": "2024-10-30", "amount": 1800,
             "provider": "City Clinic B"},
            {"claim_id": "CLM_0083", "date": "2024-10-30", "amount": 2100,
             "provider": "Wellness Center"},
        ],
        documents=[
            {"file_id": "F017", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Migraine", "doctor_name": "Dr. S. Khan"}},
            {"file_id": "F018", "actual_type": "HOSPITAL_BILL",
             "content": {"total": 4800}},
        ],
    )
    d = outcome.decision
    assert d.status == DecisionStatus.MANUAL_REVIEW
    assert d.fraud_signals  # specific signals included in output
    assert any("4 claims" in s for s in d.fraud_signals)
    assert d.rejection_reasons == []  # not auto-rejected


def test_tc011_component_failure_graceful_degradation(pipeline):
    outcome = submit(
        pipeline,
        member_id="EMP006", policy_id="PLUM_GHI_2024",
        claim_category="ALTERNATIVE_MEDICINE", treatment_date=date(2024, 10, 28),
        claimed_amount=4000, simulate_component_failure=True,
        documents=[
            {"file_id": "F021", "actual_type": "PRESCRIPTION", "content": {
                "doctor_name": "Vaidya T. Krishnan",
                "doctor_registration": "AYUR/KL/2345/2019",
                "diagnosis": "Chronic Joint Pain",
                "treatment": "Panchakarma Therapy",
            }},
            {"file_id": "F022", "actual_type": "HOSPITAL_BILL", "content": {
                "hospital_name": "Ayur Wellness Centre", "total": 4000,
                "line_items": [
                    {"description": "Panchakarma Therapy (5 sessions)", "amount": 3000},
                    {"description": "Consultation", "amount": 1000},
                ],
            }},
        ],
    )
    d = outcome.decision
    assert d.status == DecisionStatus.APPROVED  # pipeline survived the failure
    assert outcome.degraded
    assert outcome.component_failures[0].component == "fraud_detection"
    assert d.manual_review_recommended
    # Confidence must be lower than the clean approval path
    assert d.confidence_score < 0.95
    # The failure must be visible in the trace
    assert any(s.status.value == "ERROR" for s in outcome.trace)


def test_clean_alt_medicine_higher_confidence_than_degraded(pipeline):
    """Same claim with and without the injected failure: confidence must drop."""
    base = dict(
        member_id="EMP006", policy_id="PLUM_GHI_2024",
        claim_category="ALTERNATIVE_MEDICINE", treatment_date=date(2024, 10, 28),
        claimed_amount=4000,
        documents=[
            {"file_id": "F021", "actual_type": "PRESCRIPTION", "content": {
                "doctor_registration": "AYUR/KL/2345/2019",
                "diagnosis": "Chronic Joint Pain",
            }},
            {"file_id": "F022", "actual_type": "HOSPITAL_BILL",
             "content": {"total": 4000}},
        ],
    )
    clean = submit(pipeline, **base)
    degraded = submit(pipeline, **base, simulate_component_failure=True)
    assert degraded.decision.confidence_score < clean.decision.confidence_score


def test_unreadable_document_stops_pipeline(pipeline):
    outcome = submit(
        pipeline,
        member_id="EMP004", policy_id="PLUM_GHI_2024",
        claim_category="PHARMACY", treatment_date=date(2024, 10, 25),
        claimed_amount=800,
        documents=[
            {"file_id": "F003", "actual_type": "PRESCRIPTION",
             "quality": "GOOD", "content": {"patient_name": "Sneha Reddy"}},
            {"file_id": "F004", "file_name": "blurry_bill.jpg",
             "actual_type": "PHARMACY_BILL", "quality": "UNREADABLE"},
        ],
    )
    assert outcome.outcome_type == OutcomeType.DOCUMENT_ISSUE
    issue = outcome.document_issues[0]
    assert issue.code == DocumentIssueCode.UNREADABLE_DOCUMENT
    assert issue.file_id == "F004"
