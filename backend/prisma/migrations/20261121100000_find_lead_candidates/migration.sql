-- Find Leads candidates: saved so the list opens instantly and survives restarts.
CREATE TABLE IF NOT EXISTS "find_lead_candidates" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER NOT NULL,
    "emailKey" TEXT NOT NULL,
    "email" TEXT,
    "hrName" TEXT,
    "company" TEXT,
    "jobTitle" TEXT,
    "location" TEXT,
    "score" INTEGER NOT NULL DEFAULT 0,
    "isNew" BOOLEAN NOT NULL DEFAULT false,
    "addedToCrm" BOOLEAN NOT NULL DEFAULT false,
    "data" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "find_lead_candidates_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "find_lead_candidates_orgId_emailKey_key" ON "find_lead_candidates"("orgId", "emailKey");
CREATE INDEX IF NOT EXISTS "find_lead_candidates_orgId_addedToCrm_score_idx" ON "find_lead_candidates"("orgId", "addedToCrm", "score");

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'find_lead_candidates_orgId_fkey'
  ) THEN
    ALTER TABLE "find_lead_candidates"
    ADD CONSTRAINT "find_lead_candidates_orgId_fkey"
    FOREIGN KEY ("orgId") REFERENCES "organizations"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;
