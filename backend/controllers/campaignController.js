// Campaign management - marketing automation and email campaigns.
const { prisma } = require("../config/postgres");
const { AppError } = require("../middleware/errorHandler");
const asyncHandler = require("../utils/asyncHandler");
const response = require("../utils/response");
const { recordAudit } = require("../services/auditService");
const { generateCampaignDraftOptions } = require("../services/aiEmailService");
const { invalidateCache } = require("../utils/cache");
const { personalizeCampaignEmail } = require("../services/aiEmailService");
const {
  getMatchingCampaignLeads,
  getCampaignAudienceCount,
  ensureCampaignSequence,
  reconcileCampaignAudience,
} = require("../services/campaignAutomationService");

// Campaigns are stored using the existing Workflow model with JSON metadata.
// This provides full campaign management without new schema.

const CAMPAIGN_STATUSES = ["draft", "scheduled", "running", "paused", "error", "completed", "cancelled"];
const CAMPAIGN_TYPES = ["email", "sms", "social", "webhook", "multi_channel"];

const list = asyncHandler(async (req, res) => {
  const { page = 1, limit = 50, status, type } = req.query;
  const where = { orgId: req.orgId };
  // Workflow model has 'active' (Boolean), not 'status' (String)
  if (status) where.active = (status === "running");
  const skip = (Number(page) - 1) * Number(limit);
  const [items, total] = await Promise.all([
    prisma.workflow.findMany({ where, orderBy: { createdAt: "desc" }, skip, take: Number(limit) }),
    prisma.workflow.count({ where }),
  ]);

  // Expected audience size is always calculated from the latest campaign
  // conditions, so the pre-launch UI never shows a stale recipient count.
  const enrichedItems = await Promise.all(
    items.map(async (campaign) => {
      const conditions =
        campaign.conditions &&
        typeof campaign.conditions === "object"
          ? campaign.conditions
          : {};
      const isScheduled = conditions.status === "scheduled" && !campaign.active;

      if (!isScheduled) {
        return {
          ...campaign,
          expectedLeads: null,
          expectedLeadsPreview: [],
        };
      }

      const expectedLeadsPreview = await getMatchingCampaignLeads(
        conditions.audience,
        req.orgId
      );

      return {
        ...campaign,
        expectedLeads: expectedLeadsPreview.length,
        expectedLeadsPreview,
      };
    })
  );

  return response.paginated(res, enrichedItems, total, page, limit);
});


