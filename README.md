# SalesForge

## Stack
- Frontend: React + Vite
- Backend: Node.js + Express
- Database: PostgreSQL + Prisma
- Background jobs: Redis + BullMQ

## Local setup

1. Copy environment examples:
   - `backend/.env.example` → `backend/.env`
   - `frontend/.env.example` → `frontend/.env`
2. Start PostgreSQL and Redis, or use the included Docker Compose setup.
3. Install dependencies:

```bash
npm run install:all
```

4. Apply the Prisma migrations to an empty database:

```bash
cd backend && npx prisma migrate deploy
```

5. Start the backend and frontend in separate terminals:

```bash
npm run dev:backend
npm run dev:frontend
```

The Vite development server proxies `/api` to `http://localhost:3000` by default.

## Docker verification setup

The included Compose file provisions PostgreSQL and Redis, runs `npx prisma migrate deploy` and starts the backend:

```bash
docker compose up --build
```

Then open `http://localhost:8080`.

## Database migrations

`npx prisma migrate deploy` works on an empty PostgreSQL database. The migration `20260920000000_baseline_current_schema` brings the early schema (first three migrations) up to the current one.

A database that was originally created with `prisma db push` already has these objects. Do not apply the baseline there; mark the migrations as applied instead:

```bash
npx prisma migrate resolve --applied 20260920000000_baseline_current_schema
npx prisma migrate resolve --applied 20260921215000_add_replied_to_email_event_type
npx prisma migrate resolve --applied 20261001100000_add_campaign_sequence_relation
npx prisma migrate resolve --applied 20261031120000_campaign_retry_tracking_and_lead_fk
```

Only mark a migration as applied if the database really contains its changes; run `npx prisma migrate status` afterwards. Take a backup before changing a production database.

## Environment

The backend needs `DATABASE_URL` and `JWT_SECRET`. Redis is required for BullMQ-backed functionality. Email, Google, Firebase, AI, and other integrations are optional until their corresponding features are used.
