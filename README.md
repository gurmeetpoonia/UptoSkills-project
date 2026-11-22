# SalesForge

A CRM with automatic lead discovery. Leads come from a free scraper and a lead-scoring tool; only leads with a valid email go to the CRM, phone-only leads go to a separate follow-up list.

## Architecture

```
React (Vite, nginx :8080)
   |  /api
   v
Node.js + Express backend (:3000) --- PostgreSQL (Prisma)
   |            |
   |            +--- Redis + BullMQ (find-leads queue, follow-up jobs)
   v
Python FastAPI scraper (:8000)
   1. LinkedIn guest search (+ optional Serper / OpenStreetMap discovery)
   2. HR file match (leads_with_hr.xlsx)
   3. Intelligent tool: validate email / phone, score 0-100, classify
```

Find Leads flow:
1. The Find Leads panel reads saved candidates from the database (`find_lead_candidates`), so it opens instantly.
2. "Discover new" starts a background scraper job; results are saved to the same table.
3. A lead moves to My Leads (and is auto-tagged) only when the user adds it.

Upload CSV / Excel (Leads page, one button): choose a `.csv`, `.xlsx` or `.xls` file and click Run Scraper. The browser sends the file to the backend (`POST /api/leads/ingest`), the backend forwards it to the scraper service (`http://scraper:8000/ingest`, an internal address the browser never sees) and the page polls `GET /api/leads/ingest/:jobId`. The scraper validates every row with the same rules and intelligent tool as `pilot.py ingest` and returns real counts (total, qualified, rejected, duplicates, invalid email / phone) with a reason for each rejected row. Nothing is saved automatically: the user ticks the qualified leads and clicks Add selected (or Add all), which calls `POST /api/leads/ingest/:jobId/save`. Phone-only rows are listed but never saved to the CRM.

## Stack
- Frontend: React + Vite
- Backend: Node.js + Express
- Database: PostgreSQL + Prisma
- Background jobs: Redis + BullMQ
- Scraper: Python FastAPI (`scraper/`), lead-scoring tool (`tools/leadscore-termux/`)

## Quick start (Docker)

Create a `.env` in the repo root (Docker Compose reads it). Compose stops with a clear message if a required value is missing:

```
DATABASE_URL=postgresql://user:pass@host:5432/db
DIRECT_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://redis:6379
JWT_SECRET=change-me
```

```bash
docker compose up --build
```

Open `http://localhost:8080`. The backend applies migrations on start.

Optional scraper settings (all have safe defaults): `ACCEPT_HR_MAILBOX` (1 = hr@/careers@ count as valid emails, see `scraper/README.md`), `DISCOVERY_MAX_COMPANIES`, `SCRAPER_ENGINE` (`linkedin`, `serper`, `both`), `SEARCH_TIME_BUDGET` (seconds, default 40), `ENABLE_OSM` (`0` to turn off OpenStreetMap), `SERPER_API_KEY`, `APOLLO_API_KEY` (Apollo stays manual and off by default). See `scraper/README.md`.

## Local setup (without Docker)

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

## Tests

- Scraper (offline): `cd scraper && python test_scraper.py`
- Frontend build check: `cd frontend && npm run build`

## Notes
- `scraper/leads_with_hr.xlsx` contains real HR contacts. Keep it out of public repositories.
- Scraper jobs are held in memory; if the scraper restarts, a running job is lost and can be started again with Discover new.
