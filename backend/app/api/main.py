"""FastAPI application.

Endpoints:
  GET  /health                     liveness
  GET  /api/policy                 policy summary for the UI
  POST /api/claims                 submit a claim (JSON; fixture or base64 docs)
  POST /api/claims/upload          submit a claim (multipart file upload)
  GET  /api/claims                 list processed claims
  GET  /api/claims/{claim_id}      one claim with full outcome + trace

Submissions are processed synchronously (the pipeline is seconds-fast for
fixtures, tens of seconds for vision) and persisted with the full trace.
"""

from __future__ import annotations

import base64
import json
from datetime import date

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import repository
from app.db.database import SessionLocal, init_db
from app.graph.pipeline import ClaimsPipeline
from app.models.claim import ClaimSubmission, DocumentInput
from app.models.decision import ClaimOutcome
from app.policy.loader import get_policy

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Plum Claims Processing", version="1.0.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline: ClaimsPipeline | None = None


def get_pipeline() -> ClaimsPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ClaimsPipeline(get_policy())
    return _pipeline


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/policy")
def policy_summary():
    policy = get_policy()
    return {
        "policy_id": policy.policy_id,
        "policy_name": policy.policy_name,
        "insurer": policy.insurer,
        "categories": list(policy.opd_categories.keys()),
        "document_requirements": {
            k: v.model_dump() for k, v in policy.document_requirements.items()
        },
        "members": [
            {"member_id": m.member_id, "name": m.name,
             "relationship": m.relationship}
            for m in policy.members
        ],
        "network_hospitals": policy.network_hospitals,
        "per_claim_limit": policy.coverage.per_claim_limit,
    }


def _process(claim: ClaimSubmission, db: Session) -> ClaimOutcome:
    stored = repository.member_history(db, claim.member_id)
    claim = claim.model_copy(update={
        "claims_history": repository.merge_history(claim.claims_history, stored),
    })
    outcome = get_pipeline().run(claim)
    repository.save_outcome(db, claim, outcome)
    return outcome


@app.post("/api/claims", response_model=ClaimOutcome)
def submit_claim(claim: ClaimSubmission, db: Session = Depends(get_db)):
    return _process(claim, db)


@app.post("/api/claims/upload", response_model=ClaimOutcome)
async def submit_claim_upload(
    member_id: str = Form(...),
    policy_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: float = Form(...),
    hospital_name: str | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    documents = []
    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(413, f"{f.filename} exceeds the 10MB limit.")
        documents.append(DocumentInput(
            file_id=f"UP{i + 1:03d}",
            file_name=f.filename,
            file_data=base64.standard_b64encode(data).decode(),
            media_type=f.content_type or "image/jpeg",
        ))
    try:
        claim = ClaimSubmission(
            member_id=member_id,
            policy_id=policy_id,
            claim_category=claim_category,
            treatment_date=date.fromisoformat(treatment_date),
            claimed_amount=claimed_amount,
            hospital_name=hospital_name,
            documents=documents,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _process(claim, db)


@app.get("/api/claims")
def list_claims(db: Session = Depends(get_db)):
    return [
        {
            "claim_id": r.claim_id,
            "member_id": r.member_id,
            "claim_category": r.claim_category,
            "treatment_date": str(r.treatment_date),
            "claimed_amount": r.claimed_amount,
            "outcome_type": r.outcome_type,
            "status": r.status,
            "approved_amount": r.approved_amount,
            "confidence_score": r.confidence_score,
            "degraded": r.degraded,
            "created_at": r.created_at.isoformat(),
        }
        for r in repository.list_claims(db)
    ]


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str, db: Session = Depends(get_db)):
    record = repository.get_claim(db, claim_id)
    if record is None:
        raise HTTPException(404, f"Claim {claim_id} not found.")
    return {
        "claim_id": record.claim_id,
        "submission": record.submission_json,
        "outcome": record.outcome_json,
        "created_at": record.created_at.isoformat(),
    }
