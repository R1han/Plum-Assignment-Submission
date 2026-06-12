"""Fraud detection (TC009) and confidence formula tests."""

from datetime import date

import pytest

from app.engine.confidence import compute_confidence
from app.engine.fraud import FraudAgent
from app.models.claim import ClaimCategory, ClaimSubmission, DocumentInput
from app.policy.loader import load_policy


@pytest.fixture(scope="module")
def agent():
    return FraudAgent(load_policy())


def make_claim(**overrides) -> ClaimSubmission:
    base = dict(
        member_id="EMP008",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 10, 30),
        claimed_amount=4800,
        documents=[DocumentInput(file_id="F0", actual_type="PRESCRIPTION")],
    )
    base.update(overrides)
    return ClaimSubmission(**base)


def test_tc009_same_day_claims_flagged(agent):
    claim = make_claim(claims_history=[
        {"claim_id": "CLM_0081", "date": "2024-10-30", "amount": 1200, "provider": "City Clinic A"},
        {"claim_id": "CLM_0082", "date": "2024-10-30", "amount": 1800, "provider": "City Clinic B"},
        {"claim_id": "CLM_0083", "date": "2024-10-30", "amount": 2100, "provider": "Wellness Center"},
    ])
    trace = []
    result = agent.assess(claim, [], trace)
    assert result.flagged and result.route_manual_review
    assert any("4 claims" in s for s in result.signals)
    assert any("CLM_0081" in s for s in result.signals)


def test_no_history_no_flags(agent):
    result = agent.assess(make_claim(), [], [])
    assert not result.flagged
    assert not result.route_manual_review


def test_high_value_routes_manual_review(agent):
    result = agent.assess(make_claim(claimed_amount=30000), [], [])
    assert result.route_manual_review
    assert any("25000" in s.replace(",", "") for s in result.signals)


def test_alteration_warnings_flagged(agent):
    result = agent.assess(
        make_claim(), ["amount has correction marks near total"], []
    )
    assert result.flagged
    assert any("alteration" in s.lower() for s in result.signals)



def test_clean_claim_confidence_above_085():
    report = compute_confidence(1.0, "exact", 0, 0)
    assert report.score == 0.95  # TC004 expects > 0.85


def test_keyword_match_keeps_high_confidence():
    report = compute_confidence(1.0, "keyword", 0, 0)
    assert report.score == 0.93  # TC012 expects > 0.90


def test_component_failure_drops_confidence():
    clean = compute_confidence(1.0, "exact", 0, 0).score
    degraded = compute_confidence(1.0, "exact", 1, 0).score
    assert degraded < clean
    assert degraded == 0.75  # TC011: visibly reduced but not floor
    assert any("component" in d for d in compute_confidence(1.0, "exact", 1, 0).deductions)


def test_llm_certainty_penalty():
    assert compute_confidence(1.0, "llm", 0, 0).score == 0.87


def test_floor():
    assert compute_confidence(0.0, "llm", 3, 10).score == 0.05
