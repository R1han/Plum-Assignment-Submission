const STYLES: Record<string, string> = {
  APPROVED: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  PARTIAL: "bg-amber-50 text-amber-700 ring-amber-600/20",
  REJECTED: "bg-red-50 text-red-700 ring-red-600/20",
  MANUAL_REVIEW: "bg-blue-50 text-blue-700 ring-blue-600/20",
  DOCUMENTS_NEEDED: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export function StatusBadge({
  status,
  degraded,
}: {
  status: string;
  degraded?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${
          STYLES[status] ?? "bg-slate-100 text-slate-600 ring-slate-500/20"
        }`}
      >
        {status.replaceAll("_", " ")}
      </span>
      {degraded && (
        <span className="rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-semibold text-orange-700 ring-1 ring-inset ring-orange-600/20">
          DEGRADED
        </span>
      )}
    </span>
  );
}
