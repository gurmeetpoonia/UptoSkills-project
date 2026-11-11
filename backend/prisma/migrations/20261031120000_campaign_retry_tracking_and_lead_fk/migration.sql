-- Retry tracking for failed campaign sends (used by the follow-up job).
ALTER TYPE "EnrollmentStatus" ADD VALUE IF NOT EXISTS 'FAILED';

ALTER TABLE "sequence_enrollments"
ADD COLUMN IF NOT EXISTS "retryCount" INTEGER NOT NULL DEFAULT 0;

-- schema.prisma defines sequence_enrollments.leadId -> leads.id, but the earlier
-- migration did not create the foreign key. Add it only when it is missing, so
-- databases created with `prisma db push` (which already have it) are unaffected.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'sequence_enrollments_leadId_fkey'
  ) THEN
    -- Detach enrollments that point to leads that no longer exist, otherwise the
    -- constraint cannot be created. The enrollment row itself is kept.
    UPDATE "sequence_enrollments"
    SET "leadId" = NULL
    WHERE "leadId" IS NOT NULL
      AND "leadId" NOT IN (SELECT "id" FROM "leads");

    ALTER TABLE "sequence_enrollments"
    ADD CONSTRAINT "sequence_enrollments_leadId_fkey"
    FOREIGN KEY ("leadId") REFERENCES "leads"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;
