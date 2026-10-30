-- AlterTable
ALTER TABLE "sequence_enrollments" ADD COLUMN IF NOT EXISTS "orgId" INTEGER;

-- AlterTable
ALTER TABLE "sequences" ADD COLUMN IF NOT EXISTS "workflowId" INTEGER;

-- CreateIndex
CREATE INDEX IF NOT EXISTS "sequence_enrollments_orgId_idx" ON "sequence_enrollments"("orgId");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "sequence_enrollments_leadId_idx" ON "sequence_enrollments"("leadId");

-- [FIX ITEM 8]: Cleanup duplicate (sequenceId, leadId) pairs before creating unique index
DELETE FROM "sequence_enrollments" a USING "sequence_enrollments" b
WHERE a.id < b.id
  AND a."sequenceId" = b."sequenceId"
  AND a."leadId" = b."leadId";

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "sequence_enrollments_sequenceId_leadId_key"
ON "sequence_enrollments"("sequenceId", "leadId");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "sequences_workflowId_key"
ON "sequences"("workflowId");

-- AddForeignKey: sequences -> workflows
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'sequences_workflowId_fkey'
  ) THEN
    ALTER TABLE "sequences"
    ADD CONSTRAINT "sequences_workflowId_fkey"
    FOREIGN KEY ("workflowId") REFERENCES "workflows"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

-- AddForeignKey: sequence_enrollments -> organizations
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'sequence_enrollments_orgId_fkey'
  ) THEN
    ALTER TABLE "sequence_enrollments"
    ADD CONSTRAINT "sequence_enrollments_orgId_fkey"
    FOREIGN KEY ("orgId") REFERENCES "organizations"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

-- [FIX ITEM 8]: Add missing ForeignKey on sequence_enrollments.leadId referencing leads(id)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'sequence_enrollments_leadId_fkey'
  ) THEN
    ALTER TABLE "sequence_enrollments"
    ADD CONSTRAINT "sequence_enrollments_leadId_fkey"
    FOREIGN KEY ("leadId") REFERENCES "leads"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;