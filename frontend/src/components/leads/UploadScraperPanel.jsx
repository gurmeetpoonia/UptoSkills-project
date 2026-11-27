// "Upload Excel / Run Scraper": upload a lead file, run the scraper pipeline through the backend,
// show live progress and the qualified / rejected results. Every number comes from the server.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, X, Play, FileSpreadsheet, CheckCircle2, XCircle, Copy, Phone, AlertTriangle, Download, Users } from "lucide-react";
import { leadService } from "@/services";
import { UptoButton as Button } from "@/components/UI/UptoHooks";
import FollowUpBanner from "@/components/leads/FollowUpBanner";
import ConfidenceBadge from "@/components/leads/ConfidenceBadge";
import { downloadCsv } from "@/utils/csvDownload";

const POLL_MS = 1500;
const MAX_WAIT_MS = 5 * 60 * 1000;
const MAX_BYTES = 5 * 1024 * 1024;
const EXT = /\.(xlsx|xls|csv)$/i;
const PAGE = 100;

const TABS = [
  { key: "qualified", label: "Qualified", icon: CheckCircle2 },
  { key: "rejected", label: "Rejected", icon: XCircle },
  { key: "duplicate", label: "Duplicates", icon: Copy },
  { key: "phone_only", label: "Phone only", icon: Phone },
];

const STATUS_TEXT = {
  idle: "Choose a file to start",
  uploading: "Uploading file to the scraper…",
  queued: "Queued…",
  processing: "Validating and scoring leads…",
  done: "Finished",
  error: "Failed",
};

