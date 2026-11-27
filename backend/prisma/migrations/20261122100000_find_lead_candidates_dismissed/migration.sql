-- Find Leads: a lead the user deleted from the list stays hidden when discovery finds it again.
ALTER TABLE "find_lead_candidates" ADD COLUMN IF NOT EXISTS "dismissed" BOOLEAN NOT NULL DEFAULT false;
