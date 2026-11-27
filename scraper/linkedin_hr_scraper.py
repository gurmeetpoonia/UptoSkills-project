#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
linkedin_hr_scraper.py - LinkedIn job discovery + HR matching + validation + scoring.

Used two ways:
  * by main.py (FastAPI / Render):  run_master_job_army(search_query=..., limit=..., headful=...)
    -> list of lead dicts with the keys the Find Leads UI and CRM controller expect.
  * from the command line:
        python linkedin_hr_scraper.py --query "Python Developer" --location Hyderabad --limit 10

Discovery order (best first):
  1. LinkedIn *guest* job-search API over plain HTTPS (no browser, works on Render free tier).
  2. Playwright on the public search page (only if step 1 returns nothing; needs `playwright install chromium`).

HR data: leads_with_hr.xlsx (path = env HR_EXCEL_PATH, default: next to this file). A job is matched
by URL, then by company + title, then by company alone. Every HR email / phone is validated with
lead_validation.py before it can reach the CRM.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import html as _html
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from lead_validation import (NOT_DISCLOSED, email_kind, is_blank, lead_confidence, score_lead, validate_email,
                             validate_phone, verification_label)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
HR_EXCEL_FILE = os.environ.get("HR_EXCEL_PATH") or str(HERE / "leads_with_hr.xlsx")
HR_EXCEL = HR_EXCEL_FILE  # backwards-compatible alias (old CLI name)
OUTPUT_DIR = Path(os.environ.get("SCRAPER_OUTPUT_DIR") or (HERE / "output"))

GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_POSTING = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PAGE_SIZE = 25

Fetcher = Callable[[str], str]

# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
_COMPANY_NOISE = re.compile(
    r"\b(pvt|private|ltd|limited|llp|llc|inc|incorporated|corp|corporation|co|company|"
    r"technologies|technology|solutions|services|india|software|systems)\b")


def normalize_match(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def normalize_company(value: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())
    text = _COMPANY_NOISE.sub(" ", text)
    return re.sub(r"[^a-z0-9]", "", text)


def clean_job_url(raw: str) -> str:
    """Drop tracking parameters; keep the stable /jobs/view/<slug>-<id> part."""
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw.strip())
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme or "https", parsed.netloc, path, "", ""))


def job_id_from_url(url: str) -> str:
    m = re.search(r"(\d{6,})(?:/?$|\?)", url or "")
    return m.group(1) if m else ""


def parse_query(query: str, location: str = "") -> Tuple[str, str]:
    """'Python Developer in Hyderabad' -> ('Python Developer', 'Hyderabad')."""
    query = (query or "").strip()
    if location:
        return query, location.strip()
    m = re.match(r"(?i)^(.*?)\s+(?:in|at|near)\s+([A-Za-z .,-]+)$", query)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return query, "India"


# ----------------------------------------------------------------------
# HR index (leads_with_hr.xlsx)
# ----------------------------------------------------------------------
def load_existing_hr_data(path: Optional[str] = None) -> Dict[str, Any]:
    """Return {'by_url','by_company_job','by_company','count'}; empty indexes when the file is missing."""
    path = path or HR_EXCEL_FILE
    index: Dict[str, Any] = {"by_url": {}, "by_company_job": {}, "by_company": {}, "count": 0}
    if not Path(path).exists():
        print(f"[-] HR Excel file not found: {path}")
        return index
    import pandas as pd
    df = pd.read_excel(path)
    for _, row in df.iterrows():
        hr = {
            "HR NAME": row.get("HR Name"), "HR TITLE": row.get("HR Title"),
            "HR EMAIL": row.get("HR Email"), "HR PHONE": row.get("Mobile NO:"),
            "HR PROFILE URL": row.get("HR Profile URL"),
        }
        hr = {k: ("" if is_blank(v) else str(int(v)) if isinstance(v, float) and v == int(v) else str(v).strip())
              for k, v in hr.items()}
        url = clean_job_url(str(row.get("Job URL") or "")).lower()
        company = normalize_company(row.get("Company"))
        title = normalize_match(row.get("Job Title"))
        if url:
            index["by_url"][url] = hr
        if company and title:
            index["by_company_job"].setdefault((company, title), hr)
        if company:
            # prefer the first record that has a usable contact
            current = index["by_company"].get(company)
            if current is None or (not current["HR EMAIL"] and hr["HR EMAIL"]):
                index["by_company"][company] = hr
    index["count"] = len(df)
    print(f"[+] Existing HR records loaded: {len(df)}")
    return index


