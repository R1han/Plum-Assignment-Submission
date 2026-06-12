"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getPolicy,
  submitClaimJson,
  submitClaimUpload,
  type PolicySummary,
} from "@/lib/api";
import { SAMPLES } from "@/lib/samples";

export default function SubmitPage() {
  const router = useRouter();
  const [policy, setPolicy] = useState<PolicySummary | null>(null);
  const [mode, setMode] = useState<"upload" | "sample">("upload");
  const [memberId, setMemberId] = useState("EMP001");
  const [category, setCategory] = useState("CONSULTATION");
  const [treatmentDate, setTreatmentDate] = useState("");
  const [amount, setAmount] = useState("");
  const [hospital, setHospital] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [sample, setSample] = useState("clean");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPolicy().then(setPolicy).catch((e) => setError(String(e)));
  }, []);

  const requirement = policy?.document_requirements[category];

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let outcome;
      if (mode === "sample") {
        outcome = await submitClaimJson(SAMPLES[sample].payload);
      } else {
        if (!files || files.length === 0)
          throw new Error("Attach at least one document.");
        const form = new FormData();
        form.set("member_id", memberId);
        form.set("policy_id", policy?.policy_id ?? "PLUM_GHI_2024");
        form.set("claim_category", category);
        form.set("treatment_date", treatmentDate);
        form.set("claimed_amount", amount);
        if (hospital) form.set("hospital_name", hospital);
        Array.from(files).forEach((f) => form.append("files", f));
        outcome = await submitClaimUpload(form);
      }
      router.push(`/claims/${outcome.claim_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold">Submit a claim</h1>
      <p className="mt-1 text-sm text-slate-500">
        {policy
          ? `${policy.policy_name} · ${policy.insurer}`
          : "Loading policy…"}
      </p>

      <div className="mt-6 flex gap-2 rounded-lg bg-slate-100 p-1 text-sm font-medium">
        {(["upload", "sample"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex-1 rounded-md px-3 py-2 transition ${
              mode === m ? "bg-white shadow text-violet-700" : "text-slate-500"
            }`}
          >
            {m === "upload" ? "Upload documents" : "Sample claims (demo)"}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="mt-6 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {mode === "sample" ? (
          <label className="block">
            <span className="text-sm font-medium">Scenario</span>
            <select
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 p-2"
            >
              {Object.entries(SAMPLES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-slate-500">
              Pre-structured submissions that exercise the pipeline without
              document images — including the early document-stop and the
              graceful-degradation paths.
            </p>
          </label>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-sm font-medium">Member</span>
                <select
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 p-2"
                >
                  {(policy?.members ?? [])
                    .filter((m) => m.relationship === "SELF")
                    .map((m) => (
                      <option key={m.member_id} value={m.member_id}>
                        {m.member_id} — {m.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="block">
                <span className="text-sm font-medium">Treatment type</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 p-2"
                >
                  {Object.keys(policy?.document_requirements ?? {}).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-sm font-medium">Treatment date</span>
                <input
                  type="date"
                  required
                  value={treatmentDate}
                  onChange={(e) => setTreatmentDate(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 p-2"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium">Claimed amount (₹)</span>
                <input
                  type="number"
                  required
                  min={1}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 p-2"
                />
              </label>
            </div>
            <label className="block">
              <span className="text-sm font-medium">
                Hospital / clinic <span className="text-slate-400">(optional)</span>
              </span>
              <input
                value={hospital}
                onChange={(e) => setHospital(e.target.value)}
                placeholder="e.g. Apollo Hospitals"
                className="mt-1 w-full rounded-md border border-slate-300 p-2"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium">Documents</span>
              {requirement && (
                <p className="mt-1 text-xs text-slate-500">
                  Required: {requirement.required.join(", ").replaceAll("_", " ")}
                </p>
              )}
              <input
                type="file"
                multiple
                accept="image/*,.pdf"
                onChange={(e) => setFiles(e.target.files)}
                className="mt-2 w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-violet-50 file:px-3 file:py-2 file:font-medium file:text-violet-700"
              />
            </label>
          </>
        )}

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
        )}

        <button
          disabled={busy}
          className="w-full rounded-lg bg-violet-600 py-3 font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
        >
          {busy ? "Processing claim…" : "Submit claim"}
        </button>
        {busy && mode === "upload" && (
          <p className="text-center text-xs text-slate-500">
            Reading your documents with vision AI — this can take ~30 seconds.
          </p>
        )}
      </form>
    </div>
  );
}
