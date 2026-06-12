"""LLM-backed fuzzy classification — tier two of the matching strategy.

Tier one (app/engine/matching.py) is deterministic keyword matching; this
class adds Claude (Opus) as a fallback for text the keywords cannot resolve,
e.g. a line item reading "Smile corrections and brightening session" that a
human would recognize as cosmetic dentistry.

Input:  free text + the relevant policy lists.
Output: matching.MatchResult with certainty="llm" when the model resolves it.
Errors: LLM failures NEVER propagate — the classifier degrades to "no match"
        and records the failure, so adjudication continues deterministically.
"""

from __future__ import annotations

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.engine.matching import MatchResult
from app.engine.rules import Classifier
from app.models.policy import Policy


class _ListMatch(BaseModel):
    matched: bool = Field(description="True only if the text clearly falls under one of the listed entries.")
    entry: str | None = Field(default=None, description="The exact list entry it falls under, verbatim, or null.")
    reasoning: str = Field(description="One sentence explaining the call.")


class _ProcedureVerdict(BaseModel):
    verdict: str = Field(description="'covered', 'excluded', or 'unknown'")
    entry: str | None = Field(default=None, description="The exact list entry matched, verbatim, or null.")
    reasoning: str = Field(description="One sentence explaining the call.")


class LLMClassifier(Classifier):
    COMPONENT = "llm_classifier"

    def __init__(self, client: Anthropic | None = None):
        settings = get_settings()
        self.enabled = bool(settings.anthropic_api_key) and not settings.offline_mode
        self.model = settings.adjudication_model
        self.client = client or (
            Anthropic(api_key=settings.anthropic_api_key) if self.enabled else None
        )
        self.failures: list[str] = []
        self._cache: dict[tuple, MatchResult | tuple] = {}

    def exclusion_fallback(self, text: str, policy: Policy) -> MatchResult:
        return self._match_against(
            text, policy.exclusions.conditions,
            "policy exclusions (conditions and treatments NOT covered)",
        )

    def condition_fallback(self, text: str, policy: Policy) -> MatchResult:
        keys = list(policy.waiting_periods.specific_conditions.keys())
        return self._match_against(
            text, keys,
            "medical conditions subject to waiting periods (keys are "
            "condition identifiers, e.g. 'diabetes')",
        )

    def procedure_fallback(self, text, covered, excluded):
        if not self.enabled or not (covered or excluded):
            return "unknown", MatchResult(False)
        key = ("procedure", text, tuple(covered), tuple(excluded))
        if key in self._cache:
            return self._cache[key]
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        "You are classifying a medical bill line item for an "
                        "insurance claim.\n"
                        f"Line item: '{text}'\n"
                        f"COVERED procedures: {covered}\n"
                        f"EXCLUDED procedures: {excluded}\n"
                        "Decide whether this line item is one of the covered "
                        "procedures, one of the excluded procedures (including "
                        "obvious synonyms/rephrasings), or unknown."
                    ),
                }],
                output_format=_ProcedureVerdict,
            )
            parsed = response.parsed_output
            if parsed is None or parsed.verdict not in ("covered", "excluded"):
                result = ("unknown", MatchResult(False))
            else:
                result = (parsed.verdict, MatchResult(True, parsed.entry, "llm"))
            self._cache[key] = result
            return result
        except Exception as e:  
            self.failures.append(f"procedure classification failed: {e}")
            return "unknown", MatchResult(False)

    def _match_against(self, text: str, entries: list[str], list_label: str) -> MatchResult:
        if not self.enabled or not text:
            return MatchResult(False)
        key = ("list", text, tuple(entries), list_label)
        if key in self._cache:
            return self._cache[key]
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        "You are mapping medical text onto an insurance "
                        f"policy list: {list_label}.\n"
                        f"Text: '{text}'\n"
                        f"List entries: {entries}\n"
                        "Does the text clearly fall under one of these "
                        "entries? Match synonyms and clinical shorthand, but "
                        "do NOT stretch — when in doubt, matched=false."
                    ),
                }],
                output_format=_ListMatch,
            )
            parsed = response.parsed_output
            if parsed is None or not parsed.matched or parsed.entry not in entries:
                result = MatchResult(False)
            else:
                result = MatchResult(True, parsed.entry, "llm")
            self._cache[key] = result
            return result
        except Exception as e: 
            self.failures.append(f"list classification failed: {e}")
            return MatchResult(False)