def match_existing_hr(lead: Dict[str, Any], hr_index: Dict[str, Any]) -> Dict[str, Any]:
    """Fill HR fields from the index, validate them, and set HR CONTACT / VERIFICATION."""
    hr = None
    match_kind = ""
    if hr_index:
        url = clean_job_url(lead.get("JOB URL", "")).lower()
        company = normalize_company(lead.get("COMPANY"))
        title = normalize_match(lead.get("JOB TITLE"))
        for kind, found in (("url", hr_index["by_url"].get(url)),
                            ("company+title", hr_index["by_company_job"].get((company, title))),
                            ("company", hr_index["by_company"].get(company))):
            if found and any(found.values()):  # a row whose HR columns are all blank/"Not found" is no match
                hr, match_kind = found, kind
                break
    if hr:
        lead.update({k: v for k, v in hr.items() if v})
        lead["HR MATCH"] = match_kind
    lead.setdefault("HR NAME", NOT_DISCLOSED)
    for field in ("HR NAME", "HR TITLE", "HR EMAIL", "HR PHONE", "HR PROFILE URL"):
        if is_blank(lead.get(field)):
            lead[field] = NOT_DISCLOSED if field in ("HR NAME", "HR EMAIL", "HR PHONE") else ""

    email_status = validate_email(lead["HR EMAIL"])
    phone_status, phone_e164 = validate_phone(lead["HR PHONE"])
    lead["EMAIL STATUS"] = email_status
    lead["PHONE STATUS"] = phone_status
    # An invalid / disposable / dummy contact must never travel on to the CRM.
    if email_status.startswith("Invalid"):
        lead["HR EMAIL"] = NOT_DISCLOSED
    if phone_status == "Valid":
        lead["HR PHONE"] = phone_e164
    else:
        lead["HR PHONE"] = NOT_DISCLOSED
    contacts = [v for v in (lead["HR EMAIL"], lead["HR PHONE"]) if v != NOT_DISCLOSED]
    lead["HR CONTACT"] = " | ".join(contacts) if contacts else NOT_DISCLOSED
    lead["EMAIL KIND"] = email_kind(lead["HR EMAIL"])
    lead["VERIFICATION"] = verification_label(lead["HR EMAIL"], email_status, bool(hr))
    lead["CONFIDENCE"], lead["CONFIDENCE_REASON"] = lead_confidence(lead)
    return lead


# ----------------------------------------------------------------------
# Discovery - LinkedIn guest API (plain HTTP)
# ----------------------------------------------------------------------
def http_fetch(url: str, retries: int = 3, timeout: int = 25) -> str:
    """GET with a browser user-agent and back-off on 429/5xx. Returns '' on failure."""
    delay = 2.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay + random.random())
                delay *= 2
                continue
            print(f"[-] HTTP {e.code} for {url[:90]}")
            return ""
        except Exception as e:  # network down, DNS, timeout
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            print(f"[-] Request failed ({e.__class__.__name__}): {url[:90]}")
            return ""
    return ""


