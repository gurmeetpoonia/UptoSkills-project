// Client-side CSV download (no server round trip). Cells are quoted and formula-injection safe.
const esc = (v) => {
  let s = String(v ?? "");
  if (/^[=+\-@]/.test(s) && !/^\+?\d[\d\s-]*$/.test(s)) s = "'" + s; // keep phone numbers, defuse formulas
  return `"${s.replace(/"/g, '""')}"`;
};

export function downloadCsv(filename, header, rows) {
  const body = [header, ...rows].map((r) => r.map(esc).join(",")).join("\n");
  const blob = new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