const copyPreview = asyncHandler(async (req, res) => {
const {
audience,
campaignName,
tone = "professional",
goal = "replies",
valueProp = "",
prompt = ""
} = req.body || {};

if (!audience || typeof audience !== "object" || Array.isArray(audience))
throw new AppError("A valid audience object is required.", 400);
if (!["professional", "conversational", "concise"].includes(tone))
throw new AppError("Choose a supported email tone.", 400);
if (!["replies", "meetings", "awareness", "followup"].includes(goal))
throw new AppError("Choose a supported campaign goal.", 400);
if (typeof valueProp !== "string" || valueProp.length > 500)
throw new AppError("Value proposition must be 500 characters or fewer.", 400);
if (typeof prompt !== "string" || prompt.length > 1000)
throw new AppError("Prompt must be 1000 characters or fewer.", 400);

const matches = await getMatchingCampaignLeads(audience, req.orgId);
const lead = matches[0] || {};
const campaign = String(campaignName || "Sales outreach").trim().slice(0, 120);
const audienceType = audience.type || "all";
const audienceLabel = audience.label || campaign;
const offer = valueProp.trim() || prompt.trim();
const cta = {
replies: "Would you be open to a brief conversation?",
meetings: "Would you be available for a short meeting?",
awareness: "Would you like me to share more information?",
followup: "Would it be helpful to discuss the next step?"
}[goal];

let variants = [];
let usedFallback = false;

try {
const drafts = [];
const directions = [
"Lead with a relevant benefit and simple call to action.",
"Use a different concise angle and clear next step. Avoid clickbait."
];

for (let i = 0; i < directions.length; i++) {
  const generated = await personalizeCampaignEmail({
    name: lead.name,
    company: lead.companyName || lead.company,
    jobTitle: lead.jobTitle,
    industry: lead.industry,
    location: lead.location,
    leadStatus: lead.status,
    leadScore: lead.score,
    campaignName: campaign,
    campaignDescription: [
      "Draft only. Do not send this email.",
      "Tone: " + tone,
      "Goal: " + goal,
      offer ? "Owner-provided context: " + offer : "Do not invent a value proposition.",
      directions[i]
    ].join("\n"),
    audienceLabel,
    audienceType,
    audienceContext: audience,
    stepNumber: 1
  });
  drafts.push({ id: i + 1, subject: generated.subject, body: generated.body });
}
variants = drafts;

} catch (error) {
usedFallback = true;
console.warn("[Campaign preview] AI unavailable; using local drafts:", error.message);

const name = String(lead.name || "").trim();
const company = String(lead.companyName || lead.company || "").trim();
const greeting = name ? "Hi " + name + "," : "Hello,";
const context = company ? " at " + company : "";
const detail = offer || "I'd be glad to share relevant information and learn whether this could be useful to your team.";

variants = [
  {
    id: 1,
    subject: campaign + ": a possible next step",
    body: [greeting, "", "I'm reaching out regarding " + campaign + context + ".", detail, "", cta, "", "Best regards"].join("\n")
  },
  {
    id: 2,
    subject: "A brief question about " + campaign,
    body: [greeting, "", "I wanted to briefly connect about " + campaign + context + ".", offer ? "In particular, " + offer : "If relevant to your priorities, I can share a concise overview.", "", cta, "", "Best regards"].join("\n")
  }
];

}

return response.success(res, {
variants,
personalizedFor: lead.id ? {
name: lead.name || null,
company: lead.companyName || lead.company || null
} : null,
generationMode: usedFallback ? "template_fallback" : "gemini",
note: usedFallback
? "Gemini is unavailable. Two local template drafts were created; review them before sending."
: lead.id
? "Drafts personalized using one matching lead as a preview."
: "No matching lead found; drafts use generic campaign context."
});
});

const audiencePreview = asyncHandler(async (req, res) => {
  const audience = req.body?.audience;
  if (!audience || typeof audience !== "object" || Array.isArray(audience)) {
    throw new AppError("A valid audience object is required.", 400);
  }

  const type = audience.type || "all";
  if (!["all", "status", "tag", "score", "segment"].includes(type)) {
    throw new AppError("Unsupported audience type.", 400);
  }
  if (type === "status" && !["new", "contacted", "qualified", "in_progress", "converted", "closed", "lost"].includes(audience.status)) {
    throw new AppError("A valid lead status is required.", 400);
  }
  if (type === "tag" && (audience.tagId == null || audience.tagId === "" || !Number.isInteger(Number(audience.tagId)) || Number(audience.tagId) <= 0)) {
    throw new AppError("A valid tag must be selected.", 400);
  }
  if (type === "segment" && (audience.savedSearchId == null || audience.savedSearchId === "" || !Number.isInteger(Number(audience.savedSearchId)) || Number(audience.savedSearchId) <= 0)) {
    throw new AppError("A valid saved segment must be selected.", 400);
  }
  if (type === "score") {
    const min = Number(audience.min);
    const max = Number(audience.max);
    if (audience.min == null || audience.max == null || !Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max > 100 || min > max) {
      throw new AppError("Choose a valid score range from 0 to 100.", 400);
    }
  }

  const leads = await getMatchingCampaignLeads(audience, req.orgId);
  return response.success(res, {
    count: leads.length,
    sample: leads.slice(0, 5),
  });
});

const get = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({ where: { id: Number(req.params.id), orgId: req.orgId } });
  if (!campaign) throw new AppError("Campaign not found.", 404);
  return response.success(res, campaign);
});

