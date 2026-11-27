// Leads page: "Upload Excel / Run Scraper".
// The browser only talks to this API. The scraper service URL stays on the server.
//   POST /api/leads/ingest              upload a .xlsx / .xls / .csv, start the scraper pipeline
//   GET  /api/leads/ingest/:jobId       live status, counts and rows (qualified / rejected / ...)
//   POST /api/leads/ingest/:jobId/save  save the qualified leads in the CRM (once)
const axios = require("axios");
const { redisClient } = require("../config/redis");
const { prisma } = require("../config/postgres");
const { recordActivity } = require("../services/leadActivityService");
const { enrollLeadInActiveCampaigns } = require("../services/campaignAutomationService");
const { tagLead } = require("../services/autoTagService");
const { markAdded } = require("../services/findLeadCandidateService");
const asyncHandler = require("../utils/asyncHandler");
const response = require("../utils/response");
const { AppError } = require("../middleware/errorHandler");

const SCRAPER_API_URL = (
  process.env.JOB_SCRAPER_URL ||
  process.env.SCRAPER_URL ||
  process.env.SCRAPER_API_URL ||
  "http://localhost:8000"
).replace(/\/+$/, "");

const ALLOWED_EXT = /\.(xlsx|xls|csv)$/i;
const MAX_BYTES = 5 * 1024 * 1024;
const TTL = 2 * 60 * 60; // seconds

// ---- tiny key/value store: Redis when connected, memory otherwise -------------
const memory = new Map();
const kvSet = async (key, value) => {
  const str = JSON.stringify(value);
  try {
    if (redisClient.isOpen) return void (await redisClient.set(key, str, { EX: TTL }));
  } catch (err) {
    console.warn("ingest: redis set failed, using memory:", err.message);
  }
  memory.set(key, { str, at: Date.now() });
  for (const [k, v] of memory) if (Date.now() - v.at > TTL * 1000) memory.delete(k);
};
const kvGet = async (key) => {
  try {
    if (redisClient.isOpen) {
      const str = await redisClient.get(key);
      if (str) return JSON.parse(str);
    }
  } catch (err) {
    console.warn("ingest: redis get failed, using memory:", err.message);
  }
  const hit = memory.get(key);
  return hit ? JSON.parse(hit.str) : null;
};

const scraperDown = () =>
  new AppError("The scraper service is not reachable right now. Check that it is running and try again.", 503);

// Map a failed call to the scraper onto a clear API error.
const scraperError = (err, fallback) => {
  if (err.response) {
    if (err.response.status === 404)
      return new AppError("The scraper no longer has this job (it was restarted). Upload the file again.", 410);
    const detail = err.response.data?.detail;
    return new AppError(typeof detail === "string" ? detail : fallback, err.response.status === 413 ? 413 : 502);
  }
  return scraperDown();
};

// 1. POST /api/leads/ingest   (multipart field "file")
const startIngest = asyncHandler(async (req, res) => {
  const file = req.file;
  if (!file) throw new AppError("Choose a .xlsx, .xls or .csv file to upload.", 400);
  if (!ALLOWED_EXT.test(file.originalname || ""))
    throw new AppError("Unsupported file type. Upload a .xlsx, .xls or .csv file.", 400);
  if (!file.size) throw new AppError("The file is empty.", 400);
  if (file.size > MAX_BYTES) throw new AppError("The file is larger than 5 MB.", 413);

  let data;
  try {
    ({ data } = await axios.post(
      `${SCRAPER_API_URL}/ingest`,
      { filename: file.originalname, content_base64: file.buffer.toString("base64") },
      { timeout: 30000, maxBodyLength: Infinity, maxContentLength: Infinity }
    ));
  } catch (err) {
    console.error("Ingest start failed:", err.message);
    throw scraperError(err, "The scraper rejected the file.");
  }
  const jobId = data.job_id;
  await kvSet(`ingest-owner:${jobId}`, { orgId: req.orgId, userId: req.user.id, filename: file.originalname });
  return response.success(res, { jobId, filename: file.originalname });
});

const assertOwner = async (req) => {
  const owner = await kvGet(`ingest-owner:${req.params.jobId}`);
  if (!owner || owner.orgId !== req.orgId) throw new AppError("Upload job not found", 404);
  return owner;
};

const recount = (rows) => {
  const by = (s) => rows.filter((r) => r.status === s).length;
  return { qualified: by("qualified"), phone_only: by("phone_only"), rejected: by("rejected"), duplicates: by("duplicate") };
};

