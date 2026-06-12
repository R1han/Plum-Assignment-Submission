"""Deterministic text matching against policy term lists.

This is the first tier of the two-tier classification strategy: fast,
reproducible keyword/substring matching derived from the policy file. Anything
this tier cannot resolve confidently is escalated to the LLM classifier
(app/agents/classifiers.py). Keeping tier one deterministic makes the eval
reproducible and the trace checkable.

Input:  free text (diagnosis, treatment, line item descriptions) + policy lists.
Output: MatchResult(matched, rule, certainty) — certainty is "exact",
        "keyword", or "none".
Errors: none raised; unmatched text returns matched=False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Medical shorthand seen on Indian prescriptions (sample_documents_guide.md)
CONDITION_SYNONYMS: dict[str, list[str]] = {
    "diabetes": ["diabetes", "diabetic", "t2dm", "dm type 2", "mellitus"],
    "hypertension": ["hypertension", "htn", "high blood pressure"],
    "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid"],
    "joint_replacement": ["joint replacement", "knee replacement", "hip replacement", "arthroplasty"],
    "maternity": ["maternity", "pregnancy", "antenatal", "delivery", "caesarean"],
    "mental_health": ["mental health", "depression", "anxiety", "psychiatric", "psychiatry"],
    "obesity_treatment": ["obesity", "obese", "bariatric", "weight loss", "weight-loss"],
    "hernia": ["hernia"],
    "cataract": ["cataract"],
}

# Keyword expansions for the policy's exclusion condition strings.
EXCLUSION_SYNONYMS: dict[str, list[str]] = {
    "Self-inflicted injuries": ["self-inflicted", "self inflicted"],
    "War or nuclear hazard": ["war injury", "nuclear"],
    "Substance abuse treatment": ["substance abuse", "de-addiction", "deaddiction", "alcohol dependence", "drug abuse"],
    "Experimental treatments": ["experimental"],
    "Infertility and assisted reproduction": ["infertility", "ivf", "assisted reproduction"],
    "Obesity and weight loss programs": ["obesity", "obese", "weight loss", "weight-loss", "diet plan", "diet program", "diet and nutrition", "nutrition program", "bariatric"],
    "Bariatric surgery": ["bariatric"],
    "Cosmetic or aesthetic procedures": ["cosmetic", "aesthetic", "whitening", "veneer", "bleaching", "implant (cosmetic)"],
    "Vaccination (non-medically necessary)": ["vaccination", "vaccine"],
    "Health supplements and tonics": ["supplement", "tonic"],
}


@dataclass
class MatchResult:
    matched: bool
    rule: str | None = None 
    certainty: str = "none"  


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def contains_phrase(text: str, phrase: str) -> bool:
    """Word-boundary phrase containment ('hernia' must NOT match 'herniation')."""
    return re.search(rf"\b{re.escape(normalize(phrase))}\b", normalize(text)) is not None


def match_against_list(text: str, policy_list: list[str]) -> MatchResult:
    """Match text against a policy list (e.g. covered/excluded procedures).

    Exact (normalized) equality, then bidirectional substring containment.
    """
    if not text:
        return MatchResult(False)
    needle = normalize(text)
    for entry in policy_list:
        entry_norm = normalize(entry)
        if needle == entry_norm:
            return MatchResult(True, entry, "exact")
    for entry in policy_list:
        entry_norm = normalize(entry)
        entry_core = normalize(re.sub(r"\(.*?\)", "", entry))
        if entry_core and (entry_core in needle or needle in entry_core):
            return MatchResult(True, entry, "keyword")
    return MatchResult(False)


def match_waiting_condition(text: str, condition_keys: list[str]) -> MatchResult:
    """Map a diagnosis string onto one of the policy's waiting-period keys."""
    if not text:
        return MatchResult(False)
    for key in condition_keys:
        for synonym in CONDITION_SYNONYMS.get(key, [key.replace("_", " ")]):
            if contains_phrase(text, synonym):
                return MatchResult(True, key, "keyword")
    return MatchResult(False)


def match_exclusion(text: str, exclusion_conditions: list[str]) -> MatchResult:
    """Match diagnosis/treatment/line-item text against policy exclusions."""
    if not text:
        return MatchResult(False)
    for condition in exclusion_conditions:
        if contains_phrase(text, condition):
            return MatchResult(True, condition, "exact")
        for synonym in EXCLUSION_SYNONYMS.get(condition, []):
            if contains_phrase(text, synonym):
                return MatchResult(True, condition, "keyword")
    return MatchResult(False)


def contains_any(text: str, keywords: list[str]) -> str | None:
    """Return the first keyword present in text (case-insensitive), if any."""
    needle = normalize(text)
    for kw in keywords:
        if normalize(kw) in needle:
            return kw
    return None