const create = asyncHandler(async (req, res) => {
  const {
  name,
  description,
  audience,
  steps,
  type = "email",
  status = "draft",
  segment,
  content,
  schedule,
  budget,
} = req.body;
  if (!name) throw new AppError("name is required.", 400);
  // WorkflowTrigger enum: use "SCHEDULED_TIME" as the default campaign trigger.
  // Store the campaign type inside the conditions JSON object.
  const campaign = await prisma.workflow.create({
    data: {
      orgId: req.orgId,
      userId: req.user.id,
      name, description: description || null,
      trigger: "SCHEDULED_TIME",
      conditions: {
  segment: segment || null,
  audience: audience || "all",
  steps:
    Array.isArray(steps) && steps.length > 0
      ? steps.map(({ subject: _subject, body: _body, ...step }) => step)
      : [{ day: 0 }],
  type,
  schedule: schedule || null,
  status: schedule ? "scheduled" : "draft",
  budget: budget || null,
},
      actions: content || [{ type: "SEND_EMAIL" }],
      // A scheduled campaign must stay inactive until the scheduler reaches
      // the latest conditions.schedule value. Never create enrollment early.
      active: false,
    },
  });
  await recordAudit({ userId: req.user.id, orgId: req.orgId, action: "campaign.create", entityType: "Campaign", entityId: campaign.id, metadata: { name, type, status } });
  invalidateCache("/campaigns");
  return response.created(res, campaign);
});

const update = asyncHandler(async (req, res) => {
  const {
    name,
    description,
    audience,
    steps,
    status,
    segment,
    content,
    budget,
    schedule,
  } = req.body;

  const campaign = await prisma.workflow.findFirst({
    where: { id: Number(req.params.id), orgId: req.orgId },
  });
  if (!campaign) throw new AppError("Campaign not found.", 404);

  const currentConditions =
    typeof campaign.conditions === "object" && campaign.conditions
      ? campaign.conditions
      : {};
  const nextConditions = { ...currentConditions };
  const audienceChanged = audience !== undefined;
  let scheduleChanged = false;

  if (name !== undefined) campaign.name = name;
  const data = {};
  if (name !== undefined) data.name = name;
  if (description !== undefined) data.description = description;
  if (content !== undefined) data.actions = content;

  if (segment !== undefined) nextConditions.segment = segment;
  if (budget !== undefined) nextConditions.budget = budget;
  // Manual email subject/body are no longer campaign configuration.
  // Gemini generates both values per lead when the sequence runs.
  delete nextConditions.subject;
  delete nextConditions.body;

  if (steps !== undefined) {
    nextConditions.steps =
      Array.isArray(steps) && steps.length > 0
        ? steps.map(({ subject: _subject, body: _body, ...step }) => step)
        : [{ day: 0 }];
  }
  if (audience !== undefined) nextConditions.audience = audience;

  if (schedule !== undefined) {
    const scheduledAt = schedule ? new Date(schedule) : null;
    if (schedule && (!scheduledAt || Number.isNaN(scheduledAt.getTime()))) {
      throw new AppError("A valid campaign schedule date and time is required.", 400);
    }
    nextConditions.schedule = scheduledAt ? scheduledAt.toISOString() : null;
    scheduleChanged = true;
  }

  const wasRunning = campaign.active && currentConditions.status === "running";
  const nextSchedule = nextConditions.schedule ? new Date(nextConditions.schedule) : null;

  // Editing a scheduled campaign must never activate it early. The latest
  // schedule remains the source of truth for the scheduler.
  const configurationChanged =
    audienceChanged ||
    segment !== undefined ||
    budget !== undefined ||
    steps !== undefined ||
    scheduleChanged;

  if (!wasRunning && scheduleChanged) {
    data.active = false;
    nextConditions.status = nextSchedule ? "scheduled" : "draft";
    delete nextConditions.autoPaused;
    delete nextConditions.lastError;
    delete nextConditions.errorAt;
  } else if (!wasRunning && currentConditions.status === "error" && configurationChanged) {
    // A configuration change is the explicit recovery action for a failed
    // scheduled campaign. Clear the saved error and return it to scheduling.
    data.active = false;
    nextConditions.status = nextSchedule ? "scheduled" : "draft";
    delete nextConditions.autoPaused;
    delete nextConditions.lastError;
    delete nextConditions.errorAt;
  } else if (status !== undefined && wasRunning) {
    data.active = status === "running";
    nextConditions.status = status;
  } else if (status !== undefined && !scheduleChanged) {
    data.active = status === "running";
    nextConditions.status = status;
  }

  if (
    audienceChanged ||
    segment !== undefined ||
    budget !== undefined ||
    steps !== undefined ||
    scheduleChanged ||
    status !== undefined
  ) {
    data.conditions = nextConditions;
  }

  await prisma.workflow.update({ where: { id: campaign.id }, data });

  if (audienceChanged && wasRunning) {
    await reconcileCampaignAudience(campaign.id, req.orgId, req.user.id);
  }

  invalidateCache("/campaigns");
  return response.success(res, { message: "Campaign updated." });
});

