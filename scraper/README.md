# Scraper service (FastAPI)

- `linkedin_hr_scraper.py` - LinkedIn discovery (guest API, browser fallback) + HR matching + validation + scoring. No API key needed.
- `master_job_army.py` - the original multi-platform Serper search (Naukri, Indeed, ...). Kept unchanged; needs `SERPER_API_KEY`.
- `lead_validation.py` - email / Indian mobile validation (disposable, generic, dummy numbers) and lead score.
- `main.py` - `/scrape` API used by Find Leads (`search_type`: all | name | email | company).
- `leads_with_hr.xlsx` - HR index. Override the path with env `HR_EXCEL_PATH`. Contains personal contact data: keep the repo private.
- Tests (offline): `python test_scraper.py`
- CLI: `python linkedin_hr_scraper.py --query "Python Developer" --location Hyderabad --limit 10`


## Automatic intelligent-tool filter
Every `/scrape` result is passed through the LeadScore intelligent tool before it is returned, so only leads with a valid email or mobile (not expired) are shown, each with `SELECTION_REASON`, `TOOL_SCORE`, `LEAD_CLASS`.

| Env var | Meaning |
|---|---|
| `INTELLIGENT_TOOL_URL` | Base URL of the running tool (e.g. `http://localhost:5000`); used first |
| `LEADSCORE_API_KEY` | Sent as `X-Api-Key` if the tool requires it |
| `LEADSCORE_DIR` | Folder with the tool's `app.py` for local import (default `../tools/leadscore-termux`) |
| `INTELLIGENT_FILTER=off` | Disable the filter |

If the tool is unreachable the scraper falls back to built-in rules with the same selection logic (`TOOL_ENGINE` shows which was used). Request field `selection`: `any` (default), `email`, `mobile`, `both`.

## Company discovery pilot (no paid API)
`POST /discover` with `{"query": "Python Developer", "location": "Pune", "max_companies": 20}` returns a `job_id`; read the result with `GET /scrape/{job_id}` (same as `/scrape`).

