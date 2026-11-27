"""Company discovery pilot (no paid contact API).

Flow:  LinkedIn jobs -> companies that have no HR contact yet -> official website (domain) ->
public contact / careers pages -> publicly published email + phone -> intelligent tool.

Rules:
  * Only contacts that the company itself publishes on its own domain are used. Nothing is guessed
    (no firstname.lastname patterns) and nothing is bought.
  * Published mailboxes such as hr@ or careers@ are 'generic' for the tool: they are listed but are
    NOT saved to the CRM (the CRM needs an individual email). A published phone number makes the
    lead a phone-only follow-up lead.
  * At most 5 pages per company, with a pause between requests.
Individual HR emails still come from people (Akshita Y's verified Apollo rows in leads_with_hr.xlsx).
"""
import os
import re
import time
import concurrent.futures as cf
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from lead_validation import (NOT_DISCLOSED, accept_hr_mailbox, email_kind, score_lead, validate_email,
                             validate_phone, verification_label)
from page_contacts import extract_contacts, internal_links
from linkedin_hr_scraper import USER_AGENT, match_existing_hr, normalize_company

Fetcher = Callable[[str], str]


def quick_fetch(url: str, timeout: int = 6) -> str:
    """One quick, silent attempt (a wrong domain guess must not cost 6+ seconds of retries)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(400_000).decode("utf-8", errors="replace")
    except Exception:
        return ""

PAGES = ["", "/contact", "/contact-us", "/careers", "/about"]
TLDS = [".com", ".in", ".co.in", ".io", ".ai"]
HR_WORDS = ("hr", "career", "careers", "recruit", "recruitment", "talent", "jobs", "hiring", "people")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}")
BAD_EMAIL_TAIL = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")


def collect_companies(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unique companies from scraped job leads, with their open positions. Companies that already
    have an HR contact are skipped (they do not need discovery)."""
    seen: Dict[str, Dict[str, Any]] = {}
    for lead in leads:
        name = str(lead.get("COMPANY") or "").strip()
        key = normalize_company(name)
        if not key or name.lower() in ("not disclosed", "not found"):
            continue
        has_contact = str(lead.get("HR CONTACT") or NOT_DISCLOSED) != NOT_DISCLOSED
        entry = seen.setdefault(key, {"company": name, "positions": [], "locations": [], "job_urls": [], "has_contact": False})
        entry["has_contact"] = entry["has_contact"] or has_contact
        for field, key2 in (("JOB TITLE", "positions"), ("AREA / LOCATION", "locations"), ("JOB URL", "job_urls")):
            val = str(lead.get(field) or "").strip()
            if val and val != NOT_DISCLOSED and val not in entry[key2]:
                entry[key2].append(val)
    return [e for e in seen.values() if not e["has_contact"]]


def domain_candidates(company: str) -> List[str]:
    key = normalize_company(company)
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", company.lower()).split() if w]
    bases = []
    for b in (key, "".join(words[:2]), "-".join(words[:2])):
        if b and b not in bases:
            bases.append(b)
    return [b + t for b in bases for t in TLDS]


def find_domain(company: str, fetch: Fetcher = quick_fetch) -> Optional[str]:
    """First candidate domain whose homepage mentions the company name. None when not sure."""
    key = normalize_company(company)
    for domain in domain_candidates(company)[:6]:
        html = fetch(f"https://www.{domain}") or fetch(f"https://{domain}")
        if not html:
            continue
        head = re.sub(r"[^a-z0-9]", "", html[:6000].lower())
        if key and key in head:
            return domain
    return None


def _same_site(email_domain: str, domain: str) -> bool:
    return email_domain == domain or email_domain.endswith("." + domain)


MAX_PAGES = int(os.environ.get("DISCOVERY_MAX_PAGES", "8"))


def _rank(contact: Dict[str, str]) -> int:
    """Best first: a named person, any personal address, an HR mailbox (when accepted), then the rest."""
    kind = email_kind(contact["email"])
    if kind == "personal":
        return 0 if contact.get("name") else 1
    if kind == "hr_mailbox":
        return 2
    return 3


