from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import re
import threading
import uuid

from lead_validation import NOT_DISCLOSED, is_blank, score_lead, verification_label
from company_discovery import discover
from intelligent_filter import apply_filter, filter_enabled
from linkedin_hr_scraper import HR_EXCEL_FILE, match_existing_hr, run_master_job_army

app = FastAPI(title="Master Job Army API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://uptoskills-project.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: Dict[str, Dict[str, Any]] = {}

# Job-search engines (both are kept):
#   linkedin (default) - LinkedIn guest API + HR-file matching, needs no API key.
#   serper             - the multi-platform Serper search in master_job_army.py (needs SERPER_API_KEY).
#   both               - LinkedIn first; if it finds nothing and SERPER_API_KEY is set, use Serper.
SCRAPER_ENGINE = os.environ.get("SCRAPER_ENGINE", "linkedin").strip().lower()
scrape_lock = threading.Lock()  # the Serper engine drives Chromium: one run at a time (memory)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}")


def serper_search(req) -> list:
    """Run the Serper/Playwright engine (master_job_army.py) and adapt its leads to the shared lead format."""
    if not os.environ.get("SERPER_API_KEY"):
        raise RuntimeError("SERPER_API_KEY is not set on the scraper service")
    import master_job_army as serper_engine  # imported on demand: it needs Playwright

    with scrape_lock:
        raw = serper_engine.run_master_job_army(
            search_query=req.query, headful=bool(req.headful), limit=None if filter_enabled() else req.limit
        )
    leads = []
    for item in raw:
        lead = dict(item)
        contact = str(lead.get("HR CONTACT") or "")
        email = _EMAIL_RE.search(contact)
        phone = _PHONE_RE.search(contact.replace(" ", ""))
        lead.setdefault("HR NAME", NOT_DISCLOSED)
        lead["HR EMAIL"] = email.group(0).lower() if email else NOT_DISCLOSED
        lead["HR PHONE"] = phone.group(0) if phone else NOT_DISCLOSED
        try:
            lead = match_existing_hr(lead, None)  # enrich from the HR data when the company is known
        except Exception:
            pass
        leads.append(lead)
    return leads


class ScrapeRequest(BaseModel):
    query: str
    search_type: Optional[str] = "all"
    limit: Optional[int] = 5
    headful: Optional[bool] = False
    location: Optional[str] = ""
    max_pages: Optional[int] = 2
    selection: Optional[str] = "any"  # intelligent tool: any | email | mobile | both


def clean(value) -> str:
    return NOT_DISCLOSED if is_blank(value) else str(value).strip()


def search_hr_file(query: str, search_type: str, limit) -> list:
    """Search the HR index (leads_with_hr.xlsx) by HR name, HR email or company."""
    import pandas as pd

    if not os.path.exists(HR_EXCEL_FILE):
        raise FileNotFoundError(
            "HR data file not found on the scraper service. Put leads_with_hr.xlsx next to main.py "
            "or set HR_EXCEL_PATH."
        )
    df = pd.read_excel(HR_EXCEL_FILE)
    column = {"name": "HR Name", "email": "HR Email", "company": "Company"}[search_type]
    q = query.strip().lower()
    max_rows = int(limit or 20)
    results = []

    for _, row in df.iterrows():
        if q not in str(row.get(column, "")).lower():
            continue
        lead = {
            "COMPANY": clean(row.get("Company")),
            "JOB TITLE": clean(row.get("Job Title")),
            "AREA / LOCATION": clean(row.get("Location")),
            "SALARY": NOT_DISCLOSED,
            "HR NAME": clean(row.get("HR Name")),
            "HR TITLE": "" if is_blank(row.get("HR Title")) else str(row.get("HR Title")).strip(),
            "HR EMAIL": clean(row.get("HR Email")),
            "HR PHONE": clean(row.get("Mobile NO:")),
            "HR PROFILE URL": "" if is_blank(row.get("HR Profile URL")) else str(row.get("HR Profile URL")).strip(),
            "SOURCE": clean(row.get("Source")),
            "JOB URL": clean(row.get("Job URL")),
            "DISCOVERED": "" if is_blank(row.get("Posted")) else str(row.get("Posted"))[:10],
            "FULL DESCRIPTION": NOT_DISCLOSED,
        }
        lead = match_existing_hr(lead, None)  # validate only; the row already is HR data
        lead["VERIFICATION"] = verification_label(lead["EMAIL STATUS"], lead["EMAIL STATUS"], True)
        lead["SCORE"] = score_lead(lead)
        results.append(lead)
        if len(results) >= max_rows:
            break

    results.sort(key=lambda x: x["SCORE"], reverse=True)
    return results


def _finish(results: list, note: str, req: ScrapeRequest, limit: int = 0):
    """Pass the leads through the intelligent tool (valid email/mobile, not expired, not duplicate,
    scored, with a reason) and keep the best `limit`."""
    results, filter_note = apply_filter(results, req.selection or "any")
    limit = int(limit or req.limit or 10)
    results = results[:limit]
    notes = [n for n in (note, filter_note) if n]
    if not results and filter_note:
        notes.append("Nothing is left after filtering - try another search, or ask for more HR data.")
    return results, " ".join(notes)


def smart_search(req: ScrapeRequest):
    """Return (results, note). `note` explains an empty/filtered result so the UI never just says "0 leads"."""
    stype = req.search_type or "all"
    query = req.query.strip()
    if query in ("*", "all"):  # list every lead we have (HR data), screened by the intelligent tool
        results = search_hr_file("", "company", 1000)
        return _finish(results, "" if results else "No leads available yet in the HR data.", req, limit=1000)
    if stype in ("name", "email", "company"):
        results = search_hr_file(query, stype, 1000)
        note = "" if results else f"No HR record in our HR data matches this {stype}: '{query}'."
        return _finish(results, note, req)
    # "all": an email is looked up in the HR data, everything else is a LinkedIn job search.
    if "@" in query:
        results = search_hr_file(query, "email", 1000)
        return _finish(results, "" if results else f"No HR record with the email '{query}'.", req)
    linkedin_error = ""
    results = []
    if SCRAPER_ENGINE in ("linkedin", "both"):
        try:
            results = run_master_job_army(
                search_query=query,
                headful=bool(req.headful),
                # With the filter on, read every candidate job: many have no HR contact and will be removed.
                limit=None if filter_enabled() else req.limit,
                location=req.location or "",
                max_pages=int(req.max_pages or 2),
            )
        except Exception as e:  # LinkedIn blocked / network error: fall back to the HR data
            results, linkedin_error = [], str(e)
    if not results and (SCRAPER_ENGINE == "serper" or (SCRAPER_ENGINE == "both" and os.environ.get("SERPER_API_KEY"))):
        try:
            results = serper_search(req)
        except Exception as e:
            linkedin_error = f"{linkedin_error} Serper: {e}".strip()
    if results:
        return _finish(results, "", req)
    # LinkedIn gave nothing: the text may be a company or an HR name, so try the HR data.
    for kind in ("company", "name"):
        hr_results = search_hr_file(query, kind, 1000)
        if hr_results:
            return _finish(hr_results, f"No LinkedIn jobs found for '{query}'; showing HR records matching the {kind}.", req)
    reason = f" ({linkedin_error})" if linkedin_error else ""
    return [], (f"No jobs found on LinkedIn for '{query}'{reason} and no HR record matches it. "
                "LinkedIn may be limiting requests - try again in a few minutes, or search a job title "
                "like 'Python Developer in Hyderabad'.")


def run_job(job_id: str, req: ScrapeRequest):
    jobs[job_id]["status"] = "running"
    try:
        results, note = smart_search(req)
        jobs[job_id]["results"] = results
        jobs[job_id]["leads"] = results  # same data under the key the original API used
        jobs[job_id]["note"] = note
        jobs[job_id]["status"] = "done"
    except Exception as e:
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["status"] = "error"


class DiscoverRequest(BaseModel):
    query: str
    location: Optional[str] = ""
    max_companies: Optional[int] = 20
    max_pages: Optional[int] = 2
    selection: Optional[str] = "any"


def run_discovery(job_id: str, req: DiscoverRequest):
    """Pilot: jobs -> companies with no HR contact -> public website contacts -> intelligent tool."""
    jobs[job_id]["status"] = "running"
    try:
        scraped = run_master_job_army(search_query=req.query, limit=None, location=req.location or "",
                                      max_pages=int(req.max_pages or 2))
        found, stats = discover(scraped, int(req.max_companies or 20))
        note = (f"Company discovery: {stats['companies_without_contact']} companies without an HR contact, "
                f"{stats['discovered']} with public contacts, {stats['domain_not_found']} website not found, "
                f"{stats['nothing_public']} nothing published.")
        results, filter_note = apply_filter(found, req.selection or "any")
        jobs[job_id]["results"] = results
        jobs[job_id]["leads"] = results
        jobs[job_id]["note"] = " ".join(n for n in (note, filter_note) if n)
        jobs[job_id]["stats"] = stats
        jobs[job_id]["status"] = "done"
    except Exception as e:
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["status"] = "error"


@app.post("/discover")
def start_discovery(req: DiscoverRequest, background_tasks: BackgroundTasks):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "results": [], "leads": [], "error": None, "note": ""}
    background_tasks.add_task(run_discovery, job_id, req)
    return {"job_id": job_id, "status": "queued"}  # read the result with GET /scrape/{job_id}


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/scrape")
def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    if req.search_type not in (None, "all", "name", "email", "company"):
        raise HTTPException(status_code=400, detail="Invalid search_type")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "results": [], "leads": [], "error": None, "note": ""}
    background_tasks.add_task(run_job, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/scrape/{job_id}")
def get_scrape(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job