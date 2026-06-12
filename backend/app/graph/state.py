"""LangGraph pipeline state.

``trace`` and ``component_failures`` use the additive reducer so every node
can append without clobbering earlier entries — the trace is the system of
record for explainability.
"""

from __future__ import annotations

import operator
from typing import Annotated

from pydantic import BaseModel, Field

from app.agents.document_verification import VerificationResult
from app.engine.fraud import FraudAssessment
from app.engine.rules import AdjudicationResult
from app.models.claim import ClaimSubmission
from app.models.decision import ClaimOutcome, ComponentFailure, TraceStep
from app.models.extraction import ClaimFacts, ExtractedDocument


class PipelineState(BaseModel):
    claim_id: str
    claim: ClaimSubmission

    docs: list[ExtractedDocument] = Field(default_factory=list)
    facts: ClaimFacts | None = None
    verification: VerificationResult | None = None
    adjudication: AdjudicationResult | None = None
    fraud: FraudAssessment | None = None

    trace: Annotated[list[TraceStep], operator.add] = Field(default_factory=list)
    component_failures: Annotated[list[ComponentFailure], operator.add] = Field(
        default_factory=list
    )

    outcome: ClaimOutcome | None = None
