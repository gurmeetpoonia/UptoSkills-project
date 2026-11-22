# LeadScore Termux v1.7.0 — automatic scraper connection (+ five selection results, expiry removal)

Standalone Android Termux application for CSV/XLSX import, contact-presence qualification, contact validation, duplicate auditing, multi-query public-web research, fetched-source verification, explainable lead scoring, SQLite persistence, and CSV/JSON/XLSX exports.

## v1.7.0 — automatic connection with the web scraper
- New `POST /api/ingest` (JSON: `{"leads":[{Company, "Job Title", "HR Email", Mobile, ...}], "selection":"any"}`) returns one verdict per lead: `selected`, `selection_reason`, `score`, `lead_class`.
- The scraper (`scraper/intelligent_filter.py`) calls it automatically; only leads with a valid email or mobile (not expired) reach the CRM Find Leads list.
- Optional env: `LEADSCORE_HOST` (default `127.0.0.1`; use `0.0.0.0` only together with an API key), `LEADSCORE_API_KEY` (then send header `X-Api-Key`), `LEADSCORE_DATA_DIR` (where `data/leads.db` lives).

## v1.6.0 — captain's five results + expiry removal

The **Selected Leads** tab (and `/api/selected?mode=`, `/api/export?status=selected&select=`) gives, for the latest import:

| # | Result | How |
|---|--------|-----|
| 1 | Valid mobile OR email lead selected | mode `any` |
| 2 | Only valid email selected | mode `email` (lead has a valid email) |
| 3 | Only valid mobile selected | mode `mobile` (lead has a valid mobile; landline does not count) |
| 4 | Reason for each selected lead | `Selection_Reason` column, e.g. "Selected (Valid email): valid email a@x.com (domain has MX)" |
| 5 | Score of each selected lead | `Qualification_Score` + `Score_Explanation` columns |
| + | Both email and mobile | mode `both` |

**Expired leads are removed.** Any column named like Expiry / End Date / Deadline / Valid Till is parsed (dd/mm/yyyy first, ISO, "5 Dec 2026", Excel serial). A lead whose date is before today is class `Expired`, is never selected or scored, and appears under Rejected / `status=expired` export. Set `EXPIRY_INCLUSIVE_TODAY = True` in app.py to also drop leads on their expiry day.

Also: obvious dummy numbers (9876543210, 1234567890, 0987654321 ...) are rejected and `getnada.com` is treated as disposable.

## v1.5.1 — small fix
- When the optional `phonenumbers` library is installed, landline numbers were labelled "Phone" and the landline-only rule never triggered. They are now labelled "Landline", so a landline-only lead goes to Needs review.

## v1.5.0 — what changed

Every imported row now ends in exactly one class, with a reason (exported as `Lead_Class` / `Class_Reason`):

| Class | Meaning |
|---|---|
| **Ready** | At least one verified-quality contact (an email whose domain has MX records and is not role-based or disposable, **or** a valid mobile/international phone) and the basic details (company, and an HR name or job title). |
| **Needs review** | Usable but not fully verified or complete: only a role-based email (info@, hr@), email domain could not be verified because DNS was unavailable, only a landline, or missing company / HR name / job title. |
| **Rejected** | No usable contact: both fields blank, or every supplied value is invalid (bad email syntax, no such domain, disposable address, invalid phone). The reason says which. |
| **Duplicate** | Same email, same phone (in any format), the same posting with no different contact, or the same HR person at the same company. |

Changes from v1.4.4:

1. **Invalid contacts no longer qualify.** Before, any non-blank email or phone counted. Now a row needs a usable contact. A low score still never changes the class.
2. **Duplicates are decided by contact, not only by company and job.** Different HR people at the same company/job are kept as separate leads. The same phone written as `98765 43210`, `09876543210` or `+91 9876543210` is one phone. Rows with no contact are Rejected, not hidden as duplicates.
3. **DNS failures are not reported as "no MX records".** A "no MX / does not exist" verdict is only given when DNS correctly answers for a domain that certainly has mail servers (gmail.com). If you are offline, or the network answers NXDOMAIN to everything, the email shows "DNS verification unavailable" and the lead is Needs review. Unavailable results are not cached.
4. **Exports.** `Lead_Class` and `Class_Reason` columns were added, plus **Ready CSV / Ready XLSX** buttons. The qualified table shows the class under each company.

