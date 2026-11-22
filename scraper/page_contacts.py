"""Read public contact details out of a web page (the SalesForge crawler's parser).

Finds the emails a company publishes on its own site, including the ones hidden from simple
scrapers: mailto: links, Cloudflare "email protection" (data-cfemail), "name [at] company [dot] com",
HTML entities, and JSON-LD (schema.org) contact data. When a name / job title is printed next to an
email, it is returned too. Nothing is guessed: every email returned is text that is on the page.
"""
import html as htmllib
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
BAD_TAIL = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".ico", ".woff", ".woff2")
LINK_WORDS = ("contact", "career", "job", "team", "about", "people", "leadership", "recruit", "hiring",
              "join", "work-with-us", "workwithus", "vacanc", "opening", "management")
TITLE_RE = re.compile(
    r"(?i)\b(human resources?|hr\b[\w &/-]{0,30}|talent acquisition[\w &/-]{0,20}|recruit(?:er|ment)[\w &/-]{0,20}|"
    r"people (?:ops|operations|partner|and culture)[\w &/-]{0,15}|head of [\w &]{3,25}|co-?founder|founder|ceo|cto|coo|"
    r"director[\w &]{0,20}|manager[\w &]{0,20}|vp[\w &]{0,20})")
NAME_RE = re.compile(r"\b([A-Z][a-z]{1,15}(?:[ \t]+[A-Z]\.?)?(?:[ \t]+[A-Z][a-z]{1,18}){1,2})\b")
NOT_NAMES = {"contact us", "send email", "email us", "get in", "talk to", "human resources", "talent acquisition",
             "read more", "learn more", "privacy policy", "terms conditions", "our team", "about us", "head office",
             "registered office", "customer care", "apply now", "join us", "write to", "mail us", "reach us",
             "business development", "sales team", "support team", "corporate office"}


def decode_cfemail(hexstr: str) -> str:
    """Cloudflare e-mail protection: first byte is the XOR key for the rest."""
    try:
        raw = bytes.fromhex(hexstr)
        key = raw[0]
        return "".join(chr(b ^ key) for b in raw[1:])
    except (ValueError, IndexError):
        return ""


def _deobfuscate(text: str) -> str:
    text = htmllib.unescape(urllib.parse.unquote(text))
    text = re.sub(r"(?i)\s*[\[\(\{<]\s*(?:at|@)\s*[\]\)\}>]\s*", "@", text)
    text = re.sub(r"(?i)\s*[\[\(\{<]\s*(?:dot|\.)\s*[\]\)\}>]\s*", ".", text)
    # "name at company dot com" written with plain words, only when it clearly forms an address
    text = re.sub(r"(?i)\b([A-Za-z0-9._-]{2,40})\s+at\s+([A-Za-z0-9-]{2,40})\s+dot\s+([A-Za-z]{2,10})\b", r"\1@\2.\3", text)
    return text


def _clean(email: str) -> str:
    return email.strip().strip(".,;:()<>[]'\"").lower()


def _valid_shape(email: str) -> bool:
    return bool(email) and not email.endswith(BAD_TAIL) and "@" in email and bool(EMAIL_RE.fullmatch(email))


def _walk_jsonld(node: Any, out: List[Dict[str, str]]):
    if isinstance(node, list):
        for n in node:
            _walk_jsonld(n, out)
    elif isinstance(node, dict):
        email = node.get("email")
        if isinstance(email, str) and "@" in email:
            out.append({"email": _clean(email.replace("mailto:", "")),
                        "name": str(node.get("name") or "") if node.get("@type") == "Person" else "",
                        "title": str(node.get("jobTitle") or "")})
        for v in node.values():
            if isinstance(v, (dict, list)):
                _walk_jsonld(v, out)


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)</?(?:p|div|br|li|tr|td|h[1-6]|section|article|span|a)\b[^>]*>", "\n", html)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", html))


TITLE_WORDS = re.compile(r"(?i)\b(hr|human|resources?|talent|acquisition|recruit\w*|manager|director|head|officer|founder|"
                         r"executive|lead|team|contact|email|mail|phone|office|careers?|jobs?|send|write|call)\b")


