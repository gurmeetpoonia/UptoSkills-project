-- Baseline migration.
--
-- The first three migrations (20260312142204_init, 20260320101248_add_updated_at,
-- 20260413181103_init) only describe an early version of the schema (14 tables). Every later
-- migration assumes the rest of the schema exists, because the project was provisioned with
-- `prisma db push`. On an empty database `prisma migrate deploy` therefore failed at
-- 20260921215000 with: type "EmailEventType" does not exist.
--
-- This migration brings a database that is at the state of those first three migrations
-- up to the schema that 20260921215000 and the later migrations expect. It creates everything
-- that was missing and alters the old tables.
--
-- It deliberately does NOT contain what 20261001100000_add_campaign_sequence_relation adds
-- (sequence_enrollments.orgId, sequences.workflowId, their indexes and foreign keys), so that
-- migration still applies cleanly afterwards.
--
-- Existing databases that were created with `prisma db push` already have all of this. Do not
-- run it there; mark it as applied instead:
--   npx prisma migrate resolve --applied 20260920000000_baseline_current_schema
--
-- Note: the old tables are empty on a fresh database, so the column changes below are safe. A
-- database that applied only the first three migrations and holds data in `tags`
-- (id, description) or `analytics_events` (updatedAt) would lose that data.

-- CreateEnum (new types)
CREATE TYPE "OrgRole" AS ENUM ('OWNER', 'ADMIN', 'MEMBER', 'VIEWER');

CREATE TYPE "OrgPlan" AS ENUM ('FREE', 'STARTER', 'PRO', 'ENTERPRISE');

CREATE TYPE "OrgStatus" AS ENUM ('ACTIVE', 'TRIALING', 'PAST_DUE', 'CANCELED');

CREATE TYPE "SubscriptionStatus" AS ENUM ('ACTIVE', 'TRIALING', 'PAST_DUE', 'CANCELED', 'INCOMPLETE');

CREATE TYPE "PaymentStatus" AS ENUM ('SUCCEEDED', 'PENDING', 'FAILED', 'REFUNDED');

CREATE TYPE "TaskStatus" AS ENUM ('TODO', 'IN_PROGRESS', 'DONE', 'CANCELED');

CREATE TYPE "TaskPriority" AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'URGENT');

CREATE TYPE "ActivityType" AS ENUM ('CREATED', 'UPDATED', 'STATUS_CHANGED', 'ASSIGNED', 'NOTE_ADDED', 'TASK_CREATED', 'TASK_COMPLETED', 'EMAIL_SENT', 'CALL_MADE', 'MEETING_SCHEDULED', 'SCORE_CHANGED', 'TAG_ADDED', 'TAG_REMOVED');

CREATE TYPE "WebhookEvent" AS ENUM ('LEAD_CREATED', 'LEAD_UPDATED', 'LEAD_DELETED', 'LEAD_STATUS_CHANGED', 'DEAL_CREATED', 'DEAL_UPDATED', 'ORGANIZATION_CREATED', 'USER_INVITED', 'USER_JOINED', 'PAYMENT_SUCCEEDED', 'PAYMENT_FAILED', 'SUBSCRIPTION_UPDATED', 'SEARCH_COMPLETED', 'INTEGRATION_SYNCED');

CREATE TYPE "ActivityEntityType" AS ENUM ('LEAD', 'DEAL', 'CONTACT', 'COMPANY', 'ORGANIZATION');

CREATE TYPE "ActivityKind" AS ENUM ('CALL', 'MEETING', 'TASK', 'EMAIL_SENT', 'EMAIL_RECEIVED', 'NOTE', 'LINKEDIN', 'WHATSAPP', 'SMS');

CREATE TYPE "ActivityStatus" AS ENUM ('SCHEDULED', 'COMPLETED', 'CANCELED', 'OVERDUE', 'IN_PROGRESS');

CREATE TYPE "SequenceStatus" AS ENUM ('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED');

CREATE TYPE "EnrollmentStatus" AS ENUM ('ACTIVE', 'PAUSED', 'COMPLETED', 'STOPPED', 'REPLIED', 'BOUNCED', 'FAILED');

CREATE TYPE "WorkflowTrigger" AS ENUM ('LEAD_CREATED', 'LEAD_STATUS_CHANGED', 'LEAD_SCORE_CHANGED', 'DEAL_CREATED', 'DEAL_STAGE_CHANGED', 'DEAL_WON', 'DEAL_LOST', 'ACTIVITY_COMPLETED', 'FORM_SUBMITTED', 'EMAIL_OPENED', 'EMAIL_REPLIED', 'SCHEDULED_TIME', 'WEBHOOK_RECEIVED');

CREATE TYPE "WorkflowAction" AS ENUM ('SEND_EMAIL', 'CREATE_TASK', 'UPDATE_FIELD', 'ASSIGN_OWNER', 'ADD_TAG', 'REMOVE_TAG', 'NOTIFY_USER', 'CREATE_DEAL', 'WEBHOOK', 'WAIT', 'BRANCH');