Flow: LinkedIn jobs -> companies that have no HR contact -> the company's own website -> public contact/careers pages -> intelligent tool.
- Only contacts the company publishes on its own domain are used. Nothing is guessed or bought.
- Published mailboxes (hr@, careers@) are *generic*: listed, not saved to the CRM. A published phone number makes a phone-only follow-up lead.
- Max 5 pages per company with a pause. Score is capped at 70. `SOURCE` is `Company website`.
- Individual HR emails still come from `leads_with_hr.xlsx` (verified manually, e.g. Apollo's green-verified rows).


## Pilot: new companies with Apollo used by hand (no paid API)
```
python pilot.py worksheet --query "Python Developer" --location Pune --max 20 --out pilot_worksheet.xlsx
# Akshita Y fills HR Name / HR Title / HR Email / Mobile NO: / HR Profile URL from Apollo and writes Yes in
# "Apollo Verified" only for green-marked emails, then:
python pilot.py ingest pilot_worksheet.xlsx --dry-run     # report only
python pilot.py ingest pilot_worksheet.xlsx               # appends good rows to leads_with_hr.xlsx
```
Every filled row goes through the intelligent tool. Only individual, Apollo-verified emails that pass the tool are added to `leads_with_hr.xlsx` (Find Leads then finds them by company and the user saves them to the CRM). Phone-only rows go to `pilot_phone_followup.csv` (not for the CRM). Generic mailboxes, duplicates and unverified emails are reported with a reason.

## Deploying without any paid key
Nothing here needs a paid key. `LEADSCORE_API_KEY` is only a password you make up if you run the tool as a separate public service; it is not an Apollo key.
1. **Simplest (current Dockerfile, root directory `scraper`)**: set nothing. The scraper uses its built-in rules (same selection: valid email or mobile).
2. **Scraper + tool in one container (recommended)**: on Render use Dockerfile Path `scraper/Dockerfile.with-tool` with an empty Root Directory. The scraper imports the tool directly (`TOOL_ENGINE` = `tool-local`). No URL, no key.
3. **Separate tool service**: run `python app.py --web` with `LEADSCORE_HOST=0.0.0.0` and a made-up `LEADSCORE_API_KEY`, and give the scraper `INTELLIGENT_TOOL_URL` and the same key.


## Search engines (`SCRAPER_ENGINE`)

Both job-search engines are available; pick one with the `SCRAPER_ENGINE` environment variable:

| Value | Behaviour |
|---|---|
| `linkedin` (default) | LinkedIn guest API + HR-file matching. No API key. |
| `serper` | Serper multi-platform search (`master_job_army.py`). Needs `SERPER_API_KEY`. |
| `both` | LinkedIn first; if it finds nothing and `SERPER_API_KEY` is set, Serper is used. |

Whatever the engine, every lead goes through the intelligent tool (valid email/mobile, not expired, no duplicates,
score + reason). The HR data file `leads_with_hr.xlsx` is not part of the repository (it holds personal contact data):
put it next to `main.py` or set `HR_EXCEL_PATH`.

## Automatic discovery (`search_type: "discover"`)

Find Leads shows the HR data instantly and then starts a live discovery with free sources (no paid API needed):
LinkedIn jobs (plus the Serper multi-platform search when `SERPER_API_KEY` is set) -> HR data match -> public contacts from
the company website for companies still without an HR contact -> intelligent tool (valid email/mobile, not expired, no
duplicates, score + reason). New leads are added to the list with a "New" badge. Defaults for an empty search:
`DEFAULT_DISCOVERY_QUERY` (Software Developer) and `DEFAULT_DISCOVERY_LOCATION` (India).
Note: LinkedIn and company websites rarely publish individual HR emails; public mailboxes such as hr@ or careers@ are
generic and are not saved to the CRM. Named HR emails still come from the HR data (Apollo pilot).

## Optional: Apollo API (off by default)

The Apollo work is manual today (free plan, see the pilot above). When an Apollo API key becomes available, nothing in
the code has to change: set the key and discovery asks Apollo for the HR people of companies that still have no contact
(`apollo_client.py`: People Search = 0 credits, People Enrichment = 1 credit per revealed email; only emails Apollo marks
"verified" are kept; phone numbers are never requested).

| Variable | Meaning |
|---|---|
| `APOLLO_API_KEY` | the key; without it the Apollo code is skipped |
| `APOLLO_MAX_ENRICH` | credit guard: most people enriched per discovery run (default 10) |
| `APOLLO_PER_COMPANY` | most HR people kept per company (default 2) |

Check a key with `python apollo_client.py --domain example.com`. In Docker add the key to the root `.env`
(`APOLLO_API_KEY=...`); the compose file passes it to the scraper service.


## Upload ingestion (Leads page: Upload Excel / Run Scraper)
- `POST /ingest` `{filename, content_base64}` -> `{job_id}`; `GET /ingest/{job_id}` -> `status` (queued | processing | done | error), `processed`, `total`, `summary`, `rows`, `warnings`, `error`, `error_code`.
- `ingest_upload.py` reads .xlsx / .xls / .csv, maps columns (Email / HR Email, Name / HR Name, Phone / Mobile NO:, Company, Job Title ...), and classifies each row: `qualified`, `phone_only`, `rejected` (with reasons) or `duplicate`. It uses `lead_validation.py` and the intelligent tool (score, expiry, email check), the same as `pilot.py ingest`. If the file has an "Apollo Verified" column, only rows marked Yes qualify.
- Limits: 5 MB, 5000 rows, `INGEST_TIME_BUDGET` seconds (default 300). Jobs are kept in memory for one hour.
- `.xls` needs `xlrd` (in requirements.txt).

## Website crawler (Discover new)
`company_discovery.py` + `page_contacts.py` are the crawler. For each company without an HR contact it finds the website, reads the home page and follows the links to contact / careers / team / about pages (up to `DISCOVERY_MAX_PAGES`, default 8). It reads only what the company publishes on its own domain: mailto links, Cloudflare-protected addresses, `name [at] company [dot] com`, JSON-LD contact data, and the name / job title printed next to an email. Nothing is guessed.
- Companies are crawled in parallel: `DISCOVERY_WORKERS` (8), `DISCOVERY_MAX_COMPANIES` (40), `DISCOVERY_TIME_BUDGET` seconds (60); partial results are kept when the budget ends.
- A named person with a personal email ranks first, then other personal emails, then HR mailboxes, then shared mailboxes.
- `ACCEPT_HR_MAILBOX=1` (set in docker-compose) makes hr@ / careers@ / jobs@ / recruitment@ / talent@ count as valid emails, labelled "HR mailbox". info@, support@, sales@, admin@ and other shared mailboxes are never accepted. `0` (the code default) keeps the strict rule: only individual emails.
