
const axios = require("axios");
const { findLeadsQueue } = require("../queues/findLeadsQueue");
const { redisClient } = require("../config/redis");
const { prisma } = require("../config/postgres");
const { recordActivity } = require("../services/leadActivityService");
const { enrollLeadInActiveCampaigns } = require("../services/campaignAutomationService");
const { tagNamesFor, tagLead } = require("../services/autoTagService");
const { listCandidates, markAdded, dismissCandidates } = require("../services/findLeadCandidateService");
const asyncHandler = require("../utils/asyncHandler");
const response = require("../utils/response");
const { AppError } = require("../middleware/errorHandler");

const SCRAPER_API_URL = (
  process.env.JOB_SCRAPER_URL ||
  process.env.SCRAPER_URL ||
  process.env.SCRAPER_API_URL ||
  "http://localhost:8000"
).replace(/\/+$/, "");

// Generic mailbox names that should not be saved as individual HR contacts.
const GENERIC_EMAIL_NAMES = new Set([
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
  "sales",
  "marketing",
  "billing",
  "accounts",
  "account",
  "finance",
  "legal",
  "press",
  "media",
  "privacy",
  "abuse",
  "noreply",
  "no-reply",
  "webmaster",
  "postmaster",
  "feedback",
  "help",
  "service",
  "services",
  "customercare",
  "customer-care",
  "enquiries",
  "partners",
  "partnership",
  "business",
  "general",
  "reception",
]);

// ACCEPT_HR_MAILBOX=1: hr@, careers@, recruitment@ ... count as valid emails (same rule as the scraper).
// info@, support@, sales@ and the other shared mailboxes above are still rejected.
const ACCEPT_HR_MAILBOX = ["1", "true", "yes", "on"].includes(String(process.env.ACCEPT_HR_MAILBOX || "").toLowerCase());
const HR_ROLE_RE = /^(hr|careers?|jobs?|recruit[a-z]*|talent[a-z]*|hiring|people|humanresources)([._-][a-z0-9._-]+)?$/;

// Extract and validate an individual email from HR CONTACT.
const parseHrEmail = (hrContact) => {
  const emailRegex =
    /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

  const emailMatch = hrContact.match(emailRegex);

  if (!emailMatch) {
    return {
      email: null,
      reason: "No valid email address found in HR CONTACT",
    };
  }

  const email = emailMatch[0].trim().toLowerCase();

  // Check generic mailbox names, including plus-address variants.
  const localPart = email.split("@")[0].split("+")[0];

  if (GENERIC_EMAIL_NAMES.has(localPart) && !(ACCEPT_HR_MAILBOX && HR_ROLE_RE.test(localPart))) {
    return {
      email: null,
      reason: "Generic mailbox email is not accepted",
    };
  }

  return {
    email,
    reason: null,
  };
};

// 1. POST /api/leads/find
const findLeads = asyncHandler(async (req, res) => {
  const { searchQuery, searchType = "all" } = req.body;

  if (!searchQuery) {
    throw new AppError("searchQuery is required", 400);
  }

  let fastapiRes;

  try {
    fastapiRes = await axios.post(
      `${SCRAPER_API_URL}/scrape`,
      {
        query: searchQuery,
        search_type: searchType,
        limit: 10,
      },
      { timeout: 60000 }
    );
  } catch (error) {
    console.error("Scraper start failed:", error.message);

    throw new AppError(
      "Could not reach the scraper service. It may be waking up, please try again in a minute.",
      502
    );
  }

  const fastapiJobId = fastapiRes.data.job_id;

  const job = await findLeadsQueue.add("poll-fastapi", {
    fastapiJobId,
    orgId: req.orgId,
    searchType,
  });

  return response.success(res, { jobId: job.id });
});

// 1b. GET /api/leads/find/candidates?search=  (instant: read from the database, no scraper)
const getCandidates = asyncHandler(async (req, res) => {
  const result = await listCandidates(req.orgId, { search: req.query.search });
  return response.success(res, result);
});

// 1c. POST /api/leads/find/candidates/dismiss  { keys: [...] }  (delete from the Find Leads list)
const dismissFindCandidates = asyncHandler(async (req, res) => {
  const keys = Array.isArray(req.body?.keys) ? req.body.keys : [];
  if (keys.length === 0) throw new AppError("Select at least one lead to delete.", 400);
  const removed = await dismissCandidates(req.orgId, keys);
  return response.success(res, { removed });
});

// 2. GET /api/leads/find/:jobId
const getFindLeadsStatus = asyncHandler(async (req, res) => {
  const { jobId } = req.params;
  const job = await findLeadsQueue.getJob(jobId);

  if (!job) {
    throw new AppError("Job not found", 404);
  }

  const state = await job.getState();

  if (state === "completed") {
    const resultStr = await redisClient.get(
      `find-leads-result:${jobId}`
    );

    const allLeads = resultStr ? JSON.parse(resultStr) : [];
    const note = (await redisClient.get(`find-leads-note:${jobId}`)) || "";

    // Leads already saved in the CRM are not offered again.
    const emailOf = (l) => {
      const m = String(l["HR EMAIL"] || l["HR CONTACT"] || "").match(
        /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/
      );
      return m ? m[0].toLowerCase() : "";
    };
    const emails = [...new Set(allLeads.map(emailOf).filter(Boolean))];
    let known = new Set();
    if (emails.length) {
      try {
        const rows = await prisma.lead.findMany({
          where: { email: { in: emails } },
          select: { email: true },
        });
        known = new Set(rows.map((r) => r.email.toLowerCase()));
      } catch (err) {
        console.error("Could not check existing CRM leads:", err.message);
      }
    }
    const leads = allLeads.filter((l) => !known.has(emailOf(l)));

    return response.success(res, {
      status: "done",
      leads,
      note,
      alreadyInCrm: allLeads.length - leads.length,
    });
  }

  if (state === "failed") {
    return response.success(res, {
      status: "error",
      error: job.failedReason,
    });
  }

  return response.success(res, {
    status: "running",
  });
});

