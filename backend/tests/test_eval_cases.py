"""The 12 official test cases, as a regression suite."""

import pytest

from evals.harness import run_all

_results = None


def results():
    global _results
    if _results is None:
        _results = {r.case_id: r for r in run_all()}
    return _results


@pytest.mark.parametrize("case_id", [f"TC{i:03d}" for i in range(1, 13)])
def test_official_case(case_id):
    r = results()[case_id]
    assert r.error is None, f"pipeline crashed: {r.error}"
    failed = [f"{c.name}: {c.detail}" for c in r.checks if not c.passed]
    assert not failed, f"{r.case_name} failed checks: {failed}"
