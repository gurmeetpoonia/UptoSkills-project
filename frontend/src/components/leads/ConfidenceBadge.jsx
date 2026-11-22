// How sure we are that a lead is reachable. Comes from the scraper (CONFIDENCE) and is never invented here.
import React from "react";

const LEVELS = {
  high: { text: "High", cls: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300", dot: "bg-emerald-500" },
  medium: { text: "Medium", cls: "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300", dot: "bg-amber-500" },
  low: { text: "Phone only", cls: "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300", dot: "bg-sky-500" },
  none: { text: "Not usable", cls: "border-slate-300 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300", dot: "bg-slate-400" },
};

export default function ConfidenceBadge({ level, reason }) {
  const l = LEVELS[level] || LEVELS.none;
  return (
    <span title={reason || ""} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${l.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${l.dot}`} />
      {l.text}
    </span>
  );
}