export default function UploadScraperPanel({ darkMode, onClose, onSaved }) {
  const [file, setFile] = useState(null);
  const [selected, setSelected] = useState([]); // excel row numbers ticked in the Qualified table
  const [savedRows, setSavedRows] = useState([]);
  const [phase, setPhase] = useState("idle"); // idle | uploading | queued | processing | done | error
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [tab, setTab] = useState("qualified");
  const [shown, setShown] = useState(PAGE);
  const timer = useRef(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
    };
  }, []);

  const card = darkMode ? "bg-slate-900 border-slate-800" : "bg-white border-slate-100";
  const heading = darkMode ? "text-white" : "text-slate-900";
  const subtext = darkMode ? "text-slate-400" : "text-slate-500";
  const tile = darkMode ? "bg-slate-800 border-slate-700" : "bg-slate-50 border-slate-200";
  const divider = darkMode ? "border-slate-800" : "border-slate-200";

  const pick = (f) => {
    setError("");
    if (!f) return;
    if (!EXT.test(f.name)) return setError("Unsupported file type. Upload a .xlsx, .xls or .csv file.");
    if (!f.size) return setError("The file is empty.");
    if (f.size > MAX_BYTES) return setError("The file is larger than 5 MB.");
    setFile(f);
    setJob(null);
    setSaved(null);
    setPhase("idle");
  };

  const fail = (msg) => {
    setError(msg);
    setPhase("error");
  };

  const save = async (jobId, rowNumbers) => {
    setSaving(true);
    try {
      const r = await leadService.ingestSave(jobId, rowNumbers);
      if (!alive.current) return;
      setSavedRows(r.savedRows || []);
      setSelected([]);
      setSaved((prev) => ({
        created: (prev?.created || 0) + r.created,
        skipped: [...(prev?.skipped || []), ...(r.skipped || [])],
        failed: [...(prev?.failed || []), ...(r.failed || [])],
      }));
      if (r.created) toast.success(`${r.created} lead${r.created === 1 ? "" : "s"} added to My Leads`);
      else toast.info("No new leads were added");
      onSaved?.();
    } catch (err) {
      toast.error(err.message || "Could not save the leads");
    } finally {
      if (alive.current) setSaving(false);
    }
  };

  const poll = (jobId, startedAt, failures = 0) => {
    timer.current = setTimeout(async () => {
      if (!alive.current) return;
      if (Date.now() - startedAt > MAX_WAIT_MS) return fail("Processing is taking too long. Try a smaller file.");
      try {
        const s = await leadService.ingestStatus(jobId);
        if (!alive.current) return;
        setJob(s);
        if (s.status === "error") return fail(s.error || "Processing failed");
        if (s.status === "done") {
          setPhase("done");
          setTab(s.summary?.qualified ? "qualified" : s.summary?.rejected ? "rejected" : s.summary?.duplicates ? "duplicate" : "phone_only");
          setSavedRows(s.savedRows || []);
          return;
        }
        setPhase(s.status === "queued" ? "queued" : "processing");
        poll(jobId, startedAt, 0);
      } catch (err) {
        if (!alive.current) return;
        // The job is gone or the scraper is down: stop. Network blips are retried a few times.
        // unwrap() only keeps the message, so recognise the server's "stop" errors by text.
        if (/scraper|not found|restarted/i.test(err.message || "") || failures >= 3)
          return fail(err.message || "Lost connection to the server");
        poll(jobId, startedAt, failures + 1);
      }
    }, POLL_MS);
  };

  const run = async () => {
    if (!file) return setError("Choose a file first.");
    setError("");
    setSaved(null);
    setSavedRows([]);
    setSelected([]);
    setJob(null);
    setPhase("uploading");
    try {
      const { jobId } = await leadService.ingestStart(file);
      if (!alive.current) return;
      setPhase("queued");
      poll(jobId, Date.now());
    } catch (err) {
      fail(err.message || "Upload failed");
    }
  };

  const busy = ["uploading", "queued", "processing"].includes(phase);
  const sum = job?.summary;
  const pct = job?.total ? Math.min(100, Math.round((job.processed / job.total) * 100)) : phase === "uploading" ? 5 : 0;
  const rows = (job?.rows || []).filter((r) => r.status === tab);
  const addable = (job?.rows || []).filter((r) => r.status === "qualified" && !savedRows.includes(r.row));
  const toggleRow = (n) => setSelected((cur) => (cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n]));
  const toggleAll = () => setSelected((cur) => (cur.length === addable.length ? [] : addable.map((r) => r.row)));
  const countFor = { qualified: sum?.qualified, rejected: sum?.rejected, duplicate: sum?.duplicates, phone_only: sum?.phone_only };

  const Card = ({ label, value, tone, icon: Icon }) => (
    <div className={`flex items-center gap-3 rounded-xl border p-3 ${tile}`}>
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <p className={`text-xl font-semibold leading-none ${heading}`}>{value ?? "–"}</p>
        <p className={`mt-1 text-xs ${subtext}`}>{label}</p>
      </div>
    </div>
  );

  const phoneRows = (job?.rows || []).filter((r) => r.status === "phone_only");
  const downloadPhone = () =>
    downloadCsv("phone-only-followup-leads.csv", ["Name", "Company", "Job Title", "Phone", "Row"],
      phoneRows.map((r) => [r.name, r.company, r.title, r.phone, r.row]));
  const downloadRejected = () =>
    downloadCsv("rejected-rows.csv", ["Row", "Name", "Email", "Phone", "Company", "Reason"],
      (job?.rows || []).filter((r) => r.status === "rejected").map((r) => [r.row, r.name, r.email, r.phone, r.company, (r.reasons || []).join("; ")]));
  const th = `py-2.5 px-3 text-left text-[11px] font-semibold uppercase tracking-wide ${subtext}`;

  return (
    <section>
      <div className={`rounded-2xl p-6 border ${card}`}>
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className={`text-base font-semibold ${heading}`}>Upload CSV / Excel</h3>
            <p className={`text-sm mt-1 ${subtext}`}>
              Upload a .csv, .xlsx or .xls file. Needs an <code>Email</code> or <code>Phone</code> column; <code>Name</code>,{" "}
              <code>Company</code>, <code>Job Title</code> are optional. The scraper validates and scores every row. Review the list, then add the leads you want to My Leads.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className={subtext}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <label
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy) pick(e.dataTransfer.files?.[0]);
            }}
            className={`flex items-center gap-3 rounded-xl border-2 border-dashed p-4 cursor-pointer ${darkMode ? "border-slate-700" : "border-slate-300"} ${busy ? "opacity-60 pointer-events-none" : ""}`}
          >
            <FileSpreadsheet className="h-6 w-6 text-[#00b5ad] shrink-0" />
            <span className={`text-sm truncate ${file ? heading : subtext}`}>
              {file ? `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)` : "Click to choose a file or drop it here"}
            </span>
            <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = null; }} />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={run} disabled={!file || busy}>
              <Play className="h-4 w-4" /> {busy ? "Running…" : "Run Scraper"}
            </Button>
          </div>
        </div>

        {error && (
          <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 text-red-700 p-3 text-sm">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> <span>{error}</span>
          </div>
        )}

        {(busy || job) && phase !== "idle" && (
          <div className="mt-5">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className={heading}>{STATUS_TEXT[phase]}</span>
              {job?.total > 0 && (
                <span className={subtext}>
                  {job.processed} / {job.total} records
                </span>
              )}
            </div>
            <div className={`h-2 rounded-full overflow-hidden ${darkMode ? "bg-slate-800" : "bg-slate-200"}`}>
              <div className="h-full bg-[#00b5ad] transition-all" style={{ width: `${phase === "done" ? 100 : pct}%` }} />
            </div>
          </div>
        )}

        {sum && (
          <div className="mt-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card icon={Users} label="Total records" value={sum.total} tone="bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-200" />
              <Card icon={CheckCircle2} label="Qualified" value={sum.qualified} tone="bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300" />
              <Card icon={XCircle} label="Rejected" value={sum.rejected} tone="bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-300" />
              <Card icon={Copy} label="Duplicates" value={sum.duplicates} tone="bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300" />
            </div>
            <p className={`text-xs mt-2 ${subtext}`}>
              Invalid emails: {sum.invalid_email} · Invalid phone numbers: {sum.invalid_phone} · Phone-only follow-ups: {sum.phone_only}
              {sum.failed ? ` · Processing failures: ${sum.failed}` : ""}
            </p>

            {job.warnings?.map((w) => (
              <p key={w} className="text-xs mt-1 text-amber-600">⚠ {w}</p>
            ))}

            {saved && (
              <p className={`text-sm mt-3 ${heading}`}>
                Added to My Leads: <b>{saved.created}</b> added
                {saved.skipped?.length ? `, ${saved.skipped.length} skipped (already in the CRM)` : ""}
                {saved.failed?.length ? `, ${saved.failed.length} failed` : ""}.
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2 mt-5">
              {TABS.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => { setTab(key); setShown(PAGE); }}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition ${
                    tab === key
                      ? "border-[#00b5ad] bg-[#00b5ad]/10 font-medium text-[#00b5ad]"
                      : `${divider} ${subtext} hover:border-[#00b5ad]/50`
                  }`}
                >
                  <Icon className="h-4 w-4" /> {label}
                  <span className={`rounded-full px-1.5 text-xs ${tab === key ? "bg-[#00b5ad]/20" : darkMode ? "bg-slate-800" : "bg-slate-100"}`}>{countFor[key] ?? 0}</span>
                </button>
              ))}
              {tab === "rejected" && (countFor.rejected || 0) > 0 && (
                <button type="button" onClick={downloadRejected} className={`ml-auto inline-flex items-center gap-1.5 text-xs ${subtext} hover:underline`}>
                  <Download className="h-3.5 w-3.5" /> Download rejected report
                </button>
              )}
            </div>

            {tab === "phone_only" && phoneRows.length > 0 && (
              <div className="mt-3"><FollowUpBanner darkMode={darkMode} count={phoneRows.length} onDownload={downloadPhone} /></div>
            )}

            {tab === "qualified" && addable.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                <p className={`text-xs ${subtext}`}>Tick the leads you want in My Leads.</p>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => save(job.jobId, selected)} disabled={saving || selected.length === 0}>
                    {saving ? "Adding…" : `Add selected (${selected.length})`}
                  </Button>
                  <Button onClick={() => save(job.jobId)} disabled={saving}>
                    {saving ? "Adding…" : `Add all ${addable.length}`}
                  </Button>
                </div>
              </div>
            )}

            {rows.length === 0 ? (
              <p className={`text-sm py-6 text-center ${subtext}`}>No rows in this group.</p>
            ) : (
              <>
              <div className={`mt-3 overflow-auto rounded-xl border max-h-[28rem] ${divider}`}>
                <table className="w-full text-sm">
                  <thead className={`sticky top-0 z-10 ${darkMode ? "bg-slate-900" : "bg-slate-50"}`}>
                    <tr>
                      {tab === "qualified" && (
                        <th className={`${th} w-8`}>
                          <input type="checkbox" aria-label="Select all" checked={addable.length > 0 && selected.length === addable.length} onChange={toggleAll} />
                        </th>
                      )}
                      <th className={th}>Row</th>
                      <th className={th}>Lead</th>
                      <th className={th}>Contact</th>
                      {tab === "qualified" ? (
                        <>
                          <th className={th}>Score</th>
                          <th className={th}>Confidence</th>
                        </>
                      ) : (
                        <th className={th}>Why</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, shown).map((r) => (
                      <tr key={r.row} className={`border-t align-top ${divider} ${heading} ${darkMode ? "hover:bg-slate-800/50" : "hover:bg-slate-50"}`}>
                        {tab === "qualified" && (
                          <td className="py-2.5 px-3">
                            {savedRows.includes(r.row) ? (
                              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-600">Added</span>
                            ) : (
                              <input type="checkbox" aria-label={`Select row ${r.row}`} checked={selected.includes(r.row)} onChange={() => toggleRow(r.row)} />
                            )}
                          </td>
                        )}
                        <td className={`py-2.5 px-3 ${subtext}`}>{r.row}</td>
                        <td className="py-2.5 px-3">
                          <p className="font-medium">{r.name || "–"}</p>
                          <p className={`text-xs ${subtext}`}>{[r.company, r.title].filter(Boolean).join(" · ") || "–"}</p>
                        </td>
                        <td className="py-2.5 px-3">
                          <p className="break-all">{r.email || <span className={subtext}>No email</span>}</p>
                          <p className={`text-xs ${subtext}`}>{r.phone || "No phone"}</p>
                        </td>
                        {tab === "qualified" ? (
                          <>
                            <td className="py-2.5 px-3">
                              <span className={`inline-flex min-w-[2rem] justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${r.score >= 70 ? "bg-emerald-50 text-emerald-700" : r.score >= 40 ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600"}`}>{r.score}</span>
                            </td>
                            <td className="py-2.5 px-3">
                              <ConfidenceBadge level={r.confidence} reason={r.confidence_reason} />
                              <p className={`mt-1 text-xs ${subtext}`}>{r.email_status}</p>
                            </td>
                          </>
                        ) : (
                          <td className="py-2.5 px-3">
                            <div className="flex flex-wrap gap-1">
                              {(r.reasons || []).map((x) => (
                                <span key={x} className={`rounded-full border px-2 py-0.5 text-xs ${darkMode ? "border-slate-700 text-slate-300" : "border-slate-200 bg-slate-50 text-slate-600"}`}>{x}</span>
                              ))}
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
                {rows.length > shown && (
                  <div className="text-center py-3">
                    <Button variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
                      Show more ({rows.length - shown} left)
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
