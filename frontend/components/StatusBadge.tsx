const STYLES: Record<string, string> = {
  APPROVED: "bg-emerald-100 text-emerald-800",
  PARTIAL: "bg-amber-100 text-amber-800",
  REJECTED: "bg-red-100 text-red-700",
  MANUAL_REVIEW: "bg-blue-100 text-blue-800",
  DOCUMENTS_NEEDED: "bg-slate-200 text-slate-700",
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
        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
          STYLES[status] ?? "bg-slate-200 text-slate-700"
        }`}
      >
        {status.replaceAll("_", " ")}
      </span>
      {degraded && (
        <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-orange-700">
          DEGRADED
        </span>
      )}
    </span>
  );
}