def parse_search_cards(markup: str) -> List[Dict[str, str]]:
    """Parse the HTML fragment returned by the guest search API into job dicts."""
    soup = BeautifulSoup(markup or "", "html.parser")
    jobs: List[Dict[str, str]] = []
    for card in soup.select("li"):
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link or not link.get("href"):
            continue
        title_el = card.select_one("h3.base-search-card__title, h3")
        company_el = card.select_one("h4.base-search-card__subtitle, h4")
        loc_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        company = company_el.get_text(" ", strip=True) if company_el else ""
        if not title or not company:
            continue
        jobs.append({
            "url": clean_job_url(_html.unescape(link["href"])),
            "title": title, "company": company,
            "location": loc_el.get_text(" ", strip=True) if loc_el else "",
            "posted": (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else "",
        })
    return jobs


def parse_posting_detail(markup: str) -> Dict[str, Any]:
    """Description / expired flag / salary hint from the guest jobPosting fragment."""
    soup = BeautifulSoup(markup or "", "html.parser")
    desc_el = soup.select_one("div.show-more-less-html__markup, div.description__text")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""
    text = soup.get_text(" ", strip=True).lower()
    expired = ("no longer accepting applications" in text or "no longer available" in text
               or soup.select_one("figure.closed-job, .closed-job") is not None)
    salary_el = soup.select_one(".compensation__salary, .salary")
    return {"description": description, "expired": expired,
            "salary": salary_el.get_text(" ", strip=True) if salary_el else ""}


def discover_guest(keywords: str, location: str, max_pages: int, fetch: Fetcher = http_fetch,
                   want: int = 0, pause: float = 1.0) -> List[Dict[str, str]]:
    """Walk the guest search API page by page until max_pages or `want` jobs are collected."""
    found: List[Dict[str, str]] = []
    seen = set()
    offset = 0  # LinkedIn returns ~10 cards per call (not 25), so advance by what we really got
    for page_no in range(max_pages):
        params = urllib.parse.urlencode({"keywords": keywords, "location": location,
                                         "start": offset, "f_TPR": "r2592000"})
        markup = fetch(f"{GUEST_SEARCH}?{params}")
        cards = parse_search_cards(markup)
        offset += len(cards)
        new = 0
        for job in cards:
            key = job_id_from_url(job["url"]) or job["url"]
            if key in seen:
                continue
            seen.add(key)
            found.append(job)
            new += 1
        print(f"[*] Guest search page {page_no + 1}: {len(cards)} cards, {new} new")
        if not cards or (want and len(found) >= want):
            break
        if pause:
            time.sleep(pause)
    return found


def discover_playwright(keywords: str, location: str, max_pages: int, headful: bool = False) -> List[Dict[str, str]]:
    """Fallback: scroll the public search page in a real browser. Imported lazily."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[-] Playwright not installed; skipping browser fallback.")
        return []
    jobs: List[Dict[str, str]] = []
    params = urllib.parse.urlencode({"keywords": keywords, "location": location, "position": 1})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(f"https://www.linkedin.com/jobs/search/?{params}", wait_until="domcontentloaded")
            if "login" in page.url.lower() or "authwall" in page.url.lower():
                print("[-] LinkedIn asked for sign-in; browser fallback blocked.")
                return []
            for _ in range(6 + 2 * max_pages):
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                page.wait_for_timeout(900)
            jobs = parse_search_cards("<ul>" + "".join(
                f"<li>{h}</li>" for h in page.eval_on_selector_all(
                    "div.base-card, li", "els => els.map(e => e.innerHTML)")) + "</ul>")
        finally:
            browser.close()
    return jobs


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
def build_lead(job: Dict[str, str], detail: Dict[str, Any], query: str) -> Dict[str, Any]:
    description = detail.get("description", "")
    return {
        "JOB TITLE": job["title"], "COMPANY": job["company"],
        "AREA / LOCATION": job.get("location") or NOT_DISCLOSED,
        "SALARY": detail.get("salary") or NOT_DISCLOSED,
        "JOB URL": job["url"], "SOURCE": "LinkedIn",
        "DISCOVERED": job.get("posted", ""), "SEARCH QUERY": query,
        "FULL DESCRIPTION": description[:12000] if description else NOT_DISCLOSED,
    }


def fast_fetch(url: str) -> str:
    """Interactive searches: one retry and a short timeout, so a blocked LinkedIn never stalls the UI."""
    return http_fetch(url, retries=2, timeout=12)


def detail_fetch_quick(url: str) -> str:
    return http_fetch(url, retries=1, timeout=8)


def run_master_job_army(search_query: Optional[str] = None, headful: bool = False, limit: Optional[int] = 10,
                        location: str = "", max_pages: int = 2, fetch: Fetcher = http_fetch,
                        hr_index: Optional[Dict[str, Any]] = None, use_browser_fallback: bool = True,
                        pause: float = 1.0, args: Optional[argparse.Namespace] = None,
                        time_budget: Optional[float] = None, workers: int = 6) -> List[Dict[str, Any]]:
    """Discover jobs, attach + validate HR contacts, score, drop expired/invalid, return best-first.

    time_budget (seconds): stop reading job detail pages after this long and return what we have
    (cards still give company + title, so partial results are real leads). None = no limit (CLI)."""
    if args is not None:  # CLI namespace support
        search_query = search_query or args.query
        location = location or args.location
        limit = args.limit
        max_pages = args.max_pages
        headful = args.headful
    if not search_query or not search_query.strip():
        raise ValueError("Please provide a job search query.")
    limit = None if limit in (None, 0) else int(limit)
    if limit is not None and limit < 0:
        return []

    keywords, where = parse_query(search_query, location)
    print(f"\n[+] MASTER JOB ARMY  keywords='{keywords}'  location='{where}'  limit={limit}")
    hr_index = hr_index if hr_index is not None else load_existing_hr_data()

    # Scan a few more cards than needed: some are expired or have no company.
    started = time.monotonic()
    deadline = (started + float(time_budget)) if time_budget else None
    interactive = fetch is http_fetch and time_budget  # only swap in the fast fetchers for the real network
    search_fetch = fast_fetch if interactive else fetch
    detail_fetch = detail_fetch_quick if interactive else fetch
    want = (limit * 3) if limit else 0
    jobs = discover_guest(keywords, where, max_pages, fetch=search_fetch, want=want, pause=pause)
    if not jobs and use_browser_fallback and not (deadline and time.monotonic() > deadline):
        print("[*] Guest API returned nothing - trying the browser fallback.")
        jobs = discover_playwright(keywords, where, max_pages, headful=headful)
    print(f"[+] {len(jobs)} job cards discovered")

    unique_jobs, seen_urls = [], set()
    for job in jobs:
        if job["url"] in seen_urls:
            continue
        seen_urls.add(job["url"])
        unique_jobs.append(job)

    def get_detail(job: Dict[str, str]) -> Dict[str, Any]:
        job_id = job_id_from_url(job["url"])
        if not job_id or (deadline and time.monotonic() > deadline):
            return {}
        detail = parse_posting_detail(detail_fetch(GUEST_POSTING.format(job_id=job_id)))
        if pause and not interactive:
            time.sleep(random.uniform(0.3, pause))
        return detail

    if time_budget and len(unique_jobs) > 1:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
            details = list(pool.map(get_detail, unique_jobs))
    else:
        details = [get_detail(j) for j in unique_jobs]
    skipped = sum(1 for d in details if not d)
    if deadline and time.monotonic() > deadline:
        print(f"[*] Time budget of {time_budget:.0f}s reached; {skipped} jobs were kept from their card data.")

    leads: List[Dict[str, Any]] = []
    stats = {"expired": 0, "invalid": 0}
    for job, detail in zip(unique_jobs, details):
        if detail.get("expired"):
            stats["expired"] += 1
            continue
        lead = match_existing_hr(build_lead(job, detail, search_query), hr_index)
        lead["SCORE"] = score_lead(lead)
        if is_blank(lead["COMPANY"]) or is_blank(lead["JOB TITLE"]):
            stats["invalid"] += 1
            continue
        leads.append(lead)

    leads.sort(key=lambda x: x["SCORE"], reverse=True)
    if limit is not None:
        leads = leads[:limit]
    print(f"[+] Done: {len(leads)} leads (expired removed: {stats['expired']}, invalid: {stats['invalid']})")
    return leads


# ----------------------------------------------------------------------
# Excel export
# ----------------------------------------------------------------------
EXPORT_HEADERS = ["SCORE", "JOB TITLE", "COMPANY", "AREA / LOCATION", "SALARY", "HR NAME", "HR TITLE",
                  "HR EMAIL", "HR PHONE", "HR CONTACT", "EMAIL STATUS", "PHONE STATUS", "VERIFICATION",
                  "HR MATCH", "SOURCE", "DISCOVERED", "JOB URL", "FULL DESCRIPTION"]


def save_to_excel(leads: List[Dict[str, Any]], path: Optional[Path] = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = path or OUTPUT_DIR / f"linkedin_job_leads_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(EXPORT_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    for lead in leads:
        ws.append([str(lead.get(h, "")) if h == "FULL DESCRIPTION" else lead.get(h, "") for h in EXPORT_HEADERS])
    ws.freeze_panes = "A2"
    wb.save(path)
    print(f"[+] Excel file written: {path}")
    return path


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_cli(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LinkedIn Job & HR Lead Scraper")
    p.add_argument("--query", required=True, help='e.g. "Python Developer" or "Python Developer in Hyderabad"')
    p.add_argument("--location", default="", help="optional location (default: parsed from query, else India)")
    p.add_argument("--limit", type=int, default=10, help="max leads to keep (0 = unlimited)")
    p.add_argument("--max_pages", type=int, default=2, help="LinkedIn result pages to scan (25 jobs each)")
    p.add_argument("--headful", action="store_true", help="show the browser in the fallback mode")
    return p.parse_args(argv)


if __name__ == "__main__":
    cli = parse_cli()
    result = run_master_job_army(args=cli)
    if result:
        save_to_excel(result)
    else:
        print("\n[-] No valid leads found - nothing written.")