Qualified (Ready + Needs review) leads are still the ones that get internet research and scores.

## v1.4.1 — deeper research and score integrity

For each qualified company, the research engine now attempts several focused searches:

1. Company identity, official profile, products and business context.
2. Company plus the imported job title and careers/hiring terms.
3. Company technology/engineering context.
4. HR person's name plus company and recruiting terms, when an HR name is supplied.
5. Domain-restricted searches when a company domain is available.

The app gathers search result titles, snippets and URLs, then attempts to fetch a small number of source pages. A search snippet is labelled `search_snippet_only` and is **not** treated as verified evidence. A page can contribute evidence points only after it is fetched and its text matches the company name/domain. Job relevance additionally requires a match against the imported job title. HR association additionally requires the supplied HR name to appear on the fetched page. Explicit hiring evidence requires both job-title relevance and vacancy/application language.

The dashboard's **Full score & internet evidence** view shows the finding type, fetched-vs-snippet status, company-match status, title, summary, URL and retrieval time. The score explanation names the sources and states why each factor received or did not receive points.

### Scoring changes

- Contact quality and imported job-title/HR fields have limited, disclosed weights.
- Data completeness is capped at 0.04; it cannot dominate the score.
- Website HTTP reachability adds **zero** points. It is diagnostic only.
- Search snippets alone add **zero** points.
- Company profile, job relevance, explicit hiring and public HR association have separate evidence factors. Each requires a fetched, company-matched source.
- Research points are capped and sources are deduplicated by host to reduce repeated-result inflation.
- Scores are heuristic lead-priority indicators, not conversion probabilities or proof that a contact is active.

### Research provider setup

**Recommended: official Brave Search API.** It is used when `BRAVE_SEARCH_API_KEY` is configured. Obtain a key from the Brave Search API dashboard and keep it private. In Termux, set it for the current shell:

```sh
export BRAVE_SEARCH_API_KEY='PASTE_YOUR_PRIVATE_KEY_HERE'
bash ~/leadscore-termux/start.sh
```

For persistence, add the export command to `~/.bashrc` (do not share screenshots/logs containing the key). Brave requires the key in the `X-Subscription-Token` request header. See the official authentication and web-search API docs:
- https://api-dashboard.search.brave.com/documentation/guides/authentication
- https://api-dashboard.search.brave.com/api-reference/web/search/get

**Fallback without a key:** the app makes a best-effort request to DuckDuckGo's lightweight HTML results page. This is not an official organic-web-search API and can be rate-limited or change markup. DuckDuckGo's official Instant Answer API is a different product and does not provide a normal ranked web-results feed. If fallback search is blocked, the app records the failure and awards no unsupported research points.

This application does not use Google Search or claim that results are Google results. Search engines and source websites may limit automated requests. The app does not bypass logins, CAPTCHAs, or access controls.

## Refreshing previously imported leads

The Qualified Leads page includes **Research all qualified leads**. This runs fresh multi-query research against the latest imported run, updates the saved evidence and score in SQLite, and refreshes the dashboard. It can take several minutes depending on network/search provider availability. It does not change qualification status or delete imported records.

## Install in Termux

1. Extract this ZIP.
2. Open Termux and `cd` into the extracted `leadscore-termux` folder.
3. Run:

```sh
bash install.sh
```

4. Start:

```sh
bash ~/leadscore-termux/start.sh
```

5. Open `http://127.0.0.1:5000` in Android Chrome. Stop with **Ctrl+C** in Termux.

The application uses Python's standard library only; no FastAPI, Node, Rust, pydantic-core, watchfiles, or native compiler dependencies.

## Import