const remove = asyncHandler(async (req, res) => {
  const result = await prisma.workflow.deleteMany({ where: { id: Number(req.params.id), orgId: req.orgId } });
  if (result.count === 0) throw new AppError("Campaign not found.", 404);
  invalidateCache("/campaigns");
  return response.success(res, { message: "Campaign deleted." });
});

const activateCampaign = async ({
  campaign,
  orgId,
  userId,
  allowPastSchedule = false,
}) => {
  if (!campaign) throw new AppError("Campaign not found.", 404);

  // Re-read the workflow immediately before activation. This makes the
  // database's latest conditions.schedule and audience the source of truth,
  // even when the scheduler picked up an older snapshot.
  const latestCampaign = await prisma.workflow.findFirst({
    where: { id: campaign.id, orgId },
  });
  if (!latestCampaign) throw new AppError("Campaign not found.", 404);

  const conditions =
    typeof latestCampaign.conditions === "object" && latestCampaign.conditions
      ? latestCampaign.conditions
      : {};

  if (conditions.status === "running" && latestCampaign.active) {
    return {
      alreadyRunning: true,
      scheduledAt: conditions.schedule || null,
      enrolled: 0,
    };
  }

  const scheduledAt = conditions.schedule ? new Date(conditions.schedule) : null;

  if (!scheduledAt || Number.isNaN(scheduledAt.getTime())) {
    throw new AppError("A valid campaign schedule date and time is required.", 400);
  }

  if (!allowPastSchedule && scheduledAt.getTime() < Date.now()) {
    throw new AppError("Campaign schedule must be in the future.", 400);
  }

  // Email subject/body are generated by Gemini per lead at send time.
  // They are intentionally NOT required for campaign activation.
  // Keep at least one sequence step so a valid campaign can enroll leads
  // and let the worker generate the actual email content.
  const rawCampaignSteps =
    Array.isArray(conditions.steps) && conditions.steps.length > 0
      ? conditions.steps
      : [{ day: 0 }];

  // Gemini owns campaign email content. Strip any legacy/manual subject/body
  // fields before sequence creation so old campaigns cannot reintroduce a
  // removed template requirement.
  const campaignSteps = rawCampaignSteps.map((step) => {
    if (!step || typeof step !== "object") return { day: 0 };
    const { subject: _subject, body: _body, ...stepWithoutEmailContent } = step;
    return stepWithoutEmailContent;
  });

  // Sequence creation happens only at activation time. A scheduled campaign
  // therefore has no SequenceEnrollment records before its start time.
  const sequence = await ensureCampaignSequence({
    campaign: latestCampaign,
    orgId,
    userId: userId || latestCampaign.userId,
    steps: campaignSteps,
  });

  // Read the audience after reading the latest workflow, so audience edits made
  // before the scheduled time are applied to the real enrollment set.
  const leads = await getMatchingCampaignLeads(conditions.audience, orgId);

  for (const lead of leads) {
    const existingEnrollment = await prisma.sequenceEnrollment.findUnique({
      where: { sequenceId_leadId: { sequenceId: sequence.id, leadId: lead.id } },
    });

    if (existingEnrollment) {
      // Completed/replied/bounced/stopped history is never deleted or rewritten.
      if (existingEnrollment.status === "PAUSED") {
        await prisma.sequenceEnrollment.update({
          where: { id: existingEnrollment.id },
          data: { status: "ACTIVE", nextRunAt: scheduledAt, email: lead.email },
        });
      }
      continue;
    }

    await prisma.sequenceEnrollment.create({
      data: {
        orgId,
        sequenceId: sequence.id,
        leadId: lead.id,
        email: lead.email,
        status: "ACTIVE",
        currentStep: 0,
        steps: campaignSteps,
        startedAt: scheduledAt,
        nextRunAt: scheduledAt,
      },
    });
  }

  await prisma.workflow.update({
    where: { id: latestCampaign.id },
    data: {
      active: true,
      conditions: {
        ...conditions,
        status: "running",
        schedule: scheduledAt.toISOString(),
        autoPaused: false,
        lastError: null,
      },
    },
  });

  invalidateCache("/campaigns");

  return {
    alreadyRunning: false,
    scheduledAt: scheduledAt.toISOString(),
    enrolled: leads.length,
  };
};

