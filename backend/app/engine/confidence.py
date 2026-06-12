"""Confidence scoring — a deterministic, documented formula.

Input:  extraction confidence, the weakest classifier certainty used on the
        decision path, component failures, and extraction warnings.
Output: score in [0.05, 0.95] plus the itemized deductions (for the trace).
Errors: none raised.

The score answers: "how sure is the SYSTEM that this decision is right?"
Policy math is exact, so deductions come only from the fuzzy parts:
  base                                0.95  (never 1.0 — extraction is OCR)
  extraction shortfall    -(1 - conf) * 0.20
  classifier certainty    keyword -0.02, llm -0.08
  each component failure  -0.20
  each extraction warning -0.02 (capped at -0.10)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

BASE = 0.95
FLOOR = 0.05


class ConfidenceReport(BaseModel):
    score: float
    deductions: list[str] = Field(default_factory=list)


def compute_confidence(
    extraction_confidence: float = 1.0,
    classifier_certainty: str = "exact",
    component_failures: int = 0,
    warning_count: int = 0,
) -> ConfidenceReport:
    score = BASE
    deductions: list[str] = []

    shortfall = round((1.0 - extraction_confidence) * 0.20, 4)
    if shortfall:
        score -= shortfall
        deductions.append(
            f"-{shortfall:g}: extraction confidence {extraction_confidence:g}"
        )

    certainty_penalty = {"exact": 0.0, "keyword": 0.02, "llm": 0.08}.get(
        classifier_certainty, 0.08
    )
    if certainty_penalty:
        score -= certainty_penalty
        deductions.append(
            f"-{certainty_penalty:g}: weakest text-match certainty "
            f"'{classifier_certainty}'"
        )

    if component_failures:
        penalty = 0.20 * component_failures
        score -= penalty
        deductions.append(
            f"-{penalty:g}: {component_failures} pipeline component(s) failed "
            "and were skipped"
        )

    if warning_count:
        penalty = min(0.02 * warning_count, 0.10)
        score -= penalty
        deductions.append(
            f"-{penalty:g}: {warning_count} extraction warning(s)"
        )

    return ConfidenceReport(
        score=max(round(score, 3), FLOOR), deductions=deductions
    )