CREATE TYPE "QuoteStatus" AS ENUM ('DRAFT', 'SENT', 'VIEWED', 'ACCEPTED', 'REJECTED', 'EXPIRED', 'REVISED');

CREATE TYPE "DealOutcome" AS ENUM ('WON', 'LOST', 'POSTPONED', 'CANCELLED');

CREATE TYPE "LossReason" AS ENUM ('PRICE', 'COMPETITOR', 'NO_BUDGET', 'NO_DECISION', 'TIMING', 'NO_RESPONSE', 'FEATURES', 'RELATIONSHIP', 'OTHER');

CREATE TYPE "EmailEventType" AS ENUM ('SENT', 'DELIVERED', 'OPENED', 'CLICKED', 'BOUNCED', 'COMPLAINED', 'UNSUBSCRIBED', 'REPLIED');

-- AlterEnum "LeadSource" (recreate with the current values)
ALTER TYPE "LeadSource" RENAME TO "LeadSource_old";
CREATE TYPE "LeadSource" AS ENUM ('website', 'referral', 'social_media', 'email_campaign', 'cold_call', 'trade_show', 'partner', 'other', 'import', 'api', 'database_search', 'domain_search', 'email_search', 'social_search');
ALTER TABLE "leads" ALTER COLUMN "source" DROP DEFAULT;
ALTER TABLE "leads" ALTER COLUMN "source" TYPE "LeadSource" USING ("source"::text::"LeadSource");
ALTER TABLE "leads" ALTER COLUMN "source" SET DEFAULT 'other';
DROP TYPE "LeadSource_old";

-- AlterEnum "UserRole" (recreate with the current values)
ALTER TYPE "UserRole" RENAME TO "UserRole_old";
CREATE TYPE "UserRole" AS ENUM ('ADMIN', 'STARTUP', 'INVESTOR', 'OWNER', 'MEMBER', 'VIEWER');
ALTER TABLE "users" ALTER COLUMN "role" DROP DEFAULT;
ALTER TABLE "users" ALTER COLUMN "role" TYPE "UserRole" USING ("role"::text::"UserRole");
ALTER TABLE "users" ALTER COLUMN "role" SET DEFAULT 'MEMBER';
DROP TYPE "UserRole_old";

-- AlterTable (tables created by the first migrations)
ALTER TABLE "users" ADD COLUMN "failedLoginAttempts" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "users" ADD COLUMN "lockedUntil" TIMESTAMP(3);
ALTER TABLE "users" ADD COLUMN "lastLoginAt" TIMESTAMP(3);
ALTER TABLE "users" ADD COLUMN "lastLoginIp" TEXT;
ALTER TABLE "users" ADD COLUMN "twoFactorEnabled" BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE "users" ADD COLUMN "twoFactorSecret" TEXT;
ALTER TABLE "users" ADD COLUMN "twoFactorBackupCodes" TEXT;
ALTER TABLE "users" ADD COLUMN "customFields" JSONB DEFAULT '{}';
ALTER TABLE "users" ADD COLUMN "avatar" TEXT;
ALTER TABLE "users" ADD COLUMN "googleId" TEXT;
ALTER TABLE "users" ADD COLUMN "provider" TEXT;
ALTER TABLE "organizations" ADD COLUMN "slug" TEXT NOT NULL;
ALTER TABLE "organizations" ADD COLUMN "contactEmail" TEXT;
ALTER TABLE "organizations" ADD COLUMN "logo" TEXT;
ALTER TABLE "organizations" ADD COLUMN "plan" "OrgPlan" NOT NULL DEFAULT 'FREE';
ALTER TABLE "organizations" ADD COLUMN "status" "OrgStatus" NOT NULL DEFAULT 'TRIALING';
ALTER TABLE "organizations" ADD COLUMN "trialEndsAt" TIMESTAMP(3);
ALTER TABLE "leads" ADD COLUMN "orgId" INTEGER;
ALTER TABLE "leads" ADD COLUMN "assignedToId" INTEGER;
ALTER TABLE "tags" DROP CONSTRAINT "tags_pkey";
ALTER TABLE "tags" DROP COLUMN "id";
ALTER TABLE "tags" ADD COLUMN "id" SERIAL NOT NULL;
ALTER TABLE "tags" ADD CONSTRAINT "tags_pkey" PRIMARY KEY ("id");
ALTER TABLE "tags" DROP COLUMN "description";
ALTER TABLE "tags" DROP COLUMN "updatedAt";
ALTER TABLE "tags" ADD COLUMN "color" TEXT NOT NULL DEFAULT '#3b82f6';
ALTER TABLE "tags" ADD COLUMN "orgId" INTEGER;
ALTER TABLE "tags" ADD COLUMN "userId" INTEGER;
ALTER TABLE "deals" ADD COLUMN "orgId" INTEGER;
ALTER TABLE "deals" ADD COLUMN "title" TEXT;
ALTER TABLE "deals" ADD COLUMN "stageId" INTEGER;
ALTER TABLE "deals" ADD COLUMN "position" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "deals" ADD COLUMN "probability" INTEGER NOT NULL DEFAULT 50;
ALTER TABLE "deals" ADD COLUMN "expectedCloseAt" TIMESTAMP(3);
ALTER TABLE "deals" ADD COLUMN "closedAt" TIMESTAMP(3);
ALTER TABLE "deals" ADD COLUMN "source" TEXT;
ALTER TABLE "deals" ADD COLUMN "ownerId" INTEGER;
ALTER TABLE "analytics_events" DROP COLUMN "updatedAt";
ALTER TABLE "analytics_events" ADD COLUMN "orgId" INTEGER;
ALTER TABLE "analytics_events" ALTER COLUMN "type" TYPE TEXT USING ("type"::text);
ALTER TABLE "analytics_events" ADD COLUMN "resource" TEXT;
ALTER TABLE "analytics_events" ADD COLUMN "metadata" JSONB;
ALTER TABLE "notifications" ADD COLUMN "readAt" TIMESTAMP(3);
ALTER TABLE "email_searches" ADD COLUMN "userId" INTEGER;
ALTER TABLE "email_searches" ADD COLUMN "orgId" INTEGER;
ALTER TABLE "domain_searches" ADD COLUMN "userId" INTEGER;
ALTER TABLE "domain_searches" ADD COLUMN "orgId" INTEGER;
DROP TYPE "AnalyticsEventType";
DROP INDEX "tags_name_key";
DROP INDEX "tags_slug_key";

