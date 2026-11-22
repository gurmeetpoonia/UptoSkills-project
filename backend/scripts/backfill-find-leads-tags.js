// One-time: tag the Find Leads leads that already exist in the CRM.
// Run:  docker compose exec backend node scripts/backfill-find-leads-tags.js
require("dotenv").config();
const { prisma } = require("../config/postgres");
const { tagNamesFor, tagLead } = require("../services/autoTagService");

(async () => {
  const leads = await prisma.lead.findMany({
    where: { source: "database_search" },
    select: { id: true, orgId: true, addedById: true, engagement: true },
  });
  let tagged = 0;
  for (const lead of leads) {
    const e = lead.engagement || {};
    const names = tagNamesFor({
      verification: e.verification,
      leadClass: e.leadClass,
      source: e.originalSource,
    });
    tagged += await tagLead({ leadId: lead.id, orgId: lead.orgId, userId: lead.addedById, names });
  }
  console.log(`Find Leads leads: ${leads.length}, new tag links: ${tagged}`);
  await prisma.$disconnect();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
