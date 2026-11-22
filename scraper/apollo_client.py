"""Optional Apollo.io API client. NOT used unless APOLLO_API_KEY is set.

Today the Apollo work is manual (free plan, see pilot.py). When an API key becomes available, set
APOLLO_API_KEY and the automatic discovery (search_type "discover") will use Apollo for companies that
still have no HR contact:

  1. People API Search  POST /api/v1/mixed_people/api_search   (0 credits; no emails in the answer)
  2. People Enrichment  POST /api/v1/people/match               (1 credit per revealed email)

Only emails Apollo marks "verified" are returned. Phone numbers are never requested (they cost 8 credits).

Environment:
  APOLLO_API_KEY        the key; without it everything here is skipped
  APOLLO_MAX_ENRICH     credit guard: most people enriched per discovery run (default 10)
  APOLLO_PER_COMPANY    most HR people kept per company (default 2)

Try it:  python apollo_client.py --domain example.com
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from lead_validation import NOT_DISCLOSED

BASE_URL = os.environ.get("APOLLO_BASE_URL", "https://api.apollo.io/api/v1").rstrip("/")
HR_TITLES = ["HR Manager", "Human Resources", "Talent Acquisition", "Recruiter", "Technical Recruiter", "Head of People"]

Poster = Callable[[str, Dict[str, Any], Dict[str, str]], Dict[str, Any]]


class ApolloError(RuntimeError):
    pass


def apollo_enabled() -> bool:
    return bool(os.environ.get("APOLLO_API_KEY", "").strip())


def _post(path: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Apollo reads these parameters from the query string (arrays use the name[] form)."""
    pairs: List = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            pairs += [(f"{key}[]", v) for v in value]
        elif value is not None:
            pairs.append((key, str(value).lower() if isinstance(value, bool) else value))
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(pairs)}"
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={**headers, "Content-Type": "application/json", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ApolloError("Apollo rejected the API key (check APOLLO_API_KEY and the key's endpoint access)")
        if e.code == 402:
            raise ApolloError("Apollo credits are finished")
        if e.code == 429:
            raise ApolloError("Apollo rate limit reached, try again later")
        raise ApolloError(f"Apollo error HTTP {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ApolloError(f"Apollo not reachable: {e}")


def search_hr_people(domain: str, per_page: int = 5, post: Poster = _post) -> List[Dict[str, Any]]:
    """HR / talent people of a company (by website domain). Costs no credits and returns no emails."""
    headers = {"x-api-key": os.environ.get("APOLLO_API_KEY", "")}
    data = post("/mixed_people/api_search",
                {"q_organization_domains_list": [domain], "person_titles": HR_TITLES, "per_page": per_page, "page": 1}, headers)
    return [p for p in data.get("people", []) if p.get("has_email") is not False]


def enrich_person(person_id: str, domain: str, post: Poster = _post) -> Dict[str, Any]:
    """Reveal one person's email (1 credit when an email is returned)."""
    headers = {"x-api-key": os.environ.get("APOLLO_API_KEY", "")}
    data = post("/people/match", {"id": person_id, "domain": domain, "reveal_personal_emails": False}, headers)
    return data.get("person") or {}


def find_hr_contacts(company: str, domain: str, budget: Optional[List[int]] = None, post: Poster = _post) -> List[Dict[str, Any]]:
    """Leads (shared lead format) for the company's HR people whose email Apollo marks verified.
    `budget` is a one-item list holding the enrichments still allowed in this run (the credit guard)."""
    if not (apollo_enabled() and domain):
        return []
    keep = int(os.environ.get("APOLLO_PER_COMPANY", "2"))
    if budget is None:
        budget = [int(os.environ.get("APOLLO_MAX_ENRICH", "10"))]
    leads: List[Dict[str, Any]] = []
    for person in search_hr_people(domain, post=post):
        if len(leads) >= keep or budget[0] <= 0:
            break
        budget[0] -= 1
        full = enrich_person(person.get("id", ""), domain, post=post)
        email = str(full.get("email") or "").strip().lower()
        if not email or str(full.get("email_status") or "").lower() != "verified":
            continue
        name = " ".join(x for x in (full.get("first_name"), full.get("last_name")) if x) or NOT_DISCLOSED
        leads.append({
            "COMPANY": company, "HR NAME": name, "HR TITLE": full.get("title") or person.get("title") or "",
            "HR EMAIL": email, "HR PHONE": NOT_DISCLOSED, "HR CONTACT": email,
            "HR PROFILE URL": full.get("linkedin_url") or "", "SOURCE": "Apollo (API)",
        })
    return leads


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the Apollo API key: list verified HR contacts of one company domain.")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--company", default="")
    a = ap.parse_args(argv)
    if not apollo_enabled():
        print("APOLLO_API_KEY is not set; nothing to do.")
        return 1
    try:
        found = find_hr_contacts(a.company or a.domain, a.domain)
    except ApolloError as e:
        print(f"[-] {e}")
        return 2
    for lead in found:
        print(f"{lead['HR NAME']} | {lead['HR TITLE']} | {lead['HR EMAIL']}")
    print(f"[+] {len(found)} verified HR contact(s) for {a.domain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