- Blank dashboard by default; sample rows load only if you tap **Load Test Scraped Dataset**.
- CSV and XLSX are supported, including XLSX shared strings and inline strings.
- Preview shows five rows, but the complete file is processed.
- Recognizes `HR Email`, `Mobile NO:`, `Company LinkedIn`, `Job Title`, and common header variants.
- Selecting the same file again is supported.

## Contact checks

- Email: syntax plus DNS/MX attempt. MX does not prove an individual mailbox exists. DNS unavailable is shown as such.
- Phone: numbering-format validation; no claim of line activity. Unprefixed numbers assume India (+91).
- Contact checks do not override the presence-based qualification rule.

## Exports

Qualified, rejected, duplicate, and all-record exports include score factor JSON, score explanation, company research summary, evidence JSON, source URLs and research timestamp. CSV and XLSX are supported; qualified JSON is also available.

## Database and backups

- Database: `~/leadscore-termux/data/leads.db`.
- Installer preserves the existing database and migrates the schema safely.
- Backup: `bash ~/leadscore-termux/backup.sh`.
- Restore: stop the app and copy the backup database over `~/leadscore-termux/data/leads.db`.

## Tests

Run:

```sh
python ~/leadscore-termux/test_suite.py
```

Offline deterministic tests cover CSV/XLSX parsing, header mapping, qualification rules, duplicate separation, score factors, rejection of snippet-only evidence, score caps, evidence persistence and exports. Live web access cannot be proven by offline tests; it must be verified on the phone's network. If Brave is not configured and DuckDuckGo blocks the fallback request, the application must show research unavailable rather than fabricate findings.


### v1.4.1 crash fix and clean workspace
- File picker uses an explicit change listener and `FileReader.result`; it does not depend on Android browser implicit event objects.
- Removed the sample/test dataset, sample loader button, and sample API route.
- Installer backs up an existing database with a timestamp before creating a clean empty database, so test leads are removed without destroying the old DB backup.


## v1.4.3 import reliability

CSV/XLSX import now performs qualification, duplicate classification, scoring, and the SQLite save without making network research requests. This keeps imports responsive on Android and prevents slow or blocked search providers from leaving the import button spinning. After the import completes, use **Research all qualified leads** on the Qualified Leads page when you want online company/job research. The import button now reports HTTP/API errors and always resets its loading state.


## v1.4.3 research reliability and persistence

Online research now runs in a background worker after import. The dashboard receives an immediate start response and polls a progress endpoint, so slow search providers or page fetches cannot keep a browser request waiting until it times out. Each lead's research evidence, source URLs, retrieval timestamp, score breakdown, and score explanation are committed to SQLite separately as that lead finishes. If one lead's search fails, the worker records the error and continues with the remaining leads. The progress control reports completed/total counts and a final error count.

Import remains intentionally network-free and fast. Newly imported leads initially show **Not Probed** and empty research evidence until the user taps **Research all qualified leads**. Search snippets and fetch failures are retained as research diagnostics/source records where available, but unverified snippets and HTTP reachability alone do not earn research score points. If no provider is reachable, the research summary records the provider/request errors rather than implying that research succeeded.

Research provider: configure `BRAVE_SEARCH_API_KEY` for the official Brave Search API. Without it, the app uses a best-effort DuckDuckGo HTML fallback that can be rate-limited. Internet research requires a working Android/Termux network connection.


## v1.4.4 fast research and balanced scoring

- Research now uses up to 10 concurrent lead workers, two targeted searches per lead, at most two fetched source pages per lead, shorter network timeouts, and no per-query sleep. This is a best-effort fast mode; completion within 30–60 seconds depends on network/search-provider response times and batch size.
- Scoring has been recalibrated as a 0.00–1.00 lead-priority score: validated contact channels, role seniority, HR contact detail, imported context completeness, and independently matched public evidence have clearer and more balanced weights. It is not a conversion probability and is not inflated by unverified search snippets.
- Each factor retains its point contribution and explanation.
