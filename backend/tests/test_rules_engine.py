"""Rules engine tests pinned to the assignment's expected outcomes
(TC004, TC005, TC006, TC007, TC008, TC010, TC012 adjudication logic)."""

from datetime import date

import pytest

from app.engine.rules import RulesEngine
from app.models.claim import ClaimCategory, ClaimSubmission, DocumentInput, LineItem
from app.models.decision import DecisionStatus, RejectionReason
from app.models.extraction import ClaimFacts
from app.policy.loader import load_policy


@pytest.fixture(scope="module")
def policy():
    return load_policy()


@pytest.fixture
def engine(policy):
    return RulesEngine(policy)


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


def test_tc004_clean_consultation_full_approval(engine):
    claim = make_claim(ytd_claims_amount=5000)
    facts = ClaimFacts(
        diagnosis="Viral Fever",
        hospital_name="City Clinic, Bengaluru",
        line_items=[
            LineItem(description="Consultation Fee", amount=1000),
            LineItem(description="CBC Test", amount=300),
            LineItem(description="Dengue NS1 Test", amount=200),
        ],
        bill_total=1500,
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.APPROVED
    # 10% co-pay on 1500, no network discount
    assert result.financial.payable_amount == 1350
    assert result.financial.copay_amount == 150
    assert result.financial.network_discount_amount == 0


def test_tc005_diabetes_waiting_period(engine):
    claim = make_claim(
        member_id="EMP005",  # joined 2024-09-01
        treatment_date=date(2024, 10, 15),
        claimed_amount=3000,
    )
    facts = ClaimFacts(diagnosis="Type 2 Diabetes Mellitus")
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.WAITING_PERIOD in result.rejection_reasons
    # 2024-09-01 + 90 days = 2024-11-30; message must state eligibility date
    assert "2024-11-30" in result.member_message


def test_tc006_dental_partial_cosmetic_exclusion(engine):
    claim = make_claim(
        member_id="EMP002",
        claim_category=ClaimCategory.DENTAL,
        treatment_date=date(2024, 10, 15),
        claimed_amount=12000,
    )
    facts = ClaimFacts(
        hospital_name="Smile Dental Clinic",
        line_items=[
            LineItem(description="Root Canal Treatment", amount=8000),
            LineItem(description="Teeth Whitening", amount=4000),
        ],
        bill_total=12000,
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.PARTIAL
    assert result.financial.payable_amount == 8000
    verdicts = {v.description: v.covered for v in result.line_items}
    assert verdicts["Root Canal Treatment"] is True
    assert verdicts["Teeth Whitening"] is False
    # Each rejected line must carry its own reason
    whitening = next(v for v in result.line_items if not v.covered)
    assert whitening.reason


def test_tc007_mri_without_pre_auth(engine):
    claim = make_claim(
        member_id="EMP007",
        claim_category=ClaimCategory.DIAGNOSTIC,
        treatment_date=date(2024, 11, 2),
        claimed_amount=15000,
    )
    facts = ClaimFacts(
        diagnosis="Suspected Lumbar Disc Herniation",
        tests=["MRI Lumbar Spine"],
        line_items=[LineItem(description="MRI Lumbar Spine", amount=15000)],
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.REJECTED
    assert result.rejection_reasons == [RejectionReason.PRE_AUTH_MISSING]
    assert "pre-authorization" in result.member_message.lower()
    assert "resubmit" in result.member_message.lower()


def test_tc008_per_claim_limit(engine):
    claim = make_claim(
        member_id="EMP003",
        treatment_date=date(2024, 10, 20),
        claimed_amount=7500,
        ytd_claims_amount=10000,
    )
    facts = ClaimFacts(
        diagnosis="Gastroenteritis",
        line_items=[
            LineItem(description="Consultation Fee", amount=2000),
            LineItem(description="Medicines", amount=5500),
        ],
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.REJECTED
    assert result.rejection_reasons == [RejectionReason.PER_CLAIM_EXCEEDED]
    # Message must state both the limit and the claimed amount
    assert "5000" in result.member_message.replace(",", "")
    assert "7500" in result.member_message.replace(",", "")


def test_tc010_network_discount_before_copay(engine):
    claim = make_claim(
        member_id="EMP010",
        treatment_date=date(2024, 11, 3),
        claimed_amount=4500,
        hospital_name="Apollo Hospitals",
        ytd_claims_amount=8000,
    )
    facts = ClaimFacts(
        diagnosis="Acute Bronchitis",
        hospital_name="Apollo Hospitals",
        line_items=[
            LineItem(description="Consultation Fee", amount=1500),
            LineItem(description="Medicines", amount=3000),
        ],
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.APPROVED
    f = result.financial
    # 4500 * 0.8 = 3600, then 10% copay -> 3240. Order matters.
    assert f.network_discount_amount == 900
    assert f.amount_after_discount == 3600
    assert f.copay_amount == 360
    assert f.payable_amount == 3240


def test_tc012_obesity_exclusion(engine):
    claim = make_claim(
        member_id="EMP009",
        treatment_date=date(2024, 10, 18),
        claimed_amount=8000,
    )
    facts = ClaimFacts(
        diagnosis="Morbid Obesity — BMI 37",
        treatment="Bariatric Consultation and Customised Diet Plan",
        line_items=[
            LineItem(description="Bariatric Consultation", amount=3000),
            LineItem(description="Personalised Diet and Nutrition Program", amount=5000),
        ],
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.EXCLUDED_CONDITION in result.rejection_reasons
    # Deterministic keyword match -> high certainty path
    assert result.classifier_certainty in ("exact", "keyword")


def test_prescribed_medicine_does_not_trigger_exclusion(engine):
    """Demo 2A regression: the vision extractor folds the prescribed medication
    list into the free-text `treatment` field. A prescribed vitamin must NOT
    void the consultation as an excluded "health supplement" — the claim
    approves on the consultation fee."""
    claim = make_claim(ytd_claims_amount=5000)
    facts = ClaimFacts(
        diagnosis="Viral Fever",
        treatment="Tab Paracetamol 650mg - 1-1-1 x 5 days; "
                  "Tab Vitamin C 500mg - 0-0-1 x 7 days",
        medicines=[
            "Tab Paracetamol 650mg - 1-1-1 x 5 days",
            "Tab Vitamin C 500mg - 0-0-1 x 7 days",
        ],
        hospital_name="City Clinic, Bengaluru",
        line_items=[LineItem(description="Consultation Fee", amount=1500)],
        bill_total=1500,
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.APPROVED, result.member_message
    assert result.financial.payable_amount == 1350
    assert not result.rejection_reasons
    excl = next(s for s in trace if s.check == "exclusions")
    assert excl.status.value == "PASS"


def test_genuine_excluded_treatment_still_rejected_with_medicines(engine):
    """The medicine strip must not weaken real exclusions: a genuine excluded
    procedure in `treatment` is still caught even when medicines are present."""
    claim = make_claim(member_id="EMP009", treatment_date=date(2024, 10, 18))
    facts = ClaimFacts(
        diagnosis="Morbid Obesity — BMI 37",
        treatment="Bariatric surgery; Tab Vitamin C 500mg x 7 days",
        medicines=["Tab Vitamin C 500mg x 7 days"],
    )
    trace = []
    result = engine.adjudicate(claim, facts, trace)
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.EXCLUDED_CONDITION in result.rejection_reasons


def test_initial_waiting_period(engine):
    claim = make_claim(
        member_id="EMP005",  # joined 2024-09-01
        treatment_date=date(2024, 9, 15),  # 14 days in
        claimed_amount=1000,
    )
    facts = ClaimFacts(diagnosis="Viral Fever")
    result = engine.adjudicate(claim, facts, [])
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.WAITING_PERIOD in result.rejection_reasons


def test_unknown_member_rejected(engine):
    claim = make_claim(member_id="EMP999")
    result = engine.adjudicate(claim, ClaimFacts(), [])
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.MEMBER_NOT_FOUND in result.rejection_reasons


def test_below_minimum_amount(engine):
    claim = make_claim(claimed_amount=300)
    result = engine.adjudicate(claim, ClaimFacts(diagnosis="Viral Fever"), [])
    assert result.status == DecisionStatus.REJECTED
    assert RejectionReason.BELOW_MINIMUM_AMOUNT in result.rejection_reasons


def test_trace_records_skipped_checks_after_rejection(engine):
    claim = make_claim(member_id="EMP999")
    trace = []
    engine.adjudicate(claim, ClaimFacts(), trace)
    statuses = {s.check: s.status.value for s in trace}
    assert statuses["member_exists"] == "FAIL"
    # Remaining checks must be visible as SKIPPED, not silently absent
    assert any(s.status.value == "SKIPPED" for s in trace)


def test_vision_lasik_excluded(engine):
    claim = make_claim(
        claim_category=ClaimCategory.VISION,
        claimed_amount=4000,
    )
    facts = ClaimFacts(
        treatment="LASIK Surgery",
        line_items=[LineItem(description="LASIK Surgery", amount=4000)],
    )
    result = engine.adjudicate(claim, facts, [])
    assert result.status == DecisionStatus.REJECTED