// Qualified rows whose email is already a CRM lead become duplicates (emails are unique).
const markExisting = async (rows) => {
  const emails = [...new Set(rows.filter((r) => r.status === "qualified").map((r) => r.email))];
  if (!emails.length) return rows;
  const found = await prisma.lead.findMany({ where: { email: { in: emails } }, select: { email: true } });
  const known = new Set(found.map((l) => l.email.toLowerCase()));
  return rows.map((r) =>
    r.status === "qualified" && known.has(r.email)
      ? { ...r, status: "duplicate", reasons: [...r.reasons, "Already in the CRM"] }
      : r
  );
};

// 2. GET /api/leads/ingest/:jobId
const getIngestStatus = asyncHandler(async (req, res) => {
  const { jobId } = req.params;
  const owner = await assertOwner(req);

  const cached = await kvGet(`ingest-result:${jobId}`);
  let job = cached;
  if (!job) {
    try {
      ({ data: job } = await axios.get(`${SCRAPER_API_URL}/ingest/${jobId}`, { timeout: 15000 }));
    } catch (err) {
      throw scraperError(err, "Could not read the processing status.");
    }
    if (job.status === "done") {
      const rows = await markExisting(job.rows || []);
      job = { ...job, rows, summary: { ...job.summary, ...recount(rows) } };
      await kvSet(`ingest-result:${jobId}`, job);
    }
  }

  const saved = await kvGet(`ingest-saved:${jobId}`);
  return response.success(res, {
    jobId,
    filename: owner.filename,
    status: job.status,
    processed: job.processed || 0,
    total: job.total || 0,
    summary: job.summary || null,
    rows: job.status === "done" ? job.rows : [],
    warnings: job.warnings || [],
    error: job.error || null,
    errorCode: job.error_code || null,
    savedRows: saved?.rows || [],
  });
});

// 3. POST /api/leads/ingest/:jobId/save   body: { rows?: [excelRowNumber, ...] }
// Saves the chosen qualified rows (all qualified rows when `rows` is omitted). Safe to call again:
// rows that were already saved are skipped, so nothing is added twice.
const saveIngest = asyncHandler(async (req, res) => {
  const { jobId } = req.params;
  await assertOwner(req);

  const job = await kvGet(`ingest-result:${jobId}`);
  if (!job || job.status !== "done") throw new AppError("Processing has not finished yet.", 409);

  const state = (await kvGet(`ingest-saved:${jobId}`)) || { rows: [] };
  const wanted = Array.isArray(req.body?.rows) ? new Set(req.body.rows.map(Number)) : null;
  const result = { created: 0, skipped: [], failed: [] };
  const handled = [];

  for (const row of job.rows.filter((r) => r.status === "qualified")) {
    if (state.rows.includes(row.row) || (wanted && !wanted.has(row.row))) continue;
    try {
      if (await prisma.lead.findUnique({ where: { email: row.email } })) {
        result.skipped.push({ row: row.row, email: row.email, reason: "Already in the CRM" });
        handled.push(row);
        continue;
      }
      const lead = await prisma.lead.create({
        data: {
          name: row.name,
          email: row.email,
          companyName: row.company || null,
          jobTitle: row.title || null,
          location: row.location || null,
          score: row.score || 0,
          status: "new",
          source: "import",
          engagement: { upload: job.filename, emailStatus: row.email_status, phone: row.phone || null },
          orgId: req.orgId,
          addedById: req.user.id,
        },
      });
      result.created += 1;
      handled.push(row);
      await recordActivity({
        leadId: lead.id,
        userId: req.user.id,
        orgId: req.orgId,
        type: "CREATED",
        title: `${req.user.name} imported this lead from ${job.filename || "an uploaded file"}`,
      }).catch((e) => console.error("ingest activity failed:", e.message));
      await tagLead({
        leadId: lead.id,
        orgId: req.orgId,
        userId: req.user.id,
        names: ["Uploaded", "Source: Upload"],
      }).catch((e) => console.error("ingest tagging failed:", e.message));
      await enrollLeadInActiveCampaigns(lead, req.orgId, req.user.id).catch((e) =>
        console.error("ingest enrollment failed:", e.message)
      );
    } catch (err) {
      result.failed.push({ row: row.row, email: row.email, reason: err.message });
    }
  }

  // Keep the Find Leads list in step: these emails are in My Leads now.
  try {
    await markAdded(req.orgId, handled.map((r) => r.email));
  } catch (err) {
    console.warn("ingest: markAdded failed:", err.message);
  }
  state.rows = [...state.rows, ...handled.map((r) => r.row)];
  await kvSet(`ingest-saved:${jobId}`, state);
  return response.success(res, { ...result, savedRows: state.rows });
});

module.exports = { startIngest, getIngestStatus, saveIngest };
