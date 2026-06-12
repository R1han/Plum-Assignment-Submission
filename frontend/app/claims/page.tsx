"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listClaims, type ClaimListItem } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function ClaimsPage() {
  const [claims, setClaims] = useState<ClaimListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listClaims().then(setClaims).catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Decisions
      </h1>
      <p className="mt-1.5 text-sm text-slate-500">
        Every processed claim with its decision and full trace.
      </p>
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      {claims && claims.length === 0 && (
        <p className="mt-8 text-slate-500">
          No claims yet — <Link href="/" className="text-violet-600 underline">submit one</Link>.
        </p>
      )}
      {claims && claims.length > 0 && (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Claim</th>
                <th className="px-4 py-3">Member</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Claimed</th>
                <th className="px-4 py-3">Approved</th>
                <th className="px-4 py-3">Outcome</th>
                <th className="px-4 py-3">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.claim_id} className="border-t border-slate-100 transition hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs">
                    <Link href={`/claims/${c.claim_id}`} className="font-medium text-violet-600 hover:text-violet-800 hover:underline">
                      {c.claim_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{c.member_id}</td>
                  <td className="px-4 py-3">{c.claim_category}</td>
                  <td className="px-4 py-3">₹{c.claimed_amount.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3">
                    {c.status ? `₹${c.approved_amount.toLocaleString("en-IN")}` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status ?? "DOCUMENTS_NEEDED"} degraded={c.degraded} />
                  </td>
                  <td className="px-4 py-3">
                    {c.confidence_score != null ? c.confidence_score.toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