const launch = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({
    where: { id: Number(req.params.id), orgId: req.orgId },
  });
  if (!campaign) throw new AppError("Campaign not found.", 404);

  const conditions =
    typeof campaign.conditions === "object" && campaign.conditions
      ? campaign.conditions
      : {};
  const scheduledAt = conditions.schedule ? new Date(conditions.schedule) : null;

  if (!scheduledAt || Number.isNaN(scheduledAt.getTime())) {
    throw new AppError("A valid campaign schedule date and time is required.", 400);
  }
  if (scheduledAt.getTime() < Date.now()) {
    throw new AppError("Campaign schedule must be in the future.", 400);
  }

  await prisma.workflow.update({
    where: { id: campaign.id },
    data: {
      active: false,
      conditions: {
        ...conditions,
        status: "scheduled",
        autoPaused: false,
        lastError: null,
      },
    },
  });

  invalidateCache("/campaigns");

  return response.success(res, {
    message: "Campaign scheduled.",
    scheduledAt: scheduledAt.toISOString(),
    enrolled: 0,
  });
});

const pause = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({
    where: {
      id: Number(req.params.id),
      orgId: req.orgId,
    },
  });

  if (!campaign) {
    throw new AppError("Campaign not found.", 404);
  }

  const sequence = await prisma.sequence.findFirst({
    where: {
      orgId: req.orgId,
      name: `Campaign: ${campaign.name}`,
    },
    orderBy: {
      createdAt: "desc",
    },
  });

  await prisma.workflow.update({
    where: {
      id: campaign.id,
    },
    data: {
  active: false,
  conditions: {
    ...(typeof campaign.conditions === "object" && campaign.conditions
      ? campaign.conditions
      : {}),
    status: "paused",
  },
},
  });

  if (sequence) {
    await prisma.sequenceEnrollment.updateMany({
      where: {
        sequenceId: sequence.id,
        status: "ACTIVE",
      },
      data: {
        status: "PAUSED",
      },
    });

    await prisma.sequence.update({
      where: {
        id: sequence.id,
      },
      data: {
        status: "PAUSED",
      },
    });
  }

  invalidateCache("/campaigns");

  return response.success(res, {
    message: "Campaign paused.",
  });
});

const resume = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({
    where: {
      id: Number(req.params.id),
      orgId: req.orgId,
    },
  });

  if (!campaign) {
    throw new AppError("Campaign not found.", 404);
  }

  const sequence = await prisma.sequence.findFirst({
    where: {
      orgId: req.orgId,
      name: `Campaign: ${campaign.name}`,
    },
    orderBy: {
      createdAt: "desc",
    },
  });

 await prisma.workflow.update({
  where: {
    id: campaign.id,
  },
  data: {
    active: true,
    conditions: {
      ...(typeof campaign.conditions === "object" && campaign.conditions
        ? campaign.conditions
        : {}),
      status: "running",
    },
  },
});

  if (sequence) {
    await prisma.sequenceEnrollment.updateMany({
      where: {
        sequenceId: sequence.id,
        status: "PAUSED",
      },
      data: {
        status: "ACTIVE",
      },
    });

    await prisma.sequence.update({
      where: {
        id: sequence.id,
      },
      data: {
        status: "ACTIVE",
      },
    });
  }

  invalidateCache("/campaigns");

  return response.success(res, {
    message: "Campaign resumed.",
  });
});