-- CreateTable (tables that no earlier migration created)
CREATE TABLE "org_memberships" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER NOT NULL,
    "role" "OrgRole" NOT NULL DEFAULT 'MEMBER',
    "joinedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "org_memberships_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "team_invites" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER NOT NULL,
    "email" TEXT NOT NULL,
    "role" "OrgRole" NOT NULL DEFAULT 'MEMBER',
    "token" TEXT NOT NULL,
    "invitedById" INTEGER NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "acceptedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "team_invites_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "sessions" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "ipAddress" TEXT,
    "userAgent" TEXT,
    "device" TEXT,
    "location" TEXT,
    "lastActiveAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "sessions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "subscriptions" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "plan" "OrgPlan" NOT NULL DEFAULT 'FREE',
    "status" "SubscriptionStatus" NOT NULL DEFAULT 'TRIALING',
    "currentPeriodStart" TIMESTAMP(3),
    "currentPeriodEnd" TIMESTAMP(3),
    "cancelAtPeriodEnd" BOOLEAN NOT NULL DEFAULT false,
    "trialEndsAt" TIMESTAMP(3),
    "stripeCustomerId" TEXT,
    "stripeSubscriptionId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "subscriptions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "payments" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "amount" DOUBLE PRECISION NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "status" "PaymentStatus" NOT NULL DEFAULT 'PENDING',
    "description" TEXT,
    "stripePaymentId" TEXT,
    "invoiceUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payments_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "usage_records" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "resource" TEXT NOT NULL,
    "count" INTEGER NOT NULL DEFAULT 1,
    "period" TEXT NOT NULL,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usage_records_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "lead_notes" (
    "id" SERIAL NOT NULL,
    "leadId" INTEGER NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "body" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "lead_notes_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "lead_tasks" (
    "id" SERIAL NOT NULL,
    "leadId" INTEGER NOT NULL,
    "userId" INTEGER NOT NULL,
    "createdById" INTEGER NOT NULL,
    "orgId" INTEGER,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "status" "TaskStatus" NOT NULL DEFAULT 'TODO',
    "priority" "TaskPriority" NOT NULL DEFAULT 'MEDIUM',
    "dueAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "lead_tasks_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "lead_activities" (
    "id" SERIAL NOT NULL,
    "leadId" INTEGER NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "type" "ActivityType" NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "lead_activities_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "lead_tags" (
    "id" SERIAL NOT NULL,
    "leadId" INTEGER NOT NULL,
    "tagId" INTEGER NOT NULL,

    CONSTRAINT "lead_tags_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "api_keys" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "keyHash" TEXT NOT NULL,
    "keyPrefix" TEXT NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "scopes" TEXT NOT NULL DEFAULT 'read,write',
    "lastUsedAt" TIMESTAMP(3),
    "expiresAt" TIMESTAMP(3),
    "revokedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "api_keys_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "webhooks" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "secret" TEXT NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "events" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "lastTriggered" TIMESTAMP(3),
    "failureCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "webhooks_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "webhook_deliveries" (
    "id" SERIAL NOT NULL,
    "webhookId" INTEGER NOT NULL,
    "event" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "responseStatus" INTEGER,
    "responseBody" TEXT,
    "error" TEXT,
    "durationMs" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "webhook_deliveries_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "saved_searches" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "resource" TEXT NOT NULL,
    "filters" JSONB NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "isShared" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "saved_searches_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "audit_logs" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER,
    "orgId" INTEGER,
    "action" TEXT NOT NULL,
    "entityType" TEXT NOT NULL,
    "entityId" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "ipAddress" TEXT,
    "userAgent" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "pipeline_stages" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "name" TEXT NOT NULL,
    "color" TEXT NOT NULL DEFAULT 'gray',
    "position" INTEGER NOT NULL DEFAULT 0,
    "probability" INTEGER NOT NULL DEFAULT 50,
    "isWon" BOOLEAN NOT NULL DEFAULT false,
    "isLost" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "pipeline_stages_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "activities" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "kind" "ActivityKind" NOT NULL,
    "status" "ActivityStatus" NOT NULL DEFAULT 'SCHEDULED',
    "entityType" "ActivityEntityType" NOT NULL,
    "entityId" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "outcome" TEXT,
    "dueAt" TIMESTAMP(3),
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "duration" INTEGER,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "activities_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "calendar_events" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "startAt" TIMESTAMP(3) NOT NULL,
    "endAt" TIMESTAMP(3) NOT NULL,
    "allDay" BOOLEAN NOT NULL DEFAULT false,
    "location" TEXT,
    "meetingUrl" TEXT,
    "attendees" JSONB,
    "relatedTo" TEXT,
    "relatedId" INTEGER,
    "color" TEXT NOT NULL DEFAULT 'teal',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "calendar_events_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "email_templates" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "subject" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "category" TEXT,
    "variables" JSONB,
    "isShared" BOOLEAN NOT NULL DEFAULT false,
    "useCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "email_templates_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "sequences" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "status" "SequenceStatus" NOT NULL DEFAULT 'DRAFT',
    "steps" JSONB NOT NULL,
    "metrics" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "sequences_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "sequence_enrollments" (
    "id" SERIAL NOT NULL,
    "sequenceId" INTEGER NOT NULL,
    "contactId" INTEGER,
    "leadId" INTEGER,
    "email" TEXT NOT NULL,
    "status" "EnrollmentStatus" NOT NULL DEFAULT 'ACTIVE',
    "currentStep" INTEGER NOT NULL DEFAULT 0,
    "retryCount" INTEGER NOT NULL DEFAULT 0,
    "steps" JSONB NOT NULL,
    "nextRunAt" TIMESTAMP(3),
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "sequence_enrollments_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "workflows" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "trigger" "WorkflowTrigger" NOT NULL,
    "conditions" JSONB,
    "actions" JSONB NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "runCount" INTEGER NOT NULL DEFAULT 0,
    "lastRunAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "workflows_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "workflow_runs" (
    "id" SERIAL NOT NULL,
    "workflowId" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'running',
    "trigger" TEXT NOT NULL,
    "entityType" TEXT NOT NULL,
    "entityId" INTEGER,
    "log" JSONB NOT NULL,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),
    "error" TEXT,

    CONSTRAINT "workflow_runs_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "custom_fields" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "entity" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "options" JSONB,
    "required" BOOLEAN NOT NULL DEFAULT false,
    "position" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "custom_fields_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "comments" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "entityType" TEXT NOT NULL,
    "entityId" INTEGER NOT NULL,
    "body" TEXT NOT NULL,
    "mentions" JSONB,
    "parentId" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "comments_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "notification_preferences" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "channel" TEXT NOT NULL DEFAULT 'in_app',
    "category" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "notification_preferences_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "integrations" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "provider" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "config" JSONB,
    "credentials" JSONB,
    "status" TEXT NOT NULL DEFAULT 'connected',
    "lastSyncAt" TIMESTAMP(3),
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "integrations_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "forecasts" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "period" TEXT NOT NULL,
    "category" TEXT NOT NULL DEFAULT 'commit',
    "amount" DOUBLE PRECISION NOT NULL,
    "deals" JSONB,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "forecasts_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "reports" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "type" TEXT NOT NULL,
    "config" JSONB NOT NULL,
    "schedule" TEXT,
    "isShared" BOOLEAN NOT NULL DEFAULT false,
    "lastRunAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "reports_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "changelog_entries" (
    "id" SERIAL NOT NULL,
    "version" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "type" TEXT NOT NULL DEFAULT 'feature',
    "published" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "changelog_entries_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "onboarding_progress" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "step" TEXT NOT NULL,
    "completed" BOOLEAN NOT NULL DEFAULT false,
    "metadata" JSONB,
    "completedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "onboarding_progress_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "invoices" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "userId" INTEGER NOT NULL,
    "number" TEXT NOT NULL,
    "amount" DOUBLE PRECISION NOT NULL,
    "tax" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "total" DOUBLE PRECISION NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "status" TEXT NOT NULL DEFAULT 'draft',
    "items" JSONB NOT NULL,
    "issuedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "dueAt" TIMESTAMP(3),
    "paidAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "invoices_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "products" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "name" TEXT NOT NULL,
    "sku" TEXT NOT NULL,
    "description" TEXT,
    "category" TEXT,
    "unitPrice" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "cost" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "userId" INTEGER,

    CONSTRAINT "products_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "price_books" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "name" TEXT NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "isDefault" BOOLEAN NOT NULL DEFAULT false,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "userId" INTEGER,

    CONSTRAINT "price_books_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "price_book_entries" (
    "id" SERIAL NOT NULL,
    "priceBookId" INTEGER NOT NULL,
    "productId" INTEGER NOT NULL,
    "unitPrice" DOUBLE PRECISION NOT NULL,
    "minQuantity" INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT "price_book_entries_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "quotes" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "dealId" INTEGER,
    "number" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "status" "QuoteStatus" NOT NULL DEFAULT 'DRAFT',
    "subtotal" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "tax" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "discount" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "total" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "validUntil" TIMESTAMP(3),
    "sentAt" TIMESTAMP(3),
    "viewedAt" TIMESTAMP(3),
    "acceptedAt" TIMESTAMP(3),
    "rejectedAt" TIMESTAMP(3),
    "notes" TEXT,
    "terms" TEXT,
    "metadata" JSONB,
    "createdById" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "quotes_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "quote_items" (
    "id" SERIAL NOT NULL,
    "quoteId" INTEGER NOT NULL,
    "productId" INTEGER,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "quantity" INTEGER NOT NULL DEFAULT 1,
    "unitPrice" DOUBLE PRECISION NOT NULL,
    "discount" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "total" DOUBLE PRECISION NOT NULL,
    "position" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "quote_items_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "quote_events" (
    "id" SERIAL NOT NULL,
    "quoteId" INTEGER NOT NULL,
    "type" TEXT NOT NULL,
    "actor" TEXT,
    "ip" TEXT,
    "userAgent" TEXT,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "quote_events_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "playbooks" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "category" TEXT NOT NULL DEFAULT 'general',
    "tags" TEXT,
    "isPublished" BOOLEAN NOT NULL DEFAULT true,
    "createdById" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "playbooks_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "playbook_steps" (
    "id" SERIAL NOT NULL,
    "playbookId" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "type" TEXT NOT NULL DEFAULT 'text',
    "position" INTEGER NOT NULL DEFAULT 0,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "playbook_steps_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "win_loss_records" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "dealId" INTEGER,
    "outcome" "DealOutcome" NOT NULL,
    "lossReason" "LossReason",
    "competitor" TEXT,
    "amount" DOUBLE PRECISION NOT NULL,
    "closedAt" TIMESTAMP(3) NOT NULL,
    "cycleDays" INTEGER,
    "notes" TEXT,
    "lessons" TEXT,
    "metadata" JSONB,
    "recordedById" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "win_loss_records_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "email_events" (
    "id" SERIAL NOT NULL,
    "orgId" INTEGER,
    "type" "EmailEventType" NOT NULL,
    "recipient" TEXT NOT NULL,
    "subject" TEXT,
    "messageId" TEXT,
    "link" TEXT,
    "linkLabel" TEXT,
    "ip" TEXT,
    "userAgent" TEXT,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "email_events_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "intel_searches" (
    "id" SERIAL NOT NULL,
    "userId" INTEGER NOT NULL,
    "orgId" INTEGER,
    "module" TEXT NOT NULL,
    "query" TEXT NOT NULL,
    "filters" JSONB DEFAULT '{}',
    "results" JSONB NOT NULL,
    "isPinned" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "intel_searches_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "fcm_tokens" (
    "id" SERIAL NOT NULL,
    "token" TEXT NOT NULL,
    "userId" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fcm_tokens_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_googleId_key" ON "users"("googleId");

CREATE UNIQUE INDEX "organizations_slug_key" ON "organizations"("slug");

CREATE INDEX "org_memberships_orgId_idx" ON "org_memberships"("orgId");

CREATE UNIQUE INDEX "org_memberships_userId_orgId_key" ON "org_memberships"("userId", "orgId");

CREATE UNIQUE INDEX "team_invites_token_key" ON "team_invites"("token");

CREATE INDEX "team_invites_orgId_idx" ON "team_invites"("orgId");

CREATE INDEX "team_invites_email_idx" ON "team_invites"("email");

CREATE UNIQUE INDEX "sessions_tokenHash_key" ON "sessions"("tokenHash");

CREATE INDEX "sessions_userId_idx" ON "sessions"("userId");

CREATE INDEX "sessions_tokenHash_idx" ON "sessions"("tokenHash");

CREATE UNIQUE INDEX "subscriptions_userId_key" ON "subscriptions"("userId");

CREATE UNIQUE INDEX "subscriptions_orgId_key" ON "subscriptions"("orgId");

CREATE INDEX "payments_userId_idx" ON "payments"("userId");

CREATE INDEX "payments_orgId_idx" ON "payments"("orgId");

CREATE INDEX "usage_records_orgId_period_idx" ON "usage_records"("orgId", "period");

CREATE UNIQUE INDEX "usage_records_userId_orgId_resource_period_key" ON "usage_records"("userId", "orgId", "resource", "period");

CREATE INDEX "leads_orgId_idx" ON "leads"("orgId");

CREATE INDEX "leads_assignedToId_idx" ON "leads"("assignedToId");

CREATE INDEX "lead_notes_leadId_idx" ON "lead_notes"("leadId");

CREATE INDEX "lead_tasks_leadId_idx" ON "lead_tasks"("leadId");

CREATE INDEX "lead_tasks_userId_idx" ON "lead_tasks"("userId");

CREATE INDEX "lead_tasks_status_idx" ON "lead_tasks"("status");

CREATE INDEX "lead_activities_leadId_idx" ON "lead_activities"("leadId");

CREATE INDEX "lead_activities_createdAt_idx" ON "lead_activities"("createdAt");

CREATE INDEX "tags_orgId_idx" ON "tags"("orgId");

CREATE UNIQUE INDEX "tags_orgId_slug_key" ON "tags"("orgId", "slug");

CREATE UNIQUE INDEX "lead_tags_leadId_tagId_key" ON "lead_tags"("leadId", "tagId");

CREATE UNIQUE INDEX "api_keys_keyHash_key" ON "api_keys"("keyHash");

CREATE INDEX "api_keys_keyHash_idx" ON "api_keys"("keyHash");

CREATE INDEX "api_keys_orgId_idx" ON "api_keys"("orgId");

CREATE INDEX "webhooks_orgId_idx" ON "webhooks"("orgId");

CREATE INDEX "webhook_deliveries_webhookId_idx" ON "webhook_deliveries"("webhookId");

CREATE INDEX "webhook_deliveries_createdAt_idx" ON "webhook_deliveries"("createdAt");

CREATE INDEX "saved_searches_orgId_resource_idx" ON "saved_searches"("orgId", "resource");

CREATE INDEX "saved_searches_userId_idx" ON "saved_searches"("userId");

CREATE INDEX "audit_logs_userId_idx" ON "audit_logs"("userId");

CREATE INDEX "audit_logs_orgId_idx" ON "audit_logs"("orgId");

CREATE INDEX "audit_logs_action_idx" ON "audit_logs"("action");

CREATE INDEX "audit_logs_entityType_idx" ON "audit_logs"("entityType");

CREATE INDEX "audit_logs_createdAt_idx" ON "audit_logs"("createdAt");

CREATE INDEX "analytics_events_userId_idx" ON "analytics_events"("userId");

CREATE INDEX "analytics_events_type_idx" ON "analytics_events"("type");

CREATE INDEX "analytics_events_orgId_idx" ON "analytics_events"("orgId");

CREATE INDEX "analytics_events_createdAt_idx" ON "analytics_events"("createdAt");

CREATE INDEX "email_searches_userId_idx" ON "email_searches"("userId");

CREATE INDEX "email_searches_orgId_idx" ON "email_searches"("orgId");

CREATE INDEX "domain_searches_userId_idx" ON "domain_searches"("userId");

CREATE INDEX "domain_searches_orgId_idx" ON "domain_searches"("orgId");

CREATE INDEX "pipeline_stages_orgId_position_idx" ON "pipeline_stages"("orgId", "position");

CREATE INDEX "activities_orgId_kind_idx" ON "activities"("orgId", "kind");

CREATE INDEX "activities_userId_status_idx" ON "activities"("userId", "status");

CREATE INDEX "activities_entityType_entityId_idx" ON "activities"("entityType", "entityId");

CREATE INDEX "activities_dueAt_idx" ON "activities"("dueAt");

CREATE INDEX "calendar_events_orgId_startAt_idx" ON "calendar_events"("orgId", "startAt");

CREATE INDEX "calendar_events_userId_startAt_idx" ON "calendar_events"("userId", "startAt");

CREATE INDEX "email_templates_orgId_idx" ON "email_templates"("orgId");

CREATE INDEX "sequences_orgId_idx" ON "sequences"("orgId");

CREATE INDEX "sequence_enrollments_sequenceId_status_idx" ON "sequence_enrollments"("sequenceId", "status");

CREATE INDEX "sequence_enrollments_nextRunAt_idx" ON "sequence_enrollments"("nextRunAt");

CREATE INDEX "workflows_orgId_trigger_idx" ON "workflows"("orgId", "trigger");

CREATE INDEX "workflows_active_idx" ON "workflows"("active");

CREATE INDEX "workflow_runs_workflowId_idx" ON "workflow_runs"("workflowId");

CREATE INDEX "workflow_runs_status_idx" ON "workflow_runs"("status");

CREATE INDEX "custom_fields_orgId_entity_idx" ON "custom_fields"("orgId", "entity");

CREATE UNIQUE INDEX "custom_fields_orgId_entity_slug_key" ON "custom_fields"("orgId", "entity", "slug");

CREATE INDEX "comments_entityType_entityId_idx" ON "comments"("entityType", "entityId");

CREATE INDEX "comments_orgId_idx" ON "comments"("orgId");

CREATE UNIQUE INDEX "notification_preferences_userId_orgId_channel_category_key" ON "notification_preferences"("userId", "orgId", "channel", "category");

CREATE INDEX "integrations_orgId_idx" ON "integrations"("orgId");

CREATE UNIQUE INDEX "integrations_orgId_provider_key" ON "integrations"("orgId", "provider");

CREATE INDEX "forecasts_orgId_period_idx" ON "forecasts"("orgId", "period");

CREATE INDEX "reports_orgId_type_idx" ON "reports"("orgId", "type");

CREATE INDEX "changelog_entries_published_createdAt_idx" ON "changelog_entries"("published", "createdAt");

CREATE UNIQUE INDEX "onboarding_progress_userId_step_key" ON "onboarding_progress"("userId", "step");

CREATE UNIQUE INDEX "invoices_number_key" ON "invoices"("number");

CREATE INDEX "invoices_orgId_idx" ON "invoices"("orgId");

CREATE INDEX "products_orgId_category_idx" ON "products"("orgId", "category");

CREATE UNIQUE INDEX "products_orgId_sku_key" ON "products"("orgId", "sku");

CREATE INDEX "price_books_orgId_idx" ON "price_books"("orgId");

CREATE UNIQUE INDEX "price_book_entries_priceBookId_productId_key" ON "price_book_entries"("priceBookId", "productId");

CREATE UNIQUE INDEX "quotes_number_key" ON "quotes"("number");

CREATE INDEX "quotes_orgId_status_idx" ON "quotes"("orgId", "status");

CREATE INDEX "quotes_dealId_idx" ON "quotes"("dealId");

CREATE INDEX "quote_items_quoteId_idx" ON "quote_items"("quoteId");

CREATE INDEX "quote_events_quoteId_type_idx" ON "quote_events"("quoteId", "type");

CREATE INDEX "playbooks_orgId_category_idx" ON "playbooks"("orgId", "category");

CREATE INDEX "playbook_steps_playbookId_position_idx" ON "playbook_steps"("playbookId", "position");

CREATE UNIQUE INDEX "win_loss_records_dealId_key" ON "win_loss_records"("dealId");

CREATE INDEX "win_loss_records_orgId_outcome_idx" ON "win_loss_records"("orgId", "outcome");

CREATE INDEX "win_loss_records_orgId_lossReason_idx" ON "win_loss_records"("orgId", "lossReason");

CREATE INDEX "email_events_orgId_type_idx" ON "email_events"("orgId", "type");

CREATE INDEX "email_events_recipient_idx" ON "email_events"("recipient");

CREATE INDEX "email_events_createdAt_idx" ON "email_events"("createdAt");

CREATE INDEX "intel_searches_userId_idx" ON "intel_searches"("userId");

CREATE INDEX "intel_searches_orgId_idx" ON "intel_searches"("orgId");

CREATE INDEX "intel_searches_module_idx" ON "intel_searches"("module");

CREATE UNIQUE INDEX "fcm_tokens_token_key" ON "fcm_tokens"("token");

CREATE INDEX "fcm_tokens_userId_idx" ON "fcm_tokens"("userId");

-- AddForeignKey
ALTER TABLE "users" DROP CONSTRAINT "users_organizationId_fkey";
ALTER TABLE "users" ADD CONSTRAINT "users_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "org_memberships" ADD CONSTRAINT "org_memberships_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "org_memberships" ADD CONSTRAINT "org_memberships_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "team_invites" ADD CONSTRAINT "team_invites_invitedById_fkey" FOREIGN KEY ("invitedById") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "team_invites" ADD CONSTRAINT "team_invites_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "payments" ADD CONSTRAINT "payments_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "payments" ADD CONSTRAINT "payments_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "usage_records" ADD CONSTRAINT "usage_records_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "usage_records" ADD CONSTRAINT "usage_records_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "leads" DROP CONSTRAINT "leads_addedById_fkey";
ALTER TABLE "leads" ADD CONSTRAINT "leads_addedById_fkey" FOREIGN KEY ("addedById") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "leads" ADD CONSTRAINT "leads_assignedToId_fkey" FOREIGN KEY ("assignedToId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "leads" ADD CONSTRAINT "leads_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "lead_notes" ADD CONSTRAINT "lead_notes_leadId_fkey" FOREIGN KEY ("leadId") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_notes" ADD CONSTRAINT "lead_notes_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "lead_notes" ADD CONSTRAINT "lead_notes_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_tasks" ADD CONSTRAINT "lead_tasks_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_tasks" ADD CONSTRAINT "lead_tasks_leadId_fkey" FOREIGN KEY ("leadId") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_tasks" ADD CONSTRAINT "lead_tasks_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "lead_tasks" ADD CONSTRAINT "lead_tasks_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_activities" ADD CONSTRAINT "lead_activities_leadId_fkey" FOREIGN KEY ("leadId") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_activities" ADD CONSTRAINT "lead_activities_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "lead_activities" ADD CONSTRAINT "lead_activities_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tags" ADD CONSTRAINT "tags_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tags" ADD CONSTRAINT "tags_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "lead_tags" ADD CONSTRAINT "lead_tags_leadId_fkey" FOREIGN KEY ("leadId") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "lead_tags" ADD CONSTRAINT "lead_tags_tagId_fkey" FOREIGN KEY ("tagId") REFERENCES "tags"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "deals" ADD CONSTRAINT "deals_stageId_fkey" FOREIGN KEY ("stageId") REFERENCES "pipeline_stages"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "deal_startups" DROP CONSTRAINT "deal_startups_dealId_fkey";
ALTER TABLE "deal_startups" ADD CONSTRAINT "deal_startups_dealId_fkey" FOREIGN KEY ("dealId") REFERENCES "deals"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "deal_startups" DROP CONSTRAINT "deal_startups_orgId_fkey";
ALTER TABLE "deal_startups" ADD CONSTRAINT "deal_startups_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "deal_investors" DROP CONSTRAINT "deal_investors_dealId_fkey";
ALTER TABLE "deal_investors" ADD CONSTRAINT "deal_investors_dealId_fkey" FOREIGN KEY ("dealId") REFERENCES "deals"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "deal_investors" DROP CONSTRAINT "deal_investors_orgId_fkey";
ALTER TABLE "deal_investors" ADD CONSTRAINT "deal_investors_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "api_keys" ADD CONSTRAINT "api_keys_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "api_keys" ADD CONSTRAINT "api_keys_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "webhooks" ADD CONSTRAINT "webhooks_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "webhooks" ADD CONSTRAINT "webhooks_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "webhook_deliveries" ADD CONSTRAINT "webhook_deliveries_webhookId_fkey" FOREIGN KEY ("webhookId") REFERENCES "webhooks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "saved_searches" ADD CONSTRAINT "saved_searches_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "saved_searches" ADD CONSTRAINT "saved_searches_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "activity_logs" DROP CONSTRAINT "activity_logs_userId_fkey";
ALTER TABLE "activity_logs" ADD CONSTRAINT "activity_logs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "analytics_events" DROP CONSTRAINT "analytics_events_userId_fkey";
ALTER TABLE "analytics_events" ADD CONSTRAINT "analytics_events_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "notifications" DROP CONSTRAINT "notifications_userId_fkey";
ALTER TABLE "notifications" ADD CONSTRAINT "notifications_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "pipeline_stages" ADD CONSTRAINT "pipeline_stages_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "activities" ADD CONSTRAINT "activities_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "activities" ADD CONSTRAINT "activities_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "calendar_events" ADD CONSTRAINT "calendar_events_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "calendar_events" ADD CONSTRAINT "calendar_events_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "email_templates" ADD CONSTRAINT "email_templates_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "email_templates" ADD CONSTRAINT "email_templates_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sequences" ADD CONSTRAINT "sequences_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sequences" ADD CONSTRAINT "sequences_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sequence_enrollments" ADD CONSTRAINT "sequence_enrollments_sequenceId_fkey" FOREIGN KEY ("sequenceId") REFERENCES "sequences"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sequence_enrollments" ADD CONSTRAINT "sequence_enrollments_leadId_fkey" FOREIGN KEY ("leadId") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "workflows" ADD CONSTRAINT "workflows_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "workflows" ADD CONSTRAINT "workflows_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "workflow_runs" ADD CONSTRAINT "workflow_runs_workflowId_fkey" FOREIGN KEY ("workflowId") REFERENCES "workflows"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "custom_fields" ADD CONSTRAINT "custom_fields_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "comments" ADD CONSTRAINT "comments_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "comments" ADD CONSTRAINT "comments_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "notification_preferences" ADD CONSTRAINT "notification_preferences_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "notification_preferences" ADD CONSTRAINT "notification_preferences_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "integrations" ADD CONSTRAINT "integrations_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "integrations" ADD CONSTRAINT "integrations_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "forecasts" ADD CONSTRAINT "forecasts_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "forecasts" ADD CONSTRAINT "forecasts_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "reports" ADD CONSTRAINT "reports_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "reports" ADD CONSTRAINT "reports_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "onboarding_progress" ADD CONSTRAINT "onboarding_progress_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "onboarding_progress" ADD CONSTRAINT "onboarding_progress_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "products" ADD CONSTRAINT "products_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "products" ADD CONSTRAINT "products_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "price_books" ADD CONSTRAINT "price_books_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "price_books" ADD CONSTRAINT "price_books_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "price_book_entries" ADD CONSTRAINT "price_book_entries_priceBookId_fkey" FOREIGN KEY ("priceBookId") REFERENCES "price_books"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "price_book_entries" ADD CONSTRAINT "price_book_entries_productId_fkey" FOREIGN KEY ("productId") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "quotes" ADD CONSTRAINT "quotes_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "quotes" ADD CONSTRAINT "quotes_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "quote_items" ADD CONSTRAINT "quote_items_productId_fkey" FOREIGN KEY ("productId") REFERENCES "products"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "quote_items" ADD CONSTRAINT "quote_items_quoteId_fkey" FOREIGN KEY ("quoteId") REFERENCES "quotes"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "quote_events" ADD CONSTRAINT "quote_events_quoteId_fkey" FOREIGN KEY ("quoteId") REFERENCES "quotes"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "playbooks" ADD CONSTRAINT "playbooks_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "playbooks" ADD CONSTRAINT "playbooks_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "playbook_steps" ADD CONSTRAINT "playbook_steps_playbookId_fkey" FOREIGN KEY ("playbookId") REFERENCES "playbooks"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "win_loss_records" ADD CONSTRAINT "win_loss_records_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "win_loss_records" ADD CONSTRAINT "win_loss_records_recordedById_fkey" FOREIGN KEY ("recordedById") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "email_events" ADD CONSTRAINT "email_events_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "intel_searches" ADD CONSTRAINT "intel_searches_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "intel_searches" ADD CONSTRAINT "intel_searches_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "fcm_tokens" ADD CONSTRAINT "fcm_tokens_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
