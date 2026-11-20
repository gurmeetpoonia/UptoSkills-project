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
