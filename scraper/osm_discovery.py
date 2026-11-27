"""Free "map" source for company discovery: OpenStreetMap (Overpass API, no key, no cost).

This is the legal, free stand-in for a Google Maps scraper: it lists real businesses in a city
(office=it, or a name match) together with the website / phone / email that mappers published.
Google Maps itself cannot be scraped from a server (it is against Google's terms and gets blocked),
and browser extensions like "Google Maps Scraper" need a person clicking in a browser.

The result is fed to the same company-website discovery as the LinkedIn jobs, so a company with a
public contact page can still become a lead. It is optional and fail-soft: any error returns [].
Disable with ENABLE_OSM=0.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
USER_AGENT = "SalesForge-lead-discovery/1.0 (intern project; contact via repo)"
TECH_WORDS = re.compile(r"\b(software|developer|development|it|tech|python|java|react|node|data|ai|ml|web|app|cloud|devops|engineer)\b", re.I)

Poster = Callable[[str, str], str]


def osm_enabled() -> bool:
    return os.environ.get("ENABLE_OSM", "1").strip().lower() not in ("0", "false", "no", "off")


def _post(url: str, query: str, timeout: int = 20) -> str:
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def build_query(keyword: str, location: str, limit: int) -> str:
    place = re.sub(r"[\"\\]", "", (location or "").strip()) or "India"
    kw = re.sub(r"[^A-Za-z0-9 +#.\-]", "", keyword or "").strip()
    area = f'area["name"~"^{place}$",i]->.a;'
    if TECH_WORDS.search(kw or "software"):
        body = '(nwr["office"="it"]["name"](area.a);nwr["office"="company"]["name"]["website"](area.a););'
    else:
        body = f'(nwr["name"~"{kw}",i]["website"](area.a););'
    return f"[out:json][timeout:20];{area}{body}out tags center {int(limit)};"


def parse_elements(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    out, seen = [], set()
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({
            "company": name,
            "website": (tags.get("website") or tags.get("contact:website") or "").strip(),
            "phone": (tags.get("phone") or tags.get("contact:phone") or "").strip(),
            "email": (tags.get("email") or tags.get("contact:email") or "").strip(),
            "address": ", ".join(p for p in (tags.get("addr:street"), tags.get("addr:city")) if p),
        })
    return out


def osm_companies(keyword: str, location: str = "", limit: int = 25, post: Poster = _post) -> List[Dict[str, str]]:
    """Businesses from OpenStreetMap for a keyword + city. Returns [] on any problem."""
    if not osm_enabled():
        return []
    try:
        raw = post(OVERPASS_URL, build_query(keyword, location, limit))
        return parse_elements(json.loads(raw))[:limit]
    except Exception:
        return []


def as_job_rows(companies: List[Dict[str, str]], keyword: str, location: str) -> List[Dict[str, Any]]:
    """Shape OSM companies like scraped job rows so collect_companies()/discover() can use them."""
    return [{
        "COMPANY": c["company"],
        "JOB TITLE": keyword or "Software Developer",
        "AREA / LOCATION": c.get("address") or location or "",
        "JOB URL": c.get("website", ""),
        "HR CONTACT": "Not disclosed",
        "SOURCE": "OpenStreetMap",
    } for c in companies]
