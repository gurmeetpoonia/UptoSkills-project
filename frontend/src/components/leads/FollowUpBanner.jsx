// Card shown when some leads have a valid mobile but no usable email: they stay out of the CRM
// and are offered as a follow-up call list. Used by Find Leads and the Upload CSV / Excel panel.
import React from "react";
import { Phone, Download } from "lucide-react";

export default function FollowUpBanner({ count, onDownload, darkMode, label = "Download follow-up list" }) {
  if (!count) return null;
  return (
    <div
      className={`flex flex-wrap items-center gap-4 rounded-2xl border p-4 ${
        darkMode ? "border-sky-900 bg-sky-950/30" : "border-sky-200 bg-gradient-to-r from-sky-50 to-white"
      }`}
    >
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${darkMode ? "bg-sky-900/60 text-sky-300" : "bg-sky-100 text-sky-600"}`}>
        <Phone className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${darkMode ? "text-sky-100" : "text-slate-900"}`}>
          {count} phone-only {count === 1 ? "lead" : "leads"}
        </p>
        <p className={`mt-0.5 text-xs leading-relaxed ${darkMode ? "text-sky-200/80" : "text-slate-500"}`}>
          Valid mobile, no email. Kept out of the CRM; use this list for follow-up calls.
        </p>
      </div>
      <button
        type="button"
        onClick={onDownload}
        className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition ${
          darkMode ? "border-sky-700 text-sky-200 hover:bg-sky-900/50" : "border-sky-300 bg-white text-sky-700 hover:bg-sky-50"
        }`}
      >
        <Download className="h-4 w-4" /> {label}
      </button>
    </div>
  );
}
