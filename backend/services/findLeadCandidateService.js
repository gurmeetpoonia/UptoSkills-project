// Find Leads candidates live in the database, so opening Find Leads is one fast read
// instead of a scraper run. Discovery (background) only adds rows; the user decides what
// becomes a CRM lead.
const { prisma } = require("../config/postgres");

const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
const NEW_FOR_MS = 24 * 60 * 60 * 1000; // a discovered lead keeps its "New" badge for a day

const str = (v) => {
  const t = String(v == null ? "" : v).trim();
  return t && !/^not (disclosed|found)$/i.test(t) ? t : "";
};

const emailOf = (lead) => {
  const m = String(lead["HR EMAIL"] || lead["HR CONTACT"] || "").match(EMAIL_RE);
  return m ? m[0].toLowerCase() : "";
};

// One stable key per candidate: the HR email, else the job URL, else company + title.
const keyOf = (lead) =>
  emailOf(lead) ||
  str(lead["JOB URL"]).toLowerCase() ||
  `${str(lead["COMPANY"]).toLowerCase()}|${str(lead["JOB TITLE"]).toLowerCase()}`;

const toRow = (orgId, lead, isNew) => ({
  orgId,
  emailKey: keyOf(lead),
  email: emailOf(lead) || null,
  hrName: str(lead["HR NAME"]) || null,
  company: str(lead["COMPANY"]) || null,
  jobTitle: str(lead["JOB TITLE"]) || null,
  location: str(lead["AREA / LOCATION"]) || null,
  score: Math.round(Number(lead["TOOL_SCORE"] ?? lead["SCORE"] ?? 0)) || 0,
  isNew: !!isNew,
  data: lead,
});

// Save leads from a finished scraper job. Existing rows are left alone (2 queries in total).
const saveCandidates = async (orgId, leads, { markNew = false } = {}) => {
  if (!orgId || !Array.isArray(leads) || leads.length === 0) return { saved: 0 };
  const rows = [];
  const seen = new Set();
  for (const lead of leads) {
    if (!lead || typeof lead !== "object") continue;
    const row = toRow(orgId, lead, markNew);
    if (!row.emailKey || row.emailKey === "|" || seen.has(row.emailKey)) continue;
    seen.add(row.emailKey);
    rows.push(row);
  }
  if (rows.length === 0) return { saved: 0 };
  const res = await prisma.findLeadCandidate.createMany({ data: rows, skipDuplicates: true });
  return { saved: res.count };
};

// The list for the Find Leads screen: not yet in the CRM, best score first.
const listCandidates = async (orgId, { search = "" } = {}) => {
  const everSeeded = (await prisma.findLeadCandidate.count({ where: { orgId } })) > 0;
  const rows = await prisma.findLeadCandidate.findMany({
    where: { orgId, addedToCrm: false },
    orderBy: [{ score: "desc" }, { id: "asc" }],
    take: 2000,
  });

  // Hide (and remember) the ones that were added to the CRM in the meantime.
  const emails = [...new Set(rows.map((r) => r.email).filter(Boolean))];
  let known = new Set();
  if (emails.length) {
    const found = await prisma.lead.findMany({ where: { email: { in: emails } }, select: { email: true } });
    known = new Set(found.map((l) => l.email.toLowerCase()));
    if (known.size) {
      await prisma.findLeadCandidate.updateMany({
        where: { orgId, email: { in: [...known] } },
        data: { addedToCrm: true },
      });
    }
  }
  let visible = rows.filter((r) => !(r.email && known.has(r.email)));

  const q = String(search || "").trim().toLowerCase();
  if (q) {
    visible = visible.filter((r) =>
      [r.company, r.jobTitle, r.hrName, r.email, r.location].some((v) => String(v || "").toLowerCase().includes(q))
    );
  }

  // Best first: high / medium confidence (an email we can use), then phone-only, then the rest; score breaks ties.
  const RANK = { high: 0, medium: 1, low: 2, none: 3 };
  const rank = (r) => RANK[r.data?.CONFIDENCE] ?? (r.email ? 1 : 2);
  visible = [...visible].sort((a, b) => rank(a) - rank(b) || (b.score || 0) - (a.score || 0) || a.id - b.id);

  const now = Date.now();
  const leads = visible.map((r) => ({
    ...r.data,
    __new: r.isNew && now - new Date(r.createdAt).getTime() < NEW_FOR_MS,
  }));
  return { leads, total: leads.length, alreadyInCrm: known.size, seeded: everSeeded };
};

// After the user adds leads to the CRM they leave the Find Leads list.
const markAdded = async (orgId, emails) => {
  const list = [...new Set((emails || []).map((e) => String(e || "").toLowerCase()).filter(Boolean))];
  if (!orgId || list.length === 0) return 0;
  const res = await prisma.findLeadCandidate.updateMany({
    where: { orgId, email: { in: list } },
    data: { addedToCrm: true },
  });
  return res.count;
};

module.exports = { saveCandidates, listCandidates, markAdded, keyOf, emailOf };
