// Marketing campaigns page.
import React, { useEffect, useState } from "react";
import { campaignService, tagService, savedSearchService } from "@/services";
import {
  useUptoStyles,
  UptoPage,
  UptoHero,
  UptoButton,
  UptoInput,
  UptoBadge,
  UptoSpinner,
  UptoError,
  UptoEmptyState,
  UptoCard,
} from "@/components/UI/UptoHooks";
import {
  Megaphone,
  Sparkles,
  Plus,
  Play,
  Pause,
  Square,
  Clock,
  Calendar,
  ChevronDown,
  ChevronUp,
  Edit2,
  Trash2,
  Users,
  CheckCircle2,
  AlertCircle,
  Activity,
} from "lucide-react";
import CampaignStudio from "./CampaignStudio";
import { toast } from "sonner";

const LEAD_STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "qualified", label: "Qualified" },
  { value: "in_progress", label: "In Progress" },
  { value: "converted", label: "Converted" },
  { value: "closed", label: "Closed" },
  { value: "lost", label: "Lost" },
];

const Campaigns = () => {
  const s = useUptoStyles();
  const { darkMode } = s;

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showStudio, setShowStudio] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [tags, setTags] = useState([]);
  const [segments, setSegments] = useState([]);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [optimization, setOptimization] = useState(null);
  const [optimizationLoading, setOptimizationLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [leadsByCampaign, setLeadsByCampaign] = useState({});
  const [loadingLeads, setLoadingLeads] = useState(false);

  const toLocalDateTimeInput = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  const [draft, setDraft] = useState({
    name: "",
    audience: { type: "all" },
    schedule: "",
    steps: [{ day: 0, subject: "", body: "", time: "10:00" }],
  });

  const loadMetaData = async () => {
    try {
      const [tagsRes, segmentsRes] = await Promise.all([
        tagService.list(),
        savedSearchService.list({ resource: "leads" }),
      ]);

      const tagList = Array.isArray(tagsRes)
        ? tagsRes
        : tagsRes?.tags || tagsRes?.items || tagsRes?.data || [];

      const segList = Array.isArray(segmentsRes)
        ? segmentsRes
        : segmentsRes?.items || segmentsRes?.savedSearches || segmentsRes?.data || [];

      setTags(tagList);
      setSegments(segList);
    } catch (err) {
      console.error("Failed to load audience metadata:", err);
    }
  };

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await campaignService.list({ limit: 100 });
      const campaignList = res?.items || res || [];
      setItems(campaignList);
      setError(null);

      if (expandedId && !campaignList.some((c) => c.id === expandedId)) {
        setExpandedId(null);
      }
    } catch (e) {
      setError(e?.message || "Failed to load");
    } finally {
      if (!silent) setLoading(false);
    }
  };
