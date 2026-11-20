
import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { leadService, tagService, savedSearchService } from "@/services";
import { useTheme } from "@/context/ThemeContext";
import { UptoPage, SectionHeading } from "@/components/UI/UptoStyles";
import {
  UptoButton as Button,
  UptoInput as Input,
  UptoSelect as Select,
  UptoBadge as Badge,
  UptoSpinner as FullPageSpinner,
  UptoError as ErrorBanner,
  UptoEmptyState as EmptyState,
  UptoCopyButton as CopyButton,
} from "@/components/UI/UptoHooks";
import {
  Plus,
  Download,
  Upload,
  Save,
  X,
  Target,
  Filter,
  ListChecks,
  Search,
  Mail,
  Phone,
  CheckCircle2,
  XCircle,
  Users,
  BadgeCheck,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const Leads = () => {
  const { theme } = useTheme();
  const darkMode = theme === "dark";
  const { isMember } = useAuth();
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    search: "",
    status: "",
    source: "",
    tagId: "",
    sortBy: "createdAt",
    order: "desc",
  });

  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showFindLeads, setShowFindLeads] = useState(false);

  const [tags, setTags] = useState([]);
  const [selected, setSelected] = useState([]);
  const [draft, setDraft] = useState({
    name: "",
    email: "",
    companyName: "",
    status: "new",
    source: "website",
  });
  const [csv, setCsv] = useState("");
  const [savedSearches, setSavedSearches] = useState([]);

  // Find Leads states
  const [findQuery, setFindQuery] = useState("");
  const [findJobId, setFindJobId] = useState(null);
  const [findStatus, setFindStatus] = useState("idle");
  const [findResults, setFindResults] = useState([]);
  const [findNote, setFindNote] = useState("");
  const [findInCrm, setFindInCrm] = useState(0);
  const [findSelected, setFindSelected] = useState([]);
  const findFailCount = useRef(0);

  const limit = 20;

  const heading = darkMode ? "text-white" : "text-slate-900";
  const subtext = darkMode ? "text-slate-400" : "text-slate-500";
  const body = darkMode ? "text-slate-300" : "text-slate-600";
  const card = darkMode
    ? "bg-slate-900 border-slate-800"
    : "bg-white border-slate-100";
  const divider = darkMode ? "border-slate-800" : "border-slate-200";
  const inputBg = darkMode
    ? "bg-slate-800 border-slate-700 text-white"
    : "bg-white border-slate-300 text-slate-900";
  const pill = darkMode
    ? "bg-teal-900/50 text-teal-400"
    : "bg-teal-50 text-teal-700";

  const load = async (p = page, f = filters) => {
    setLoading(true);

    try {
      const params = {
        page: p,
        limit,
        ...Object.fromEntries(
          Object.entries(f).filter(
            ([_, v]) => v !== "" && v !== null
          )
        ),
      };

      const r = await leadService.list(params);

      setItems(r.items || []);
      setTotal(r.total || 0);
      setPages(r.pages || 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1, filters);
  }, []);

  useEffect(() => {
    tagService.list().then(setTags).catch(() => {});
    savedSearchService
      .list({ resource: "leads" })
      .then((r) => setSavedSearches(r || []))
      .catch(() => {});
  }, []);

  // Auto-apply filters when they change
  useEffect(() => {
    const timer = setTimeout(() => {
      load(1, filters);
    }, 300);

    return () => clearTimeout(timer);
  }, [
    filters.status,
    filters.source,
    filters.tagId,
    filters.search,
  ]);

  // Opening Find Leads shows all available leads automatically (no search needed)
  useEffect(() => {
    if (showFindLeads && findStatus === "idle" && !findJobId) {
      startFind(null, "*");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showFindLeads]);

  // Polling for Find Leads
  useEffect(() => {
    let timer;

    if (
      showFindLeads &&
      findStatus === "running" &&
      findJobId
    ) {
      timer = setInterval(async () => {
        try {
          const res = await leadService.getFindStatus(findJobId);

          if (res.status === "done") {
            setFindStatus("done");
            setFindResults(res.leads || []);
            setFindNote(res.note || "");
            setFindInCrm(res.alreadyInCrm || 0);
            clearInterval(timer);
          } else if (res.status === "error") {
            setFindStatus("error");
            toast.error(res.error || "Scraping failed");
            clearInterval(timer);
          }
        } catch (err) {
          console.error(err);
          findFailCount.current += 1;

          if (findFailCount.current >= 3) {
            setFindStatus("error");
            toast.error(
              "Lost connection while checking scrape status."
            );
            clearInterval(timer);
          }
        }
      }, 5000);
    }

    return () => clearInterval(timer);
  }, [showFindLeads, findStatus, findJobId]);

  // "*" = show every lead the scraper has (HR data), already screened by the intelligent tool
  const startFind = async (e, queryOverride) => {
    if (e && e.preventDefault) e.preventDefault();

    const q = (queryOverride ?? findQuery).trim() || "*";

    try {
      setFindStatus("running");
      setFindResults([]);
      setFindNote("");
      setFindInCrm(0);
      setFindSelected([]);
      findFailCount.current = 0;

      const res = await leadService.find(q);
      setFindJobId(res.jobId);
    } catch (err) {
      setFindStatus("error");
      toast.error(
        /internal server error|scraper|502|network/i.test(err.message || "")
          ? "Cannot reach the scraper service. Start it (uvicorn on port 8000) and press Search again."
          : err.message
      );
    }
  };

  const confirmFind = async () => {
    if (findSelected.length === 0) return;

    const selectedLeads = findResults.filter((_, idx) =>
      findSelected.includes(idx)
    );

    try {
      const res = await leadService.confirmFind(
        findJobId,
        selectedLeads
      );

      toast.success(
        `Created ${res.created.length} leads. Skipped ${res.skipped.length}.`
      );

      // Keep Find Leads open, but drop what was just added (or already existed) from the list.
      const gone = new Set(
        [
          ...res.created.map((c) => String(c.email || "").toLowerCase()),
          ...res.skipped
            .filter((x) => /already exists/i.test(x.reason || ""))
            .map((x) => findEmail(x.item || {})),
        ].filter(Boolean)
      );
      setFindResults((prev) => prev.filter((l) => !gone.has(findEmail(l))));
      setFindInCrm((n) => n + gone.size);
      setFindSelected([]);

      load(1);
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Leads with a valid mobile but no usable email: shown, not saved to the CRM
  // (the CRM needs an email), kept as a separate follow-up list.
  const isPhoneOnlyFindLead = (lead) => {
    const phone = String(lead["HR PHONE"] || "").trim();
    return (
      lead["TOOL_SELECTED"] !== false &&
      /\d{8,}/.test(phone) &&
      !canSelectFindLead(lead)
    );
  };

  const downloadPhoneFollowUp = (rows) => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const head = ["Company", "Job Title", "HR Name", "HR Phone", "Reason", "Job URL"];
    const lines = rows.map((l) =>
      [l["COMPANY"], l["JOB TITLE"], l["HR NAME"], l["HR PHONE"], l["SELECTION_REASON"], l["JOB URL"]]
        .map(esc)
        .join(",")
    );
    const blob = new Blob([[head.map(esc).join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "phone-only-followup-leads.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  // Validate contacts before allowing CRM selection
  const canSelectFindLead = (lead) => {
    const hr = String(lead["HR CONTACT"] || "").trim();
    const verification = String(
      lead["VERIFICATION"] || ""
    ).toLowerCase();

    if (
      !hr ||
      hr.toLowerCase() === "not disclosed" ||
      hr.toLowerCase() === "notdisclosed" ||
      hr.toLowerCase().includes("inferred (unverified)") ||
      verification.includes("generic email") ||
      verification.includes("not disclosed") ||
      verification.includes("notdisclosed")
    ) {
      return false;
    }

    const emailMatch = hr.match(
      /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/
    );

    if (!emailMatch) return false;

    const localPart = emailMatch[0]
      .split("@")[0]
      .toLowerCase();

    const genericNames = [
      "careers",
      "career",
      "jobs",
      "job",
      "hr",
      "info",
      "contact",
      "hello",
      "support",
      "admin",
      "recruitment",
      "recruiter",
      "talent",
      "hiring",
      "office",
      "mail",
      "enquiry",
      "inquiry",
      "apply",
      "team",
    ];

    return !genericNames.includes(localPart);
  };

  const toggleFindSelectAll = () => {
    const validIndices = findResults
      .map((l, i) => (canSelectFindLead(l) ? i : -1))
      .filter((i) => i !== -1);

    if (findSelected.length === validIndices.length) {
      setFindSelected([]);
    } else {
      setFindSelected(validIndices);
    }
  };


  // ---- Find Leads display helpers (read-only; they do not change what is saved) ----
  const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
  const findEmail = (l) => {
    const m = String(l["HR EMAIL"] || l["HR CONTACT"] || "").match(EMAIL_RE);
    return m ? m[0].toLowerCase() : "";
  };
  const findPhone = (l) => {
    const p = String(l["HR PHONE"] || "").trim();
    return /\d{8,}/.test(p) ? p : "";
  };
  const emailState = (l) => {
    const st = String(l["TOOL_EMAIL_STATUS"] || "").toLowerCase();
    if (!findEmail(l)) return null;
    if (st.includes("mx found") || st.includes("domain verified"))
      return { text: "Email verified", tone: "good" };
    if (st.includes("no mx") || st.includes("invalid") || st.includes("disposable"))
      return { text: "Email not valid", tone: "bad" };
    return { text: "Email format valid", tone: "warn" };
  };
  const phoneState = (l) => {
    const st = String(l["TOOL_PHONE_STATUS"] || "").toLowerCase();
    if (!findPhone(l)) return null;
    if (st.includes("landline")) return { text: "Landline", tone: "warn" };
    if (st.startsWith("valid")) return { text: "Valid mobile", tone: "good" };
    return { text: "Mobile not valid", tone: "bad" };
  };
  const toneCls = (t) =>
    t === "good"
      ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
      : t === "bad"
        ? "border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
        : "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300";
  // "31 of 67 leads removed by the intelligent tool: 31 no valid email or mobile, 2 expired ..."
  const getFindStats = () => {
    const m = String(findNote || "").match(/(\d+) of (\d+) leads removed/);
    const removed = m ? Number(m[1]) : 0;
    const total = m ? Number(m[2]) : findResults.length;
    const num = (re) => {
      const x = String(findNote || "").match(re);
      return x ? Number(x[1]) : 0;
    };
    return {
      total,
      valid: findResults.length,
      ready: findResults.filter(canSelectFindLead).length,
      phoneOnly: findResults.filter(isPhoneOnlyFindLead).length,
      removed,
      noContact: num(/(\d+) no valid/),
      expired: num(/(\d+) expired/),
      duplicate: num(/(\d+) duplicate/),
    };
  };

  const toggleFindSelect = (idx) => {
    setFindSelected((p) =>
      p.includes(idx)
        ? p.filter((i) => i !== idx)
        : [...p, idx]
    );
  };

  const create = async (e) => {
    e.preventDefault();

    try {
      await leadService.create(draft);
      toast.success("Lead created");

      setShowCreate(false);
      setDraft({
        name: "",
        email: "",
        companyName: "",
        status: "new",
        source: "website",
      });

      load(1);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const importLeads = async (e) => {
    const file = e.target.files?.[0];

    if (!file) return;

    const reader = new FileReader();

    reader.onload = async (event) => {
      try {
        const text = event.target.result;
        const r = await leadService.import(text);

        toast.success(
          `Imported ${r.created} new, updated ${r.updated}, ${r.failed} failed`
        );

        setShowImport(false);
        load(1, filters);
      } catch (err) {
        toast.error(err.message || "Failed to import CSV");
      }
    };

    reader.readAsText(file);
    e.target.value = null;
  };

  const saveSearch = async () => {
    const name = prompt("Name this search");

    if (!name) return;

    try {
      await savedSearchService.create({
        name,
        resource: "leads",
        filters,
      });

      toast.success("Search saved");

      const s = await savedSearchService.list({
        resource: "leads",
      });

      setSavedSearches(s || []);
    } catch (e) {
      toast.error(e.message);
    }
  };

  const applySaved = (s) => {
    const f = { ...filters, ...s.filters };

    setFilters(f);
    setTimeout(() => load(1, f), 0);
  };

  const deleteSavedSearch = async (e, id) => {
    e.stopPropagation();

    if (!confirm("Delete this saved search filter?")) return;

    try {
      await savedSearchService.remove(id);
      toast.success("Saved search deleted");

      setSavedSearches((prev) =>
        prev.filter((item) => item.id !== id)
      );
    } catch (e) {
      toast.error(e.message || "Failed to delete saved search");
    }
  };

  const remove = async (id, e) => {
    if (e) e.stopPropagation();

    if (!confirm("Delete this lead?")) return;

    const previousItems = [...items];

    setItems((prev) =>
      prev.filter((item) => item.id !== id)
    );

    setTotal((t) => Math.max(0, t - 1));

    try {
      await leadService.remove(id);
      toast.success("Lead deleted");
    } catch (err) {
      setItems(previousItems);
      setTotal((t) => t + 1);
      toast.error(err.message || "Failed to delete lead");
    }
  };

  return (
    <UptoPage>
      {/* Hero */}
      <div className="relative overflow-hidden -mx-6 md:-mx-10 lg:-mx-16 px-6 md:px-10 lg:px-16 py-10">
        <div className="absolute inset-0 pointer-events-none">
          <div
            className={`absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl ${
              darkMode ? "bg-teal-900/10" : "bg-teal-300/20"
            }`}
          />
        </div>

        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className={`text-3xl md:text-4xl font-semibold mb-2 ${heading}`}>
              Leads
            </h1>
            <p className={`text-base ${subtext}`}>
              {total.toLocaleString()} total leads in your pipeline
            </p>
          </div>

          {isMember && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowImport((p) => !p)}
                className={
                  !darkMode
                    ? "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
                    : "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
                }
              >
                <Upload className="h-4 w-4" /> Import CSV
              </Button>

              <a
                href={leadService.exportUrl(filters)}
                target="_blank"
                rel="noreferrer"
              >
                <Button
                  variant="secondary"
                  className={
                    !darkMode
                      ? "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
                      : "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
                  }
                >
                  <Download className="h-4 w-4" /> Export
                </Button>
              </a>

              <Button
                onClick={() => setShowFindLeads((p) => !p)}
                variant="secondary"
                className={
                  !darkMode
                    ? "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
                    : "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
                }
              >
                <Search className="h-4 w-4" /> Find Leads
              </Button>

              <Button
                onClick={() => setShowCreate((p) => !p)}
                className="bg-[#00b5ad] text-white hover:bg-[#2dd4bf]"
              >
                <Plus className="h-4 w-4" /> New Lead
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <section>
        <SectionHeading label="Filters" darkMode={darkMode} />

        <div className={`rounded-2xl p-5 border ${card}`}>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[200px] flex-1">
              <input
                placeholder="Search by name, email, company…"
                value={filters.search}
                onChange={(e) =>
                  setFilters((p) => ({
                    ...p,
                    search: e.target.value,
                  }))
                }
                className={`w-full rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              />
            </div>

            <select
              value={filters.status}
              onChange={(e) =>
                setFilters((p) => ({
                  ...p,
                  status: e.target.value,
                }))
              }
              className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
            >
              <option value="">All Statuses</option>
              {[
                "new",
                "contacted",
                "qualified",
                "in_progress",
                "converted",
                "closed",
                "lost",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>

            <select
              value={filters.source}
              onChange={(e) =>
                setFilters((p) => ({
                  ...p,
                  source: e.target.value,
                }))
              }
              className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
            >
              <option value="">All Sources</option>
              {[
                "website",
                "referral",
                "social_media",
                "email_campaign",
                "cold_call",
                "trade_show",
                "partner",
                "import",
                "api",
                "other",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>

            <select
              value={filters.tagId}
              onChange={(e) =>
                setFilters((p) => ({
                  ...p,
                  tagId: e.target.value,
                }))
              }
              className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
            >
              <option value="">All Tags</option>
              {tags.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>

            <Button
              onClick={saveSearch}
              variant="secondary"
              className={
                !darkMode
                  ? "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
                  : "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
              }
            >
              <Save className="h-4 w-4" /> Save
            </Button>
          </div>

          {savedSearches.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className={`text-xs ${subtext}`}>Saved:</span>

              {savedSearches.map((s) => (
                <div
                  key={s.id}
                  className={`inline-flex items-center gap-2 rounded-full border pl-3 pr-2 py-0.5 text-xs ${
                    darkMode
                      ? "border-slate-700 bg-slate-800 text-slate-300"
                      : "border-slate-300 bg-slate-50 text-slate-700"
                  }`}
                >
                  <button
                    onClick={() => applySaved(s)}
                    className="hover:text-[#00b5ad] font-medium transition-colors"
                  >
                    {s.name}
                  </button>

                  <button
                    onClick={(e) => deleteSavedSearch(e, s.id)}
                    className="rounded-full p-0.5 hover:bg-red-500/10 text-slate-400 hover:text-red-500 transition-colors"
                    title="Delete search shortcut"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Find Leads Section */}
      {showFindLeads && (
        <section>
          <div className={`rounded-2xl p-6 border ${card}`}>
            <div className="flex justify-between items-center mb-4">
              <h3 className={`text-base font-semibold ${heading}`}>
                Find Leads
              </h3>

              <button
                onClick={() => setShowFindLeads(false)}
                className="text-slate-400 hover:text-slate-500"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {(
              findStatus === "idle" ||
              findStatus === "error" ||
              findStatus === "running" ||
              findStatus === "done"
            ) && (
              <form
                onSubmit={startFind}
                className="flex gap-3 mb-4"
              >
                <input
                  placeholder='Filter by company, HR name or job (leave empty to show all leads)'
                  value={findQuery}
                  onChange={(e) => setFindQuery(e.target.value)}
                  disabled={findStatus === "running"}
                  className={`flex-1 rounded-xl border px-3 py-2 text-sm ${inputBg}`}
                />

                <Button
                  type="submit"
                  disabled={findStatus === "running"}
                  className="bg-[#00b5ad] text-white hover:bg-[#2dd4bf]"
                >
                  {findStatus === "running" ? "Searching..." : findQuery.trim() ? "Search" : "Show all"}
                </Button>
              </form>
            )}

            {findStatus === "running" && (
              <div className="flex flex-col items-center justify-center py-8">
                <FullPageSpinner />
                <p className={`mt-4 text-sm ${subtext}`}>
                  Searching across platforms... this can take a few minutes
                </p>
              </div>
            )}

            {findStatus === "done" && (
              <div className="flex flex-col gap-4">
                {(() => {
                  const st = getFindStats();
                  const items = [
                    { label: "Total leads checked", value: st.total, icon: Users, tone: "text-sky-600 bg-sky-50 dark:bg-sky-950/40 dark:text-sky-300" },
                    { label: "Valid leads", value: st.valid, icon: CheckCircle2, tone: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-300", hint: [st.phoneOnly && `${st.phoneOnly} phone-only`, findInCrm && `${findInCrm} already in CRM`].filter(Boolean).join(" · ") },
                    { label: "Ready for CRM", value: st.ready, icon: BadgeCheck, tone: "text-teal-600 bg-teal-50 dark:bg-teal-950/40 dark:text-teal-300", hint: "has a usable email" },
                    { label: "Not valid", value: st.removed, icon: XCircle, tone: "text-rose-600 bg-rose-50 dark:bg-rose-950/40 dark:text-rose-300",
                      hint: [st.noContact && `${st.noContact} no contact`, st.expired && `${st.expired} expired`, st.duplicate && `${st.duplicate} duplicate`].filter(Boolean).join(" · ") },
                  ];
                  return (
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                      {items.map((it) => (
                        <div key={it.label} className={`rounded-xl border p-4 ${darkMode ? "border-slate-800 bg-slate-900/40" : "border-slate-200 bg-white"}`}>
                          <div className="flex items-center justify-between">
                            <p className={`text-xs font-medium ${subtext}`}>{it.label}</p>
                            <span className={`rounded-lg p-1.5 ${it.tone}`}>
                              <it.icon className="h-4 w-4" />
                            </span>
                          </div>
                          <p className={`mt-2 text-2xl font-semibold ${heading}`}>{it.value}</p>
                          {it.hint ? <p className={`mt-0.5 text-xs ${subtext}`}>{it.hint}</p> : null}
                        </div>
                      ))}
                    </div>
                  );
                })()}
                <div className="flex justify-between items-center">
                  <p className={`text-sm ${subtext}`}>
                    Found {findResults.length} {findResults.length === 1 ? "lead" : "leads"}
                  </p>

                  <Button
                    onClick={confirmFind}
                    disabled={findSelected.length === 0}
                    className="bg-[#00b5ad] text-white hover:bg-[#2dd4bf]"
                  >
                    Add Selected ({findSelected.length})
                  </Button>
                </div>

                <div className="overflow-x-auto rounded-xl border dark:border-slate-800">
                  <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                    <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      <tr>
                        <th className="py-3 px-4 w-12">
                          <input
                            type="checkbox"
                            checked={
                              findResults.filter(canSelectFindLead).length > 0 &&
                              findSelected.length ===
                                findResults.filter(canSelectFindLead).length
                            }
                            onChange={toggleFindSelectAll}
                            className="rounded border-slate-300 text-[#00b5ad] focus:ring-[#00b5ad]"
                          />
                        </th>

                        <th className="py-3 px-4">Company</th>
                        <th className="py-3 px-4">HR Name</th>
                        <th className="py-3 px-4">Job Title</th>
                        <th className="py-3 px-4">Score</th>
                        <th className="py-3 px-4">Contact Status</th>
                      </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                      {findResults.map((l, i) => {
                        const canSelect = canSelectFindLead(l);
                        return (
                          <tr
                            key={i}
                            className={!canSelect ? "opacity-60" : ""}
                          >
                            <td className="py-3 px-4">
                              <input
                                type="checkbox"
                                disabled={!canSelect}
                                checked={findSelected.includes(i)}
                                onChange={() => toggleFindSelect(i)}
                                className="rounded border-slate-300 text-[#00b5ad] focus:ring-[#00b5ad]"
                              />
                            </td>

                            <td className="py-3 px-4">
                              <div className="flex items-start gap-3">
                                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-sm font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
                                  {String(l["COMPANY"] || "?").trim().charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <div className={`font-medium ${heading}`}>
                                    {l["COMPANY"] || "Unknown"}
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap gap-2">
                                    {findEmail(l) ? (
                                      <span
                                        title={emailState(l)?.text}
                                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${toneCls(emailState(l)?.tone)}`}
                                      >
                                        <Mail className="h-3 w-3" />
                                        {findEmail(l)}
                                      </span>
                                    ) : (
                                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${darkMode ? "border-slate-700 text-slate-400" : "border-slate-200 text-slate-500"}`}>
                                        <Mail className="h-3 w-3" /> No email
                                      </span>
                                    )}
                                    {findPhone(l) ? (
                                      <span
                                        title={phoneState(l)?.text}
                                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${toneCls(phoneState(l)?.tone)}`}
                                      >
                                        <Phone className="h-3 w-3" />
                                        {findPhone(l)}
                                      </span>
                                    ) : (
                                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${darkMode ? "border-slate-700 text-slate-400" : "border-slate-200 text-slate-500"}`}>
                                        <Phone className="h-3 w-3" /> No mobile
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </td>

                            <td className="py-3 px-4">
                              {l["HR NAME"] && !/^not\s*disclosed$/i.test(l["HR NAME"]) ? (
                                <>
                                  <div className={`font-medium ${heading}`}>{l["HR NAME"]}</div>
                                  {l["HR TITLE"] ? (
                                    <div className={`text-xs ${subtext}`}>{l["HR TITLE"]}</div>
                                  ) : null}
                                </>
                              ) : (
                                <span className={`text-xs ${subtext}`}>Not available</span>
                              )}
                            </td>

                            <td className={`py-3 px-4 ${body}`}>
                              {l["JOB TITLE"] || "Not available"}
                            </td>

                            <td className="py-3 px-4">
                              <span
                                title={l["SELECTION_REASON"] || ""}
                                className={`inline-flex min-w-[2.5rem] justify-center rounded-full px-2.5 py-1 text-xs font-semibold ${
                                  Number(l["SCORE"]) >= 80
                                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                                    : Number(l["SCORE"]) >= 50
                                      ? "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
                                      : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                                }`}
                              >
                                {l["SCORE"] ?? "—"}
                              </span>
                            </td>

                            <td className="py-3 px-4">
                              {(() => {
                                const es = emailState(l);
                                const label = canSelect
                                  ? es?.tone === "good" ? "Verified" : "Ready"
                                  : isPhoneOnlyFindLead(l) ? "Phone only" : "Review required";
                                const tone = canSelect
                                  ? es?.tone === "good" ? "good" : "warn"
                                  : isPhoneOnlyFindLead(l) ? "warn" : "bad";
                                return (
                                  <span
                                    title={l["SELECTION_REASON"] || ""}
                                    className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${toneCls(tone)}`}
                                  >
                                    {label}
                                  </span>
                                );
                              })()}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {findResults.filter(isPhoneOnlyFindLead).length > 0 && (
                  <div className="rounded-xl border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-200">
                    <div className="flex items-center justify-between gap-3">
                      <p>
                        {findResults.filter(isPhoneOnlyFindLead).length} phone-only
                        lead(s): valid mobile but no email, so they are not saved
                        to the CRM. Keep them for follow-up calls.
                      </p>
                      <Button
                        onClick={() =>
                          downloadPhoneFollowUp(findResults.filter(isPhoneOnlyFindLead))
                        }
                        className="bg-sky-600 text-white hover:bg-sky-700"
                      >
                        Download follow-up list
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* New Lead */}
      {showCreate && (
        <section>
          <div className={`rounded-2xl p-6 border ${card}`}>
            <h3 className={`text-base font-semibold mb-4 ${heading}`}>
              New Lead
            </h3>

            <form
              onSubmit={create}
              className="grid grid-cols-1 gap-3 md:grid-cols-2"
            >
              <input
                placeholder="Full name *"
                value={draft.name}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, name: e.target.value }))
                }
                required
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              />

              <input
                placeholder="Email *"
                type="email"
                value={draft.email}
                onChange={(e) =>
                  setDraft((p) => ({ ...p, email: e.target.value }))
                }
                required
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              />

              <input
                placeholder="Company"
                value={draft.companyName}
                onChange={(e) =>
                  setDraft((p) => ({
                    ...p,
                    companyName: e.target.value,
                  }))
                }
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              />

              <input
                placeholder="Job title"
                value={draft.jobTitle || ""}
                onChange={(e) =>
                  setDraft((p) => ({
                    ...p,
                    jobTitle: e.target.value,
                  }))
                }
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              />

              <select
                value={draft.status}
                onChange={(e) =>
                  setDraft((p) => ({
                    ...p,
                    status: e.target.value,
                  }))
                }
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              >
                {[
                  "new",
                  "contacted",
                  "qualified",
                  "in_progress",
                  "converted",
                  "closed",
                  "lost",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>

              <select
                value={draft.source}
                onChange={(e) =>
                  setDraft((p) => ({
                    ...p,
                    source: e.target.value,
                  }))
                }
                className={`rounded-xl border px-3 py-2 text-sm ${inputBg}`}
              >
                {[
                  "website",
                  "referral",
                  "social_media",
                  "email_campaign",
                  "cold_call",
                  "trade_show",
                  "partner",
                  "import",
                  "api",
                  "other",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>

              <div className="md:col-span-2 flex gap-2">
                <Button
                  type="submit"
                  className="bg-[#00b5ad] text-white hover:bg-[#2dd4bf]"
                >
                  Create Lead
                </Button>

                <Button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  variant="secondary"
                  className={
                    !darkMode
                      ? "bg-white text-slate-700 border border-slate-300"
                      : "bg-slate-800 text-slate-200 border border-slate-700"
                  }
                >
                  Cancel
                </Button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* Import CSV */}
      {showImport && (
        <section>
          <div className={`rounded-2xl p-6 border ${card}`}>
            <h3 className={`text-base font-semibold mb-4 ${heading}`}>
              Import CSV
            </h3>

            <p className={`text-sm mb-4 ${subtext}`}>
              Upload a .csv file containing your leads. Required columns are:
              {" "}
              <code>name</code>, <code>email</code>.
            </p>

            <div className="flex flex-col gap-4">
              <input
                type="file"
                accept=".csv"
                onChange={importLeads}
                className={`block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-[#00b5ad] file:text-white hover:file:bg-[#2dd4bf] cursor-pointer ${subtext}`}
              />

              <div className="flex gap-2">
                <Button
                  onClick={() => setShowImport(false)}
                  variant="secondary"
                  className={
                    !darkMode
                      ? "bg-white text-slate-700 border border-slate-300"
                      : "bg-slate-800 text-slate-200 border border-slate-700"
                  }
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Leads table */}
      <section>
        <SectionHeading label="Your Leads" darkMode={darkMode} />

        {error && (
          <ErrorBanner
            error={error}
            onRetry={() => load(page)}
          />
        )}

        <div className={`rounded-2xl border ${card} overflow-hidden`}>
          {loading ? (
            <FullPageSpinner />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Target}
              title="No leads match your filters"
              body="Try clearing filters or importing a CSV."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Email</th>
                    <th className="py-3 px-4">Company</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Score</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {items.map((l) => (
                    <tr
                      key={l.id}
                      className={`cursor-pointer ${
                        darkMode
                          ? "hover:bg-slate-800/40"
                          : "hover:bg-slate-50/60"
                      }`}
                      onClick={() => navigate(`/leads/${l.id}`)}
                    >
                      <td className={`py-3 px-4 font-medium ${heading}`}>
                        {l.name}
                      </td>

                      <td className={`py-3 px-4 ${body}`}>
                        <div className="flex items-center gap-2">
                          {l.email}
                          <CopyButton value={l.email} />
                        </div>
                      </td>

                      <td className={`py-3 px-4 ${body}`}>
                        {l.companyName || "—"}
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            l.status === "lost"
                              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
                              : l.status === "converted"
                                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                                : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          }`}
                        >
                          {l.status}
                        </span>
                      </td>

                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${heading}`}>
                            {l.score}
                          </span>

                          <div
                            className={`h-1.5 w-16 overflow-hidden rounded-full ${
                              darkMode ? "bg-slate-800" : "bg-slate-100"
                            }`}
                          >
                            <div
                              className="h-full bg-gradient-to-r from-[#00b5ad] to-[#2dd4bf]"
                              style={{ width: `${l.score}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      <td
                        className="py-3 px-4 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {isMember && (
                          <button
                            onClick={(e) => remove(l.id, e)}
                            className="text-red-500 hover:text-red-700 text-xs"
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button
            onClick={() => {
              const p = page - 1;
              setPage(p);
              load(p);
            }}
            disabled={page === 1}
            variant="secondary"
            className={
              !darkMode
                ? "bg-white text-slate-700 border border-slate-300"
                : "bg-slate-800 text-slate-200 border border-slate-700"
            }
          >
            Previous
          </Button>

          <span className={`text-xs ${subtext}`}>
            Page {page} of {pages}
          </span>

          <Button
            onClick={() => {
              const p = page + 1;
              setPage(p);
              load(p);
            }}
            disabled={page >= pages}
            variant="secondary"
            className={
              !darkMode
                ? "bg-white text-slate-700 border border-slate-300"
                : "bg-slate-800 text-slate-200 border border-slate-700"
            }
          >
            Next
          </Button>
        </div>
      )}
    </UptoPage>
  );
};

export default Leads;
