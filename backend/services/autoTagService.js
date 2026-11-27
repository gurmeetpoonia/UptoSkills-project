// Auto-tags leads created by Find Leads so the Leads page "All Tags" filter has useful options.
const { prisma } = require("../config/postgres");

const slugify = (name) =>
  String(name)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const TAG_COLORS = {
  "HR Lead": "#14b8a6",
  "Find Leads": "#3b82f6",
  Verified: "#22c55e",
  Unverified: "#f59e0b",
};

// Tags for one Find Leads item (the scraper's annotated row, or a lead's stored engagement JSON).
const tagNamesFor = ({ verification, leadClass, source } = {}) => {
  const names = ["HR Lead", "Find Leads"];
  const v = String(verification || "").toLowerCase();
  if (v) names.push(/^(verified|valid|deliverable)/.test(v) ? "Verified" : "Unverified");
  const cls = String(leadClass || "").trim();
  if (cls && !/^(expired|duplicate)$/i.test(cls)) names.push(`Class: ${cls}`);
  const src = String(source || "").trim();
  if (src) names.push(`Source: ${src}`);
  return names;
};

const ensureTag = async ({ name, orgId, userId }) => {
  const slug = slugify(name);
  const existing = await prisma.tag.findFirst({ where: { orgId, slug } });
  if (existing) return existing;
  try {
    return await prisma.tag.create({
      data: { name, slug, color: TAG_COLORS[name] || "#6366f1", orgId, userId },
    });
  } catch (err) {
    // Lost a race with another request: read the winner.
    const again = await prisma.tag.findFirst({ where: { orgId, slug } });
    if (again) return again;
    throw err;
  }
};

const tagLead = async ({ leadId, orgId, userId, names }) => {
  const tags = [];
  for (const name of names) tags.push(await ensureTag({ name, orgId, userId }));
  if (!tags.length) return 0;
  const res = await prisma.leadTag.createMany({
    data: tags.map((t) => ({ leadId, tagId: t.id })),
    skipDuplicates: true,
  });
  return res.count;
};

module.exports = { tagNamesFor, tagLead, ensureTag };
