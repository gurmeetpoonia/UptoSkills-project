const { prisma } = require("../config/postgres");
const { AppError } = require("../middleware/errorHandler");
const asyncHandler = require("../utils/asyncHandler");
const response = require("../utils/response");
const slugify = require("../utils/slugify");
const { incrementUsage } = require("../services/usageService");
const { enrollLeadInActiveCampaigns } = require("../services/campaignAutomationService");

// Every query in this controller is scoped to the caller's organization.
const getOrgId = (req) => {
  const orgId = req.orgId || req.user?.orgId || req.user?.organizationId;
  if (!orgId) throw new AppError("Organization context is required.", 403);
  return Number(orgId);
};

// Campaign enrollment is a side effect: it must never turn a successful
// tag operation into a 500.
const safeEnroll = async (lead, orgId, userId) => {
  try {
    await enrollLeadInActiveCampaigns(lead, orgId, userId);
  } catch (err) {
    console.error("[tagController] enrollLeadInActiveCampaigns failed:", err.message);
  }
};

// 1. List: only tags of the caller's organization
const list = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const items = await prisma.tag.findMany({
    where: { orgId },
    orderBy: { name: "asc" },
    include: { _count: { select: { leads: true } } },
  });
  return response.success(res, items);
});

// 2. Create: attach orgId and userId to the new tag
const create = asyncHandler(async (req, res) => {
  const { name, color } = req.body;
  if (!name) throw new AppError("Tag name is required.", 400);
  const orgId = getOrgId(req);
  const slug = slugify(name);
  try {
    const tag = await prisma.tag.create({
      data: {
        name,
        slug,
        color: color || "#3b82f6",
        orgId,
        userId: req.user?.id || null,
      },
    });
    if (req.user?.id) {
      await incrementUsage({ userId: req.user.id, orgId, resource: "tags" }).catch(() => {});
    }
    return response.created(res, tag);
  } catch (error) {
    if (error.code === "P2002") throw new AppError("A tag with this name already exists.", 409);
    throw error;
  }
});

// 3. Update: only within the caller's organization
const update = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const { name, color } = req.body;
  const data = {};
  if (name !== undefined) {
    data.name = name;
    data.slug = slugify(name);
  }
  if (color !== undefined) data.color = color;

  const result = await prisma.tag.updateMany({
    where: { id: Number(req.params.id), orgId },
    data,
  });
  if (result.count === 0) throw new AppError("Tag not found.", 404);
  return response.success(res, { message: "Tag updated." });
});

// 4. Remove: only within the caller's organization
const remove = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const result = await prisma.tag.deleteMany({
    where: { id: Number(req.params.id), orgId },
  });
  if (result.count === 0) throw new AppError("Tag not found.", 404);
  return response.success(res, { message: "Tag removed." });
});

// 5. AttachToLead: lead and tag must both belong to the caller's organization
const attachToLead = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const { leadId } = req.params;
  const { tagId } = req.body;

  const lead = await prisma.lead.findFirst({
    where: { id: Number(leadId), orgId },
  });
  if (!lead) throw new AppError("Lead not found.", 404);

  const tag = await prisma.tag.findFirst({
    where: { id: Number(tagId), orgId },
  });
  if (!tag) throw new AppError("Tag not found.", 404);

  await prisma.leadTag.upsert({
    where: { leadId_tagId: { leadId: lead.id, tagId: tag.id } },
    create: { leadId: lead.id, tagId: tag.id },
    update: {},
  });

  // Re-check active campaigns (never fails the request)
  await safeEnroll(lead, orgId, req.user.id);

  return response.success(res, { message: "Tag attached." });
});

// 6. DetachFromLead
const detachFromLead = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const { leadId, tagId } = req.params;

  const lead = await prisma.lead.findFirst({
    where: { id: Number(leadId), orgId },
  });
  if (!lead) throw new AppError("Lead not found.", 404);

  await prisma.leadTag.deleteMany({
    where: { leadId: lead.id, tagId: Number(tagId) },
  });

  await safeEnroll(lead, orgId, req.user.id);

  return response.success(res, { message: "Tag detached." });
});

// 7. ListForLead
const listForLead = asyncHandler(async (req, res) => {
  const orgId = getOrgId(req);
  const { leadId } = req.params;

  const lead = await prisma.lead.findFirst({
    where: { id: Number(leadId), orgId },
    select: { id: true },
  });
  if (!lead) throw new AppError("Lead not found.", 404);

  const items = await prisma.leadTag.findMany({
    where: { leadId: lead.id },
    include: { tag: true },
  });
  return response.success(res, items.map((i) => i.tag));
});

module.exports = { list, create, update, remove, attachToLead, detachFromLead, listForLead };