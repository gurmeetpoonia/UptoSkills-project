# Verification report

Date: 2026-10-31

This report lists only checks that were actually run, and says plainly what was **not** run.

## Checked

| Check | Result |
| --- | --- |
| Frontend production build (`npm run build`) | Pass |
| Syntax check (`node --check`) and `no-undef` lint of every backend file changed by this PR | Clean |
| Lint of every frontend file changed by this PR | Clean |
| Campaign automation unit tests (`backend/test/campaignAutomationService.test.js`) | 7 of 7 pass |
| Migration `20261031120000_campaign_retry_tracking_and_lead_fk` on a throw-away PostgreSQL 16 database (minimal copies of the affected tables) | Applies cleanly, is safe to run twice, detaches orphaned `leadId` values, creates the `leadId` foreign key, and the new `FAILED` status and `retryCount` column work |
| Campaigns page and Campaign Studio, run locally with `npm run dev` against a local database (by the PR author) | Page loads with the existing Campaign Optimization card and the new campaign list; Campaign Studio opens and shows two drafts |
| `prisma migrate status` / `prisma migrate diff` against that local database (by the PR author, 2026-10-30, before the retry migration was added) | Schema up to date, empty diff |

Note: the drafts seen in the local run were the built-in template fallback, because `GEMINI_API_KEY` was not set locally.

## Not checked

- The full backend test suite after the final changes. It needs `npx prisma generate` to have run; please run `npm test` in `backend`.
- `npx prisma validate` and `npx prisma format --check` (need `DATABASE_URL`, `DIRECT_URL` and `SHADOW_DATABASE_URL` to be set, as in CI).
- Running `npx prisma migrate deploy` with the new migration on a real database.
- The retry / `FAILED` behaviour of the follow-up job in a running server.
- Real email sending, Gemini-generated drafts, Google sign-in.
- Docker Compose startup and any Vercel or Render deployment.

## Migration notes

- `20260920000000_baseline_current_schema` is new. The first three migrations only create an early schema (14 tables), while `20260921215000` and later assume the full one, so `prisma migrate deploy` failed on an empty database (`type "EmailEventType" does not exist`). The baseline sits between them and creates/alters everything missing; it excludes what `20261001100000` adds so that migration still applies unchanged.
  - Checked on an empty PostgreSQL: all 7 migrations apply in order, and the resulting tables, columns, defaults, enums (values and order), indexes and constraints are identical to the schema Prisma generates from `schema.prisma`. This was done by applying each `migration.sql` with `psql` (one transaction per file), not with the real `prisma migrate deploy`, so please run `npx prisma migrate deploy` on an empty local database once and confirm.
  - Databases created with `prisma db push`: use `prisma migrate resolve --applied` (see README), do not run the baseline there.
  - The baseline drops `tags.description`, `tags.updatedAt` and `analytics_events.updatedAt` and replaces `tags.id` (TEXT to SERIAL). That is only relevant for a database that applied just the first three migrations and holds data in those tables.
- `20261001100000_add_campaign_sequence_relation` is unchanged from the version that was reviewed. It creates a unique index on `sequence_enrollments("sequenceId", "leadId")`. On a database that already has data, check for duplicates first:

  ```sql
  SELECT "sequenceId", "leadId", COUNT(*)
  FROM sequence_enrollments
  WHERE "leadId" IS NOT NULL
  GROUP BY "sequenceId", "leadId"
  HAVING COUNT(*) > 1;
  ```

  Remove or merge any rows this returns before running the migration.
- `20261031120000_campaign_retry_tracking_and_lead_fk` adds `EnrollmentStatus.FAILED`, `sequence_enrollments.retryCount`, and the missing `sequence_enrollments.leadId` foreign key. Enrollments that point to leads that no longer exist get `leadId = NULL` before the constraint is added; no rows are deleted.
- Deploy with `npx prisma migrate deploy`. CI, `render.yaml` and `docker-compose.yml` all use `migrate deploy`; nothing runs `prisma db push --accept-data-loss` anymore.

## Configuration

`SHADOW_DATABASE_URL` is referenced by `schema.prisma`; CI sets it in `.github/workflows/backend.yml`. Set it locally when running `prisma validate` or `prisma migrate dev`.