const loadOptimization = async () => {
  setOptimizationLoading(true);

  try {
    const result = await campaignService.optimization();
    setOptimization(result);
  } catch (e) {
    console.error("Failed to load campaign optimization:", e);
  } finally {
    setOptimizationLoading(false);
  }
};
  useEffect(() => {
    load();
    loadMetaData();
    loadOptimization();

    const interval = setInterval(() => {
      load(true);
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  // Poll leads for running/completed campaigns
  useEffect(() => {
    if (expandedId === null) return;

    const campaign = items.find((c) => c.id === expandedId);
    if (!campaign || (campaign.conditions?.status === "scheduled" && !campaign.active)) {
      return;
    }

    let isMounted = true;

    const refreshLeads = async () => {
      try {
        const data = await campaignService.getLeads(expandedId);
        if (isMounted) {
          setLeadsByCampaign((prev) => ({
            ...prev,
            [expandedId]: data?.leads || [],
          }));
        }
      } catch (err) {
        if (
          err?.statusCode === 404 ||
          err?.response?.status === 404 ||
          String(err?.message).includes("not found")
        ) {
          if (isMounted) {
            setExpandedId(null);
            setLeadsByCampaign((prev) => {
              const copy = { ...prev };
              delete copy[expandedId];
              return copy;
            });
          }
        }
        console.error("Failed to refresh campaign leads:", err);
      }
    };

    refreshLeads();
    const interval = setInterval(refreshLeads, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [expandedId, items]);

  const handleAudienceTypeChange = (type) => {
    if (type === "all") {
      setDraft({ ...draft, audience: { type: "all" } });
    } else if (type === "tag") {
      setDraft({
        ...draft,
        audience: {
          type: "tag",
          tagId: tags[0]?.id ? Number(tags[0].id) : "",
        },
      });
    } else if (type === "status") {
      setDraft({ ...draft, audience: { type: "status", status: "new" } });
    } else if (type === "segment") {
      setDraft({
        ...draft,
        audience: { type: "segment", savedSearchId: segments[0]?.id || "" },
      });
    }
  };
  const handleGenerateAIEmail = async (index) => {
  const step = draft.steps[index];

  if (!draft.name.trim() && !step.body.trim()) {
    toast.error("Add a campaign name or email context first.");
    return;
  }

  setAiGenerating(true);

  try {
    const result = await campaignService.generateEmail({
      purpose: draft.name || "Create a B2B sales outreach email",
      context: step.body || "",
      tone: "professional",
    });

    const steps = [...draft.steps];
    steps[index] = {
      ...steps[index],
      subject: result.subject || steps[index].subject,
      body: result.body || steps[index].body,
    };

    setDraft({ ...draft, steps });
    toast.success("AI email generated");
  } catch (err) {
    console.error("AI email generation failed:", err);
    toast.error(err?.message || "Failed to generate AI email");
  } finally {
    setAiGenerating(false);
  }
};
  const renderAudienceLabel = (aud) => {
    if (!aud || aud === "all") return "All Leads";

    let audienceObj = aud;
    if (typeof aud === "string") {
      try {
        audienceObj = JSON.parse(aud);
      } catch (_) {
        return aud;
      }
    }

    if (audienceObj?.type === "all") return "All Leads";

    if (audienceObj?.type === "tag") {
      const tag = tags.find((t) => t.id === Number(audienceObj.tagId));
      return tag ? `Tag: ${tag.name}` : `Tag #${audienceObj.tagId}`;
    }

    if (audienceObj?.type === "status") {
      const matchedStatus = LEAD_STATUS_OPTIONS.find((s) => s.value === audienceObj.status);
      return `Status: ${matchedStatus ? matchedStatus.label : audienceObj.status}`;
    }

    if (audienceObj?.type === "segment") {
      const seg = segments.find((s) => s.id === Number(audienceObj.savedSearchId));
      return seg ? `Segment: ${seg.name}` : `Segment #${audienceObj.savedSearchId}`;
    }

    return "All Leads";
  };

  const resetDraft = () => {
    setDraft({
      name: "",
      audience: { type: "all" },
      schedule: "",
      steps: [{ day: 0, subject: "", body: "", time: "10:00" }],
    });
  };

  const closeEditor = () => {
    setShowCreate(false);
    setEditingId(null);
    resetDraft();
  };

  const handleCreate = async (e) => {
    e.preventDefault();

    if (!draft.name.trim()) {
      toast.error("Please enter a campaign name.");
      return;
    }

    if (!draft.schedule) {
      toast.error("Please select a campaign start date.");
      return;
    }

    try {
      const startDate = draft.schedule.slice(0, 10);
      const startTime = draft.steps?.[0]?.time || "10:00";
      const scheduleDateTime = `${startDate}T${startTime}`;

      const payload = {
        ...draft,
        schedule: new Date(scheduleDateTime).toISOString(),
      };

      if (editingId) {
        await campaignService.update(editingId, payload);
        toast.success("Campaign updated");
      } else {
        await campaignService.create(payload);
        toast.success("Campaign created");
      }

      closeEditor();
      await load();
    } catch (err) {
      toast.error(err?.message || "Operation failed");
    }
  };

  const handleLaunch = async (id) => {
    try {
      await campaignService.launch(id);
      toast.success("Campaign launched");
      load();
    } catch (e) {
      toast.error(e?.message || "Launch failed");
    }
  };

  const handlePause = async (id) => {
    try {
      await campaignService.pause(id);
      toast.success("Campaign paused");
      load();
    } catch (e) {
      toast.error(e?.message || "Pause failed");
    }
  };

  const handleStop = async (id) => {
    try {
      await campaignService.stop(id);
      toast.success("Campaign stopped");
      load();
    } catch (e) {
      toast.error(e?.message || "Stop failed");
    }
  };

  const handleResume = async (id) => {
    try {
      await campaignService.resume(id);
      toast.success("Campaign resumed");
      load();
    } catch (e) {
      toast.error(e?.message || "Resume failed");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this campaign?")) return;

    try {
      if (expandedId === id) setExpandedId(null);
      await campaignService.remove(id);
      toast.success("Campaign deleted");
      load();
    } catch (err) {
      toast.error(err?.message || "Delete failed");
    }
  };

  // Fixed toggleLeads: Scheduled state me previewAudience se leads laata hai, running me actual getLeads se
  const toggleLeads = async (campaignId) => {
    if (expandedId === campaignId) {
      setExpandedId(null);
      return;
    }

    const campaign = items.find((c) => c.id === campaignId);
    setExpandedId(campaignId);
    setLoadingLeads(true);

    try {
      // Agar campaign scheduled hai, toh audience preview call karke expected leads display karein
      if (campaign?.conditions?.status === "scheduled" && !campaign.active) {
        const aud = campaign.conditions?.audience || { type: "all" };
        const res = await campaignService.previewAudience(aud);
        const data = res?.data ?? res;
        const leadsList = (data?.sample || []).map((lead) => ({
          ...lead,
          enrollmentStatus: "SCHEDULED",
        }));
        setLeadsByCampaign((prev) => ({
          ...prev,
          [campaignId]: leadsList,
        }));
      } else {
        // Running/Completed me DB sequence enrollments fetch karein
        const data = await campaignService.getLeads(campaignId);
        setLeadsByCampaign((prev) => ({
          ...prev,
          [campaignId]: data?.leads || [],
        }));
      }
    } catch (err) {
      console.warn("Failed to load leads:", err);
      toast.error(err?.message || "Failed to load leads");
    } finally {
      setLoadingLeads(false);
    }
  };

  const handleEdit = (campaign) => {
    setEditingId(campaign.id);

    const rawAudience = campaign.conditions?.audience || "all";
    let audience = rawAudience;

    if (typeof rawAudience === "string" && rawAudience !== "all") {
      try {
        audience = JSON.parse(rawAudience);
      } catch (_) {
        audience = rawAudience;
      }
    }

    setDraft({
      name: campaign.name || "",
      audience,
      schedule: toLocalDateTimeInput(campaign.conditions?.schedule),
      steps: campaign.conditions?.steps?.length
        ? campaign.conditions.steps
        : [{ day: 0, subject: "", body: "", time: "10:00" }],
    });

    setShowCreate(true);
  };

  const getStatusBadge = (c) => {
    const status = c.conditions?.status;
    if (status === "paused") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
          <Pause className="w-3 h-3" /> Paused
        </span>
      );
    }
    if (status === "scheduled") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
          <Clock className="w-3 h-3" /> Scheduled
        </span>
      );
    }
    if (status === "completed") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" /> Completed
        </span>
      );
    }
    if (status === "error") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
          <AlertCircle className="w-3 h-3" /> Error
        </span>
      );
    }
    if (c.active) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/20">
          <Activity className="w-3 h-3 animate-pulse" /> Running
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
        Draft
      </span>
    );
  };

  return (
    <UptoPage>
      <UptoHero
        title="Campaigns"
        subtitle="Email and marketing automation."
        darkMode={darkMode}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <UptoButton
              variant={!showStudio ? "primary" : "secondary"}
              onClick={() => setShowStudio(false)}
            >
              <Megaphone className="mr-1.5 inline h-4 w-4" /> Campaign History
            </UptoButton>
            <UptoButton
              variant={showStudio ? "primary" : "secondary"}
              onClick={() => setShowStudio(true)}
            >
              <Sparkles className="mr-1.5 inline h-4 w-4" /> Create Campaign
            </UptoButton>
          </div>
        }
      />
      {optimizationLoading ? (
  <UptoCard className="mb-6">
    <UptoSpinner />
  </UptoCard>
) : optimization?.campaigns?.length > 0 ? (
  <UptoCard className="mb-6">
    <div className="mb-4">
      <h2 className="text-lg font-semibold">Campaign Optimization</h2>
      <p className="text-sm text-muted-foreground">
        Performance insights and recommendations based on campaign engagement.
      </p>
    </div>

    <div className="space-y-4">
      {optimization.campaigns.map((campaign) => (
        <div
          key={campaign.campaignId}
          className="rounded-lg border p-4"
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">{campaign.campaignName}</h3>

            <UptoBadge>
              {campaign.sent} sent
            </UptoBadge>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div>
              <div className="text-xs text-muted-foreground">Open Rate</div>
              <div className="text-lg font-semibold">
                {campaign.openRate}%
              </div>
            </div>

            <div>
              <div className="text-xs text-muted-foreground">Click Rate</div>
              <div className="text-lg font-semibold">
                {campaign.clickRate}%
              </div>
            </div>

            <div>
              <div className="text-xs text-muted-foreground">Reply Rate</div>
              <div className="text-lg font-semibold">
                {campaign.replyRate}%
              </div>
            </div>

            <div>
              <div className="text-xs text-muted-foreground">Replies</div>
              <div className="text-lg font-semibold">
                {campaign.replied}
              </div>
            </div>
          </div>

          {campaign.recommendations?.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2">
                Recommendations
              </div>

              <ul className="space-y-1">
                {campaign.recommendations.map((recommendation, index) => (
                  <li
                    key={index}
                    className="text-sm text-muted-foreground"
                  >
                    • {recommendation}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}
    </div>
  </UptoCard>
) : null}

      {showStudio && (
        <CampaignStudio onClose={() => setShowStudio(false)} onSaved={() => load()} />
      )}

      <div className="w-full space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 shadow-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Campaigns
            </span>
            <p className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              {items.length}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 shadow-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-teal-600 dark:text-teal-400">
              Running
            </span>
            <p className="mt-1 text-2xl font-bold tracking-tight text-teal-600 dark:text-teal-400">
              {items.filter((c) => c.active).length}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 shadow-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-blue-500">
              Scheduled
            </span>
            <p className="mt-1 text-2xl font-bold tracking-tight text-blue-500">
              {items.filter((c) => c.conditions?.status === "scheduled" && !c.active).length}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 shadow-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-500">
              Completed
            </span>
            <p className="mt-1 text-2xl font-bold tracking-tight text-emerald-500">
              {items.filter((c) => c.conditions?.status === "completed").length}
            </p>
          </div>
        </div>

        <UptoCard className="p-0 overflow-hidden border border-slate-200 dark:border-slate-800">
          {loading && (
            <div className="p-8">
              <UptoSpinner />
            </div>
          )}

          {error && (
            <div className="p-6">
              <UptoError message={error} onRetry={load} />
            </div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="p-8">
              <UptoEmptyState
                icon={Megaphone}
                title="No campaigns yet"
                body="Launch your first outreach or workflow to track activity and delivery status here."
              />
            </div>
          )}

          {!loading && !error && items.length > 0 && (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
              {items.map((c) => (
                <div
                  key={c.id}
                  className="group transition-colors hover:bg-slate-50/60 dark:hover:bg-slate-800/30 p-4 sm:p-5"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-1.5 min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <h3 className="text-base font-bold text-slate-900 dark:text-white truncate">
                          {c.name}
                        </h3>
                        {getStatusBadge(c)}
                      </div>

                      <div className="flex flex-wrap items-center gap-y-1.5 gap-x-3 text-xs text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                          <Users className="h-3.5 w-3.5 text-teal-500" />
                          {renderAudienceLabel(c.conditions?.audience)}
                        </span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5 text-slate-400" />
                          {c.conditions?.schedule
                            ? new Date(c.conditions.schedule).toLocaleString(undefined, {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })
                            : "No schedule"}
                        </span>

                        {c.conditions?.status === "scheduled" && !c.active && (
                          <>
                            <span>•</span>
                            <span className="font-semibold text-blue-600 dark:text-blue-400">
                              {c.expectedLeads ?? 0} Expected Leads
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {c.conditions?.status === "paused" ? (
                        <>
                          <UptoButton
                            variant="ghost"
                            className="text-xs h-8 px-2.5 text-teal-600 dark:text-teal-400"
                            onClick={() => handleResume(c.id)}
                          >
                            <Play className="h-3.5 w-3.5 mr-1" /> Resume
                          </UptoButton>
                          <UptoButton
                            variant="secondary"
                            className="text-xs h-8 px-2.5"
                            onClick={() => handleStop(c.id)}
                          >
                            <Square className="h-3 w-3 mr-1 text-slate-500" /> Stop
                          </UptoButton>
                        </>
                      ) : !c.active && c.conditions?.status === "scheduled" ? (
                        <span className="text-xs font-medium text-slate-500 px-2">
                          Waiting for trigger
                        </span>
                      ) : c.conditions?.status === "error" ? (
                        <span className="text-xs font-medium text-rose-500 px-2">
                          Needs Reconfiguration
                        </span>
                      ) : !c.active &&
                        c.conditions?.status !== "completed" &&
                        c.conditions?.status !== "cancelled" ? (
                        <UptoButton
                          variant="secondary"
                          className="text-xs h-8 px-2.5 text-teal-600 hover:text-teal-700"
                          onClick={() => handleLaunch(c.id)}
                        >
                          <Play className="h-3.5 w-3.5 mr-1" /> Schedule
                        </UptoButton>
                      ) : c.active ? (
                        <>
                          <UptoButton
                            variant="secondary"
                            className="text-xs h-8 px-2.5"
                            onClick={() => handlePause(c.id)}
                          >
                            <Pause className="h-3.5 w-3.5 mr-1 text-amber-500" /> Pause
                          </UptoButton>
                          <UptoButton
                            variant="secondary"
                            className="text-xs h-8 px-2.5"
                            onClick={() => handleStop(c.id)}
                          >
                            <Square className="h-3 w-3 mr-1 text-rose-500" /> Stop
                          </UptoButton>
                        </>
                      ) : null}

                      <UptoButton
                        variant="ghost"
                        className="text-xs h-8 px-2.5"
                        onClick={() => toggleLeads(c.id)}
                      >
                        {expandedId === c.id ? (
                          <>
                            Hide Leads <ChevronUp className="h-3.5 w-3.5 ml-1" />
                          </>
                        ) : (
                          <>
                            View Leads <ChevronDown className="h-3.5 w-3.5 ml-1" />
                          </>
                        )}
                      </UptoButton>

                      <button
                        type="button"
                        onClick={() => handleEdit(c)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 hover:text-teal-600 dark:hover:text-teal-400 hover:border-teal-500 transition-colors"
                        title="Edit Campaign"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(c.id)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 hover:text-rose-600 hover:border-rose-500 transition-colors"
                        title="Delete Campaign"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {c.conditions?.status === "error" && c.conditions?.lastError && (
                    <div className="mt-3.5 rounded-xl border border-rose-200 bg-rose-50/80 dark:border-rose-900/50 dark:bg-rose-950/20 p-3 text-xs flex items-start gap-2 text-rose-700 dark:text-rose-300">
                      <AlertCircle className="h-4 w-4 shrink-0 text-rose-500 mt-0.5" />
                      <div>
                        <span className="font-semibold">Activation error: </span>
                        <span>{c.conditions.lastError}</span>
                      </div>
                    </div>
                  )}

                  {/* Leads Drawer: Ab scheduled campaign ke time par bhi audience list dikhegi */}
                  {expandedId === c.id && (
                    <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/40 p-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-3 flex items-center justify-between">
                        <span>Campaign Leads</span>
                        <span className="text-[11px] font-normal text-slate-500">
                          {c.conditions?.status === "scheduled" && !c.active
                            ? "Targeted audience leads (Scheduled)"
                            : "Enrolled delivery status"}
                        </span>
                      </h4>

                      {loadingLeads ? (
                        <div className="py-4">
                          <UptoSpinner />
                        </div>
                      ) : leadsByCampaign[c.id]?.length ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                          {leadsByCampaign[c.id].map((l) => (
                            <div
                              key={l.enrollmentId || l.id}
                              className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200/70 dark:border-slate-700 text-xs"
                            >
                              <div className="min-w-0">
                                <p className="font-semibold text-slate-900 dark:text-white truncate">
                                  {l.name || "—"}{" "}
                                  <span className="font-normal text-slate-500">({l.email})</span>
                                </p>
                                <p className="text-[11px] text-slate-400 mt-0.5">
                                  {l.companyName || "No Company"}
                                </p>
                              </div>
                              <div className="flex items-center gap-2.5">
                                <UptoBadge
                                  tone={
                                    (l.enrollmentStatus || "SCHEDULED") === "COMPLETED"
                                      ? "success"
                                      : (l.enrollmentStatus || "SCHEDULED") === "FAILED"
                                      ? "danger"
                                      : (l.enrollmentStatus || "SCHEDULED") === "SCHEDULED"
                                      ? "info"
                                      : "default"
                                  }
                                >
                                  {l.enrollmentStatus || "SCHEDULED"}
                                </UptoBadge>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500">No leads found for this campaign.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </UptoCard>
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <form
            onSubmit={handleCreate}
            className="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full max-h-[90vh] overflow-y-auto border border-slate-200 dark:border-slate-800 shadow-xl"
          >
            <h3 className={`text-lg font-bold mb-4 ${s.heading}`}>
              {editingId ? "Edit campaign" : "New campaign"}
            </h3>

            <div className="space-y-4">
              <UptoInput
                label="Campaign Name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                required
              />

              <div className="space-y-2">
                <label className={`text-sm font-medium ${s.body}`}>Target Audience</label>
                <select
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  value={typeof draft.audience === "string" ? "all" : draft.audience?.type || "all"}
                  onChange={(e) => handleAudienceTypeChange(e.target.value)}
                >
                  <option value="all">All Leads</option>
                  <option value="status">By Status</option>
                  <option value="tag">By Tag</option>
                  <option value="segment">By Saved Segment</option>
                </select>
              </div>

              <UptoInput
                label="Campaign Start Date"
                type="date"
                min={new Date().toISOString().slice(0, 10)}
                value={(draft.schedule || "").slice(0, 10)}
                onChange={(e) => setDraft({ ...draft, schedule: e.target.value })}
                required
              />
            </div>

            <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-4">
              <UptoButton type="button" variant="ghost" onClick={closeEditor}>
                Cancel
              </UptoButton>
              <UptoButton type="submit">
                {editingId ? "Save Changes" : "Create"}
              </UptoButton>
            </div>
          </form>
        </div>
      )}
    </UptoPage>
  );
};

export default Campaigns;