"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getClaim, type ClaimOutcome } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { TraceTimeline } from "@/components/TraceTimeline";

export default function ClaimDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [outcome, setOutcome] = useState<ClaimOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getClaim(id)
      .then((r) => setOutcome(r.outcome))
      .catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!outcome) return <p className="text-sm text-slate-500">Loading…</p>;

  const d = outcome.decision;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/claims"
            className="text-sm font-medium text-violet-600 hover:text-violet-800 hover:underline"
          >
            ← All decisions
          </Link>
          <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight text-slate-900">
            {outcome.claim_id}
          </h1>
        </div>
        <StatusBadge
          status={d ? d.status : "DOCUMENTS_NEEDED"}
          degraded={outcome.degraded}
        />
      </div>

      {/* Document issues (stopped early) */}
      {outcome.outcome_type === "DOCUMENT_ISSUE" && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <h2 className="font-semibold text-amber-900">
            Action needed — your claim was not processed
          </h2>
          <ul className="mt-3 space-y-3">
            {outcome.document_issues.map((issue, i) => (
              <li key={i} className="rounded-lg bg-white p-4 text-sm shadow-sm">
                <span className="mr-2 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-800">
                  {issue.code}
                </span>
                {issue.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Rejected / manual-review callout — surface the reason prominently */}
      {d && (d.status === "REJECTED" || d.status === "MANUAL_REVIEW") && (
        <section
          className={`rounded-2xl border p-5 ${
            d.status === "REJECTED"
              ? "border-red-200 bg-red-50"
              : "border-orange-200 bg-orange-50"
          }`}
        >
          <h2
            className={`font-semibold ${
              d.status === "REJECTED" ? "text-red-900" : "text-orange-900"
            }`}
          >
            {d.status === "REJECTED"
              ? "Claim not approved"
              : "Sent for manual review"}
          </h2>
          <p
            className={`mt-2 text-sm ${
              d.status === "REJECTED" ? "text-red-800" : "text-orange-800"
            }`}
          >
            {d.member_message}
          </p>
          {d.rejection_reasons.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {d.rejection_reasons.map((r, i) => (
                <span
                  key={i}
                  className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                    d.status === "REJECTED"
                      ? "bg-red-100 text-red-800"
                      : "bg-orange-100 text-orange-800"
                  }`}
                >
                  {r}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Decision summary */}
      {d && (
        <section className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-400">Approved amount</p>
            <p className="mt-1 text-2xl font-semibold">
              ₹{d.approved_amount.toLocaleString("en-IN")}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-400">Confidence</p>
            <p className="mt-1 text-2xl font-semibold">{d.confidence_score.toFixed(2)}</p>
            {d.manual_review_recommended && (
              <p className="mt-1 text-xs font-medium text-orange-600">
                Manual review recommended
              </p>
            )}
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-400">Member message</p>
            <p className="mt-1 text-sm text-slate-700">{d.member_message}</p>
          </div>
        </section>
      )}

      {/* Component failures */}
      {outcome.component_failures.length > 0 && (
        <section className="rounded-2xl border border-orange-200 bg-orange-50 p-5">
          <h2 className="text-sm font-semibold text-orange-900">
            Degraded processing — component failures
          </h2>
          <ul className="mt-2 space-y-1 text-sm text-orange-800">
            {outcome.component_failures.map((f, i) => (
              <li key={i}>
                <strong>{f.component}</strong>: {f.error} <em>({f.impact})</em>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Financial breakdown */}
      {d?.financial && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold">Financial breakdown</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-5">
            <Item label="Claimed" value={d.financial.claimed_amount} />
            <Item label="Covered" value={d.financial.covered_amount} />
            <Item
              label={`Network discount (${d.financial.network_discount_percent}%)`}
              value={-d.financial.network_discount_amount}
            />
            <Item
              label={`Co-pay (${d.financial.copay_percent}%)`}
              value={-d.financial.copay_amount}
            />
            <Item label="Payable" value={d.financial.payable_amount} bold />
          </dl>
          {d.financial.notes.length > 0 && (
            <ul className="mt-3 list-inside list-disc text-xs text-slate-500">
              {d.financial.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Line items */}
      {d && d.line_items.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold">Line items</h2>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="py-1">Item</th>
                <th className="py-1">Amount</th>
                <th className="py-1">Verdict</th>
                <th className="py-1">Reason</th>
              </tr>
            </thead>
            <tbody>
              {d.line_items.map((v, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-2">{v.description}</td>
                  <td className="py-2">₹{v.amount.toLocaleString("en-IN")}</td>
                  <td className="py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        v.covered
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {v.covered ? "covered" : "not covered"}
                    </span>
                  </td>
                  <td className="py-2 text-slate-500">{v.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Fraud signals */}
      {d && d.fraud_signals.length > 0 && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
          <h2 className="text-sm font-semibold text-blue-900">Fraud signals</h2>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-blue-800">
            {d.fraud_signals.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Reasons */}
      {d && d.reasons.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold">Decision reasons</h2>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-600">
            {d.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Full trace */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="font-semibold">
          Processing trace
          <span className="ml-2 text-xs font-normal text-slate-400">
            every check the system ran, in order
          </span>
        </h2>
        <div className="mt-4">
          <TraceTimeline trace={outcome.trace} />
        </div>
      </section>
    </div>
  );
}

function Item({
  label,
  value,
  bold,
}: {
  label: string;
  value: number;
  bold?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className={bold ? "font-semibold" : ""}>
        ₹{value.toLocaleString("en-IN")}
      </dd>
    </div>
  );
}