const stop = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({
    where: {
      id: Number(req.params.id),
      orgId: req.orgId,
    },
  });

  if (!campaign) {
    throw new AppError("Campaign not found.", 404);
  }

  const sequence = await prisma.sequence.findFirst({
    where: {
      orgId: req.orgId,
      name: `Campaign: ${campaign.name}`,
    },
    orderBy: {
      createdAt: "desc",
    },
  });

  await prisma.workflow.update({
    where: {
      id: campaign.id,
    },
    data: {
      active: false,
      conditions: {
        ...(typeof campaign.conditions === "object" && campaign.conditions
          ? campaign.conditions
          : {}),
        status: "cancelled",
      },
    },
  });

  if (sequence) {
    await prisma.sequenceEnrollment.updateMany({
      where: {
        sequenceId: sequence.id,
        status: {
          in: ["ACTIVE", "PAUSED"],
        },
      },
      data: {
        status: "STOPPED",
      },
    });

    await prisma.sequence.update({
      where: {
        id: sequence.id,
      },
      data: {
        status: "ARCHIVED",
      },
    });
  }

  invalidateCache("/campaigns");

  return response.success(res, {
    message: "Campaign stopped.",
  });
});

const metrics = asyncHandler(async (req, res) => {
  const campaigns = await prisma.workflow.findMany({
    where: { orgId: req.orgId },
    select: {
      id: true,
      active: true,
      conditions: true,
      runCount: true,
      lastRunAt: true,
      trigger: true,
    },
  });

  let running = 0;
  let paused = 0;
  let totalRuns = 0;

  for (const c of campaigns) {
    const status =
      typeof c.conditions === "object" && c.conditions
        ? c.conditions.status
        : null;

    if (status === "running") running++;
    if (status === "paused") paused++;

    totalRuns += c.runCount || 0;
  }

  return response.success(res, {
    total: campaigns.length,
    running,
    paused,
    totalRuns,
  });
});
const optimization = asyncHandler(async (req, res) => {
  const campaigns = await prisma.workflow.findMany({
    where: { orgId: req.orgId },
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      name: true,
      active: true,
      conditions: true,
    },
  });

  const sequences = await prisma.sequence.findMany({
    where: { orgId: req.orgId },
    select: {
      id: true,
      name: true,
      workflowId: true,
    },
  });

  const sequenceByName = new Map(
    sequences.map((sequence) => [sequence.name, sequence])
  );
  const sequenceByWorkflow = new Map(
    sequences.filter((s) => s.workflowId).map((s) => [s.workflowId, s])
  );

  const pct = (n, d) => (d > 0 ? Math.round((n / d) * 100) : 0);
  const results = [];

  for (const campaign of campaigns) {
    const sequence =
      sequenceByWorkflow.get(campaign.id) ||
      sequenceByName.get(`Campaign: ${campaign.name}`);

    const conditions = campaign.conditions || {};
    const status = campaign.active
      ? "running"
      : conditions.status === "completed"
        ? "completed"
        : conditions.status === "scheduled"
          ? "scheduled"
          : conditions.status === "paused"
            ? "paused"
            : conditions.status === "cancelled"
              ? "stopped"
              : "draft";

    const base = {
      campaignId: campaign.id,
      campaignName: campaign.name,
      sequenceId: sequence?.id || null,
      status,
      enrolled: 0,
      enrolledByStatus: {},
      sent: 0,
      delivered: 0,
      opened: 0,
      clicked: 0,
      replied: 0,
      bounced: 0,
      openRate: 0,
      clickRate: 0,
      replyRate: 0,
      bounceRate: 0,
      lastSentAt: null,
      recommendations: [],
    };

    if (!sequence) {
      base.recommendations.push("Launch this campaign to start sending emails.");
      results.push(base);
      continue;
    }

    const enrollGroups = await prisma.sequenceEnrollment.groupBy({
      by: ["status"],
      where: { sequenceId: sequence.id },
      _count: { _all: true },
    });
    for (const g of enrollGroups) {
      base.enrolledByStatus[g.status] = g._count._all;
      base.enrolled += g._count._all;
    }

    // Emails sent before attribution metadata existed carry the campaign name as
    // subject and the enrolled lead's address as recipient, so match those too.
    const enrolledEmails = (
      await prisma.sequenceEnrollment.findMany({
        where: { sequenceId: sequence.id },
        select: { email: true },
      })
    ).map((e) => e.email);

    const sentEvents = await prisma.emailEvent.findMany({
      where: {
        orgId: req.orgId,
        type: "SENT",
        OR: [
          { metadata: { path: ["sequenceId"], equals: sequence.id } },
          ...(enrolledEmails.length
            ? [{ subject: campaign.name, recipient: { in: enrolledEmails } }]
            : []),
        ],
      },
      select: {
        id: true,
        messageId: true,
        createdAt: true,
      },
    });

    if (sentEvents.length === 0) {
      base.recommendations.push(
        base.enrolled > 0
          ? "Leads are enrolled; emails will appear here as soon as they are sent."
          : "No attributed email data yet."
      );
      results.push(base);
      continue;
    }

    const messageIds = sentEvents.map((e) => e.messageId).filter(Boolean);

    const engagementEvents = await prisma.emailEvent.findMany({
      where: {
        orgId: req.orgId,
        messageId: { in: messageIds },
        type: {
          in: ["DELIVERED", "OPENED", "CLICKED", "REPLIED", "BOUNCED"],
        },
      },
      select: {
        messageId: true,
        type: true,
      },
    });

    const uniqueByType = (type) =>
      new Set(
        engagementEvents
          .filter((event) => event.type === type && event.messageId)
          .map((event) => event.messageId)
      ).size;

    const sent = sentEvents.length;
    const opened = uniqueByType("OPENED");
    const clicked = uniqueByType("CLICKED");
    const replied = uniqueByType("REPLIED");
    const bounced = uniqueByType("BOUNCED");
    const delivered = Math.max(uniqueByType("DELIVERED"), sent - bounced);

    const openRate = pct(opened, sent);
    const clickRate = pct(clicked, sent);
    const replyRate = pct(replied, sent);
    const bounceRate = pct(bounced, sent);

    const recommendations = [];

    if (bounceRate >= 5) {
      recommendations.push(
        "High bounce rate: verify emails before sending and remove invalid addresses."
      );
    }

    if (openRate < 20) {
      recommendations.push(
        "Test stronger or more personalized subject lines."
      );
    }

    if (openRate >= 20 && clickRate < 5) {
      recommendations.push(
        "Improve email body relevance and strengthen the call to action."
      );
    }

    if (clickRate >= 5 && replyRate < 3) {
      recommendations.push(
        "Add a clearer conversational CTA to encourage replies."
      );
    }

    if (replyRate >= 3) {
      recommendations.push(
        "This campaign is generating replies; consider expanding its audience."
      );
    }

    if (recommendations.length === 0) {
      recommendations.push(
        "Continue monitoring performance and test one variable at a time."
      );
    }

    results.push({
      ...base,
      sent,
      delivered,
      opened,
      clicked,
      replied,
      bounced,
      openRate,
      clickRate,
      replyRate,
      bounceRate,
      lastSentAt: sentEvents.reduce(
        (max, e) => (e.createdAt > max ? e.createdAt : max),
        sentEvents[0].createdAt
      ),
      recommendations,
    });
  }

  const sum = (key) => results.reduce((acc, c) => acc + (c[key] || 0), 0);
  const totals = {
    campaigns: results.length,
    running: results.filter((c) => c.status === "running").length,
    enrolled: sum("enrolled"),
    sent: sum("sent"),
    opened: sum("opened"),
    clicked: sum("clicked"),
    replied: sum("replied"),
    bounced: sum("bounced"),
  };
  totals.openRate = pct(totals.opened, totals.sent);
  totals.clickRate = pct(totals.clicked, totals.sent);
  totals.replyRate = pct(totals.replied, totals.sent);
  totals.bounceRate = pct(totals.bounced, totals.sent);

  return response.success(res, {
    campaigns: results,
    totals,
    generatedAt: new Date(),
  });
});
const getEnrolledLeads = asyncHandler(async (req, res) => {
  const campaign = await prisma.workflow.findFirst({
    where: { id: Number(req.params.id), orgId: req.orgId },
  });
  if (!campaign) throw new AppError("Campaign not found.", 404);

  const sequence = await prisma.sequence.findFirst({
    where: {
      OR: [
        { workflowId: campaign.id },
        { orgId: req.orgId, name: `Campaign: ${campaign.name}` },
      ],
    },
  });

  if (!sequence) {
    return response.success(res, { campaignName: campaign.name, leads: [] });
  }

  const enrollments = await prisma.sequenceEnrollment.findMany({
    where: { sequenceId: sequence.id },
    orderBy: { createdAt: "desc" },
  });

  const leadIds = enrollments.map((e) => e.leadId).filter(Boolean);
  const leads = leadIds.length
    ? await prisma.lead.findMany({
        where: { id: { in: leadIds } },
        select: { id: true, name: true, email: true, status: true, companyName: true },
      })
    : [];
  const leadById = new Map(leads.map((l) => [l.id, l]));

  const enrolledEmails = enrollments.map((e) => e.email).filter(Boolean);
  const sentEvents = enrolledEmails.length
    ? await prisma.emailEvent.findMany({
        where: {
          orgId: req.orgId,
          type: "SENT",
          recipient: { in: enrolledEmails },
          OR: [
            { metadata: { path: ["sequenceId"], equals: sequence.id } },
            { subject: campaign.name },
          ],
        },
        select: { recipient: true, createdAt: true },
      })
    : [];
  const sentByEmail = new Map();
  for (const ev of sentEvents) {
    const cur = sentByEmail.get(ev.recipient) || { count: 0, last: null };
    cur.count += 1;
    if (!cur.last || ev.createdAt > cur.last) cur.last = ev.createdAt;
    sentByEmail.set(ev.recipient, cur);
  }

  const result = enrollments.map((enrollment) => {
    const lead = enrollment.leadId ? leadById.get(enrollment.leadId) : null;
    const sentInfo = sentByEmail.get(enrollment.email);
    return {
      emailsSent: sentInfo?.count || 0,
      lastSentAt: sentInfo?.last || null,
      enrollmentId: enrollment.id,
      leadId: enrollment.leadId,
      name: lead?.name || null,
      email: enrollment.email,
      companyName: lead?.companyName || null,
      leadStatus: lead?.status || null,
      enrollmentStatus: enrollment.status,
      currentStep: enrollment.currentStep,
      totalSteps: Array.isArray(enrollment.steps) ? enrollment.steps.length : 0,
      startedAt: enrollment.startedAt,
      completedAt: enrollment.completedAt,
    };
  });

  return response.success(res, { campaignName: campaign.name, leads: result });
});

const generateDrafts = asyncHandler(async (req, res) => {
  const { campaignName, prompt, tone, goal, valueProposition, audienceLabel, lead } = req.body || {};
  if (typeof prompt !== "string" || prompt.trim().length < 3) {
    throw new AppError("Enter a prompt or a few keywords before generating drafts.", 400);
  }
  if (prompt.length > 4000) throw new AppError("Campaign prompt must be 4,000 characters or fewer.", 400);
  const drafts = await generateCampaignDraftOptions({
    campaignName: String(campaignName || "").slice(0, 160),
    prompt: prompt.trim(),
    tone,
    goal,
    valueProposition: String(valueProposition || "").slice(0, 1000),
    audienceLabel: String(audienceLabel || "").slice(0, 200),
    lead: lead && typeof lead === "object" ? lead : null,
  });
  return response.success(res, { drafts });
});


module.exports = {
  copyPreview,
  generateDrafts,
  audiencePreview,
  activateCampaign,
  list,
  get,
  create,
  update,
  remove,
  launch,
  pause,
  resume,
  stop,
  metrics,
  optimization,
  getEnrolledLeads,
  CAMPAIGN_STATUSES,
  CAMPAIGN_TYPES
};
