"""Policy loading.

Input:  path to a policy_terms.json file (defaults to settings.policy_file).
Output: a validated ``Policy`` object.
Errors: FileNotFoundError if the file is missing,
        pydantic.ValidationError if the file does not match the schema.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.models.policy import Policy


def load_policy(path: Path | None = None) -> Policy:
    policy_path = path or get_settings().policy_file
    with open(policy_path, encoding="utf-8") as f:
        raw = json.load(f)
    return Policy.model_validate(raw)


@lru_cache
def get_policy() -> Policy:
    """Cached default policy for request handling."""
    return load_policy()
