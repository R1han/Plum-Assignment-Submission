"use client";

import { useState } from "react";
import type { TraceStep } from "@/lib/api";

const ICONS: Record<TraceStep["status"], { glyph: string; cls: string }> = {
  PASS: { glyph: "✓", cls: "bg-emerald-100 text-emerald-700" },
  FAIL: { glyph: "✕", cls: "bg-red-100 text-red-700" },
  ERROR: { glyph: "!", cls: "bg-orange-100 text-orange-700" },
  SKIPPED: { glyph: "–", cls: "bg-slate-100 text-slate-400" },
  INFO: { glyph: "i", cls: "bg-blue-100 text-blue-700" },
};

export function TraceTimeline({ trace }: { trace: TraceStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <ol className="relative space-y-0">
      {trace.map((step, i) => {
        const icon = ICONS[step.status];
        const hasData = step.data && Object.keys(step.data).length > 0;
        return (
          <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
            {i < trace.length - 1 && (
              <span className="absolute left-[11px] top-7 h-full w-px bg-slate-200" />
            )}
            <span
              className={`z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${icon.cls}`}
            >
              {icon.glyph}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {step.component}
                </span>
                <span className="text-sm font-medium">{step.check}</span>
              </div>
              <p className="mt-0.5 text-sm text-slate-600">{step.detail}</p>
              {hasData && (
                <button
                  onClick={() => setOpen(open === i ? null : i)}
                  className="mt-1 text-xs font-medium text-violet-600 hover:underline"
                >
                  {open === i ? "Hide data" : "Show data"}
                </button>
              )}
              {open === i && hasData && (
                <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                  {JSON.stringify(step.data, null, 2)}
                </pre>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
