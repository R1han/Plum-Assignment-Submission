"""API tests using an isolated in-memory database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import main as api_main
from app.db import database
from app.engine.rules import Classifier
from app.graph.pipeline import ClaimsPipeline
from app.policy.loader import get_policy


@pytest.fixture()
def client(monkeypatch):
    # StaticPool keeps the single in-memory DB across sessions
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    monkeypatch.setattr(api_main, "SessionLocal", TestSession)
    monkeypatch.setattr(
        api_main, "_pipeline", ClaimsPipeline(get_policy(), classifier=Classifier())
    )
    with TestClient(api_main.app) as c:
        yield c


TC004_PAYLOAD = {
    "member_id": "EMP001",
    "policy_id": "PLUM_GHI_2024",
    "claim_category": "CONSULTATION",
    "treatment_date": "2024-11-01",
    "claimed_amount": 1500,
    "ytd_claims_amount": 5000,
    "documents": [
        {"file_id": "F007", "actual_type": "PRESCRIPTION", "content": {
            "doctor_name": "Dr. Arun Sharma", "patient_name": "Rajesh Kumar",
            "diagnosis": "Viral Fever"}},
        {"file_id": "F008", "actual_type": "HOSPITAL_BILL", "content": {
            "hospital_name": "City Clinic", "patient_name": "Rajesh Kumar",
            "line_items": [{"description": "Consultation Fee", "amount": 1500}],
            "total": 1500}},
    ],
}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_policy_endpoint(client):
    body = client.get("/api/policy").json()
    assert body["policy_id"] == "PLUM_GHI_2024"
    assert "CONSULTATION" in body["document_requirements"]


def test_submit_and_retrieve_claim(client):
    response = client.post("/api/claims", json=TC004_PAYLOAD)
    assert response.status_code == 200
    outcome = response.json()
    assert outcome["outcome_type"] == "DECISION"
    assert outcome["decision"]["status"] == "APPROVED"
    assert outcome["decision"]["approved_amount"] == 1350
    assert outcome["trace"]  # trace persisted in the response

    claim_id = outcome["claim_id"]
    listing = client.get("/api/claims").json()
    assert any(c["claim_id"] == claim_id for c in listing)

    detail = client.get(f"/api/claims/{claim_id}").json()
    assert detail["outcome"]["decision"]["status"] == "APPROVED"
    assert detail["outcome"]["trace"]


def test_invalid_submission_is_422_not_500(client):
    bad = dict(TC004_PAYLOAD, claimed_amount=-5)
    assert client.post("/api/claims", json=bad).status_code == 422


def test_unknown_claim_404(client):
    assert client.get("/api/claims/NOPE").status_code == 404


def test_stored_history_feeds_fraud_check(client):
    """Submitting the 4th same-day claim via the API must route to manual
    review using history accumulated in the database."""
    payload = {
        "member_id": "EMP008",
        "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION",
        "treatment_date": "2024-10-30",
        "claimed_amount": 1200,
        "documents": [
            {"file_id": "F1", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Migraine", "patient_name": "Ravi Menon"}},
            {"file_id": "F2", "actual_type": "HOSPITAL_BILL",
             "content": {"total": 1200, "patient_name": "Ravi Menon"}},
        ],
    }
    for _ in range(3):
        assert client.post("/api/claims", json=payload).status_code == 200
    fourth = client.post("/api/claims", json=payload).json()
    assert fourth["decision"]["status"] == "MANUAL_REVIEW"
    assert fourth["decision"]["fraud_signals"]
