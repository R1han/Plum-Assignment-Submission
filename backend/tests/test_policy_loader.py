from datetime import date

import pytest

from app.policy.loader import load_policy


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def test_policy_parses(policy):
    assert policy.policy_id == "PLUM_GHI_2024"
    assert policy.coverage.per_claim_limit == 5000
    assert len(policy.members) == 12


def test_category_lookup_case_insensitive(policy):
    cat = policy.get_category("CONSULTATION")
    assert cat is not None
    assert cat.copay_percent == 10
    assert cat.network_discount_percent == 20


def test_member_lookup_and_join_date(policy):
    assert policy.get_member("EMP005").join_date == date(2024, 9, 1)
    # Dependent inherits primary member's join date
    assert policy.member_join_date("DEP001") == date(2024, 4, 1)
    assert policy.get_member("NOPE") is None


def test_document_requirements(policy):
    req = policy.get_document_requirement("CONSULTATION")
    assert req.required == ["PRESCRIPTION", "HOSPITAL_BILL"]


def test_network_hospital_matching(policy):
    assert policy.is_network_hospital("Apollo Hospitals")
    assert policy.is_network_hospital("Apollo Hospitals, Bengaluru")
    assert not policy.is_network_hospital("City Clinic")
    assert not policy.is_network_hospital(None)
