"""Generate the eval report: python -m evals.run_evals [output_path]"""

from __future__ import annotations

import sys
from pathlib import Path

from evals.harness import CaseResult, run_all


def _trace_table(outcome) -> str:
    rows = ["| # | Component | Check | Status | Detail |",
            "|---|-----------|-------|--------|--------|"]
    for i, s in enumerate(outcome.trace, 1):
        detail = s.detail.replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {i} | {s.component} | {s.check} | {s.status.value} | {detail} |")
    return "\n".join(rows)


def _decision_block(outcome) -> str:
    if outcome.decision is None:
        issues = "\n".join(
            f"- **{i.code.value}**{f' ({i.file_id})' if i.file_id else ''}: {i.message}"
            for i in outcome.document_issues
        )
        return f"**No decision — stopped early with document issues:**\n\n{issues}"
    d = outcome.decision
    lines = [
        f"- **Status:** {d.status.value}",
        f"- **Approved amount:** ₹{d.approved_amount:g}",
        f"- **Confidence:** {d.confidence_score}",
        f"- **Member message:** {d.member_message}",
    ]
    if d.rejection_reasons:
        lines.append(f"- **Rejection reasons:** {', '.join(r.value for r in d.rejection_reasons)}")
    if d.line_items:
        lines.append("- **Line items:**")
        for v in d.line_items:
            lines.append(f"  - {v.description} (₹{v.amount:g}): "
                         f"{'covered' if v.covered else 'NOT covered'} — {v.reason}")
    if d.financial:
        lines.append(f"- **Financial:** claimed ₹{d.financial.claimed_amount:g} → "
                     f"covered ₹{d.financial.covered_amount:g} → discount "
                     f"₹{d.financial.network_discount_amount:g} → co-pay "
                     f"₹{d.financial.copay_amount:g} → payable "
                     f"₹{d.financial.payable_amount:g}")
    if d.fraud_signals:
        lines.append("- **Fraud signals:** " + " | ".join(d.fraud_signals))
    if outcome.component_failures:
        lines.append("- **Component failures:** " + "; ".join(
            f"{f.component} ({f.error})" for f in outcome.component_failures))
    return "\n".join(lines)


def render(results: list[CaseResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    out = [
        "# Eval Report — 12 Official Test Cases",
        "",
        f"**Result: {passed}/{len(results)} cases match the expected outcome.**",
        "",
        "Pipeline configuration: deterministic classifier tier only (no LLM "
        "calls), so this report is exactly reproducible: "
        "`python -m evals.run_evals`. The LLM fallback tier engages only on "
        "fuzzy text the keyword tier cannot resolve, which none of the "
        "official fixtures require.",
        "",
        "| Case | Name | Expected | Got | Match |",
        "|------|------|----------|-----|-------|",
    ]
    for r in results:
        if r.error:
            out.append(f"| {r.case_id} | {r.case_name} | — | CRASH: {r.error} | ❌ |")
            continue
        d = r.outcome.decision
        got = d.status.value if d else "stopped early (document issue)"
        if d and d.approved_amount:
            got += f", ₹{d.approved_amount:g}"
        expected = "no decision (stop early)"
        for c in r.checks:
            if c.name.startswith("decision =="):
                expected = c.name.removeprefix("decision == ")
        out.append(f"| {r.case_id} | {r.case_name} | {expected} | {got} | "
                   f"{'✅' if r.passed else '❌'} |")

    for r in results:
        out += ["", "---", "", f"## {r.case_id} — {r.case_name}", ""]
        if r.error:
            out.append(f"**PIPELINE CRASH:** `{r.error}`")
            continue
        out.append(_decision_block(r.outcome))
        out += ["", "**Expectation checks:**", ""]
        for c in r.checks:
            out.append(f"- {'✅' if c.passed else '❌'} {c.name} — {c.detail}")
        out += ["", "**Full trace:**", "", _trace_table(r.outcome)]
    return "\n".join(out) + "\n"


def main():
    results = run_all()
    report = render(results)
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parent / "report.md"
    out_path.write_text(report, encoding="utf-8")
    passed = sum(1 for r in results if r.passed)
    print(f"{passed}/{len(results)} cases passed. Report: {out_path}")
    for r in results:
        marker = "PASS" if r.passed else "FAIL"
        print(f"  [{marker}] {r.case_id} {r.case_name}")
        if not r.passed:
            for c in r.checks:
                if not c.passed:
                    print(f"        ✗ {c.name}: {c.detail}")
            if r.error:
                print(f"        ✗ {r.error}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