def _name_title_near(text: str, email: str) -> Dict[str, str]:
    """A name / title printed on the same line as the email or in the 3 lines above it. The search stops at
    a line holding another email, so one person's name is never given to someone else's address."""
    lines = text.split("\n")
    idx = next((i for i, ln in enumerate(lines) if email in ln.lower()), -1)
    if idx < 0:
        return {"name": "", "title": ""}
    cand = [lines[idx].lower().split(email)[0] and lines[idx][:lines[idx].lower().index(email)]]
    for j in range(idx - 1, max(-1, idx - 4), -1):
        if "@" in lines[j]:
            break
        cand.append(lines[j])
    name = title = ""
    for ln in cand:
        ln = ln.strip()
        if not ln:
            continue
        if not title:
            t = TITLE_RE.search(ln)
            if t:
                title = re.sub(r"\s+", " ", t.group(1)).strip()
        if not name:
            for m in NAME_RE.finditer(ln):
                c = m.group(1).strip()
                if c.lower() not in NOT_NAMES and not TITLE_WORDS.search(c):
                    name = c
                    break
    return {"name": name, "title": title}


def extract_contacts(html: str, domain: Optional[str] = None) -> List[Dict[str, str]]:
    """Every distinct email published on the page: [{email, name, title}]. If `domain` is given, only
    addresses on that domain (or a subdomain) are returned, so partner / customer emails are ignored."""
    if not html:
        return []
    found: Dict[str, Dict[str, str]] = {}

    def add(email: str, name: str = "", title: str = ""):
        email = _clean(email)
        if not _valid_shape(email):
            return
        if domain:
            d = email.split("@", 1)[1]
            if not (d == domain or d.endswith("." + domain)):
                return
        cur = found.setdefault(email, {"email": email, "name": "", "title": ""})
        cur["name"] = cur["name"] or name
        cur["title"] = cur["title"] or title

    for m in re.finditer(r'data-cfemail="([0-9a-fA-F]+)"', html):
        add(decode_cfemail(m.group(1)))
    for m in re.finditer(r"/cdn-cgi/l/email-protection#([0-9a-fA-F]+)", html):
        add(decode_cfemail(m.group(1)))
    for m in re.finditer(r'(?i)href=["\']mailto:([^"\'?>\s]+)', html):
        add(_deobfuscate(m.group(1)))
    for m in re.finditer(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html):
        try:
            items: List[Dict[str, str]] = []
            _walk_jsonld(json.loads(m.group(1)), items)
            for it in items:
                add(it["email"], it["name"], it["title"])
        except (ValueError, TypeError):
            continue
    shown = re.sub(r'(?is)<a\b[^>]*data-cfemail="([0-9a-fA-F]+)"[^>]*>.*?</a>',
                   lambda m: " " + decode_cfemail(m.group(1)) + " ", html)
    shown = re.sub(r'(?is)<a\b[^>]*href=["\']mailto:([^"\'?>\s]+)[^>]*>.*?</a>',
                   lambda m: " " + _deobfuscate(m.group(1)) + " ", shown)
    text = _visible_text(shown)
    plain = _deobfuscate(text)
    for m in EMAIL_RE.finditer(plain):
        add(m.group(0))
    # attach a name / title printed next to the email (only when the page shows both)
    for email, info in found.items():
        if not info["name"] or not info["title"]:
            near = _name_title_near(plain, email)
            info["name"] = info["name"] or near["name"]
            info["title"] = info["title"] or near["title"]
    return list(found.values())


def internal_links(html: str, base_url: str, limit: int = 8) -> List[str]:
    """Same-site links that look like contact / careers / team / about pages."""
    if not html:
        return []
    host = urllib.parse.urlparse(base_url).netloc.lower().removeprefix("www.")
    out: List[str] = []
    seen: Set[str] = set()
    for m in re.finditer(r'(?i)<a\b[^>]*?href=["\']([^"\'#]+)["\']', html):
        href = m.group(1).strip()
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urllib.parse.urljoin(base_url, href)
        p = urllib.parse.urlparse(url)
        if p.scheme not in ("http", "https") or p.netloc.lower().removeprefix("www.") != host:
            continue
        path = p.path.lower()
        if not any(w in path for w in LINK_WORDS) or path.endswith(BAD_TAIL + (".pdf", ".zip", ".doc", ".docx")):
            continue
        clean = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) >= limit:
            break
    return out