def extract_public_contacts(domain: str, fetch: Fetcher = quick_fetch, pause: float = 0.0,
                            max_pages: int = None) -> Dict[str, Any]:
    """Crawl one company site: home page, the contact / careers / team / about pages it links to, plus
    the usual paths. Returns {"emails": [...best first], "phones": [...], "people": [{email,name,title}]}."""
    max_pages = max_pages or MAX_PAGES
    by_email: Dict[str, Dict[str, str]] = {}
    phones: List[str] = []
    queue: List[str] = [f"https://www.{domain}{p}" for p in PAGES[:1]]
    seen: set = set()
    first = True
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        html = fetch(url)
        if not html and first:  # the bare domain may not use www
            html = fetch(url.replace("https://www.", "https://", 1))
        if pause:
            time.sleep(pause)
        if first:
            first = False
            base = url if html else f"https://{domain}/"
            extra = internal_links(html, base, limit=max_pages) if html else []
            defaults = [f"https://www.{domain}{p}" for p in PAGES[1:]]
            queue = extra + [d for d in defaults if d not in extra]
        if not html:
            continue
        for c in extract_contacts(html, domain):
            cur = by_email.setdefault(c["email"], c)
            cur["name"] = cur.get("name") or c.get("name", "")
            cur["title"] = cur.get("title") or c.get("title", "")
        text = urllib.parse.unquote(html)
        for m in PHONE_RE.findall(re.sub(r"<[^>]+>", " ", text)):
            status, e164 = validate_phone(m)
            if status == "Valid" and e164 not in phones:
                phones.append(e164)
    people = sorted(by_email.values(), key=_rank)
    return {"emails": [p["email"] for p in people], "phones": phones, "people": people}


def discover_company(entry: Dict[str, Any], fetch: Fetcher = quick_fetch, pause: float = 0.0):
    """(lead, reason). lead is None when nothing public was found; reason is then
    'domain_not_found' or 'nothing_public'."""
    domain = find_domain(entry["company"], fetch)
    if not domain:
        return None, "domain_not_found"
    found = extract_public_contacts(domain, fetch, pause)
    email = next((e for e in found["emails"] if validate_email(e) in ("Valid", "Generic")), "")
    person = next((p for p in found.get("people", []) if p["email"] == email), {})
    phone = found["phones"][0] if found["phones"] else ""
    if not email and not phone:
        return None, "nothing_public"
    lead = {
        "COMPANY": entry["company"],
        "JOB TITLE": entry["positions"][0] if entry["positions"] else NOT_DISCLOSED,
        "AREA / LOCATION": entry["locations"][0] if entry["locations"] else NOT_DISCLOSED,
        "SALARY": NOT_DISCLOSED,
        "HR NAME": person.get("name") or NOT_DISCLOSED,
        "HR TITLE": person.get("title") or "",
        "HR EMAIL": email or NOT_DISCLOSED,
        "HR PHONE": phone or NOT_DISCLOSED,
        "HR PROFILE URL": "",
        "SOURCE": "Company website",
        "JOB URL": entry["job_urls"][0] if entry["job_urls"] else NOT_DISCLOSED,
        "DISCOVERED": "",
        "FULL DESCRIPTION": NOT_DISCLOSED,
        "COMPANY DOMAIN": domain,
        "OPEN POSITIONS": len(entry["positions"]),
    }
    lead = match_existing_hr(lead, None)
    lead["VERIFICATION"] = verification_label(lead["HR EMAIL"], lead["EMAIL STATUS"], False)
    if lead["VERIFICATION"].startswith("Unverified"):
        lead["VERIFICATION"] = lead["VERIFICATION"].replace("Unverified", "Unverified (public website)", 1)
    named = bool(person.get("name")) and email_kind(email) == "personal"
    lead["SCORE"] = min(score_lead(lead), 85 if named else 70)  # a public mailbox is weaker than a named person
    return lead, "ok"


def discover(leads: List[Dict[str, Any]], max_companies: int = None, fetch: Fetcher = quick_fetch,
             pause: float = None, workers: int = None, time_budget: float = None):
    """Returns (discovered leads, stats). `leads` are scraped job leads. Companies are crawled in parallel
    (DISCOVERY_WORKERS, default 8) and the run stops at `time_budget` seconds, keeping what it has."""
    max_companies = max_companies or int(os.environ.get("DISCOVERY_MAX_COMPANIES", "40"))
    pause = float(os.environ.get("DISCOVERY_PAUSE", "0.3")) if pause is None else pause
    workers = workers or int(os.environ.get("DISCOVERY_WORKERS", "8"))
    companies = collect_companies(leads)[:max_companies]
    out, stats = [], {"companies_without_contact": len(companies), "domain_not_found": 0, "nothing_public": 0,
                      "discovered": 0, "not_reached": 0}
    deadline = time.time() + time_budget if time_budget else None

    def work(entry):
        if deadline and time.time() > deadline:
            return None, "not_reached"
        return discover_company(entry, fetch, pause)

    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for lead, reason in pool.map(work, companies):
            if lead is None:
                stats[reason] = stats.get(reason, 0) + 1
                continue
            out.append(lead)
            stats["discovered"] += 1
    return out, stats