// 3. POST /api/leads/find/:jobId/confirm
const confirmFindLeads = asyncHandler(async (req, res) => {
  const { selectedLeads } = req.body;

  if (!Array.isArray(selectedLeads)) {
    throw new AppError("selectedLeads must be an array", 400);
  }

  const results = {
    created: [],
    skipped: [],
  };

  for (const item of selectedLeads) {
    if (!item || typeof item !== "object") {
      results.skipped.push({
        item,
        reason: "Invalid lead record",
      });
      continue;
    }

    // The intelligent tool already screened this lead in the scraper
    // service; never save one it rejected.
    if (item["TOOL_SELECTED"] === false) {
      results.skipped.push({
        item,
        reason:
          item["SELECTION_REASON"] ||
          "Not selected by the intelligent tool",
      });
      continue;
    }

    const hrContact = String(item["HR CONTACT"] || "").trim();

    const verification = String(
      item["VERIFICATION"] || ""
    ).toLowerCase();

    // Normalize status so both "Not Disclosed" and
    // "NotDisclosed" are recognized.
    const normalizedVerification = verification.replace(
      /[^a-z]/g,
      ""
    );

    const normalizedContact = hrContact.toLowerCase();

    // Reject missing, inferred, generic, and undisclosed contacts.
    if (
      !hrContact ||
      normalizedContact === "not disclosed" ||
      normalizedContact === "notdisclosed" ||
      /inferred\s*\(unverified\)/i.test(hrContact) ||
      /inferred\s*\(unverified\)/i.test(verification) ||
      verification.includes("generic email") ||
      normalizedVerification.includes("notdisclosed")
    ) {
      results.skipped.push({
        item,
        reason: "Missing, inferred, generic or undisclosed contact",
      });
      continue;
    }

    // Extract and validate the email independently on the backend.
    const { email: parsedEmail, reason } =
      parseHrEmail(hrContact);

    if (!parsedEmail) {
      const hasPhone = /\d{8,}/.test(String(item["HR PHONE"] || ""));
      results.skipped.push({
        item,
        reason: hasPhone
          ? "Phone-only lead: the CRM needs an email, kept for follow-up"
          : reason,
      });
      continue;
    }

    // Map scraper fields to CRM fields.
    const companyName = item["COMPANY"] || null;
    const jobTitle = item["JOB TITLE"] || null;
    const location = item["AREA / LOCATION"] || null;
    const score = item["SCORE"] || 0;

    // Use the HR person's own name (e.g. "Priyanka Pandita"); fall back to "HR — Company".
    const hrName = String(item["HR NAME"] || "").trim();
    const hasHrName = hrName && !/^not\s*disclosed$/i.test(hrName);
    const leadName = hasHrName
      ? hrName
      : companyName
        ? `HR — ${companyName}`
        : "HR — Unknown Company";

    // Preserve the original verification information.
    const engagement = {
      salary: item["SALARY"],
      verification: item["VERIFICATION"] || "Unverified",
      jobUrl: item["JOB URL"],
      fullDescription: item["FULL DESCRIPTION"],
      originalSource: item["SOURCE"],
      discovered: item["DISCOVERED"],
      selectionReason: item["SELECTION_REASON"],
      leadClass: item["LEAD_CLASS"],
      toolScore: item["TOOL_SCORE"],
      toolEngine: item["TOOL_ENGINE"],
      hrTitle: item["HR TITLE"],
    };

    try {
      // Check whether this email already exists.
      const existing = await prisma.lead.findUnique({
        where: {
          email: parsedEmail,
        },
      });

      if (existing) {
        results.skipped.push({
          item,
          reason: "Lead with this email already exists",
        });
        continue;
      }

      const lead = await prisma.lead.create({
        data: {
          name: leadName,
          email: parsedEmail,
          companyName,
          jobTitle,
          location,
          score,
          status: "new",
          source: "database_search",
          engagement,
          orgId: req.orgId,
          addedById: req.user.id,
        },
      });

      await recordActivity({
        leadId: lead.id,
        userId: req.user.id,
        orgId: req.orgId,
        type: "CREATED",
        title: `${req.user.name} created this lead via Find Leads`,
      });

      results.created.push(lead);
      try {
        await tagLead({
          leadId: lead.id,
          orgId: req.orgId,
          userId: req.user.id,
          names: tagNamesFor({
            verification: item["VERIFICATION"],
            leadClass: item["LEAD_CLASS"],
            source: item["SOURCE"],
          }),
        });
      } catch (tagErr) {
        console.error("Auto-tagging failed for lead", lead.id, tagErr.message);
      }
      try {
        await enrollLeadInActiveCampaigns(lead, req.orgId, req.user.id);
      } catch (enrollErr) {
        console.error("Campaign enrollment failed for lead", lead.id, enrollErr.message);
      }
    } catch (err) {
      results.skipped.push({
        item,
        reason: `DB Error: ${err.message}`,
      });
    }
  }

  try {
    await markAdded(
      req.orgId,
      results.created.map((l) => l.email)
    );
  } catch (markErr) {
    console.error("Could not mark Find Leads candidates as added:", markErr.message);
  }

  return response.success(res, results);
});

module.exports = {
  dismissFindCandidates,
  getCandidates,
  findLeads,
  getFindLeadsStatus,
  confirmFindLeads,
};
