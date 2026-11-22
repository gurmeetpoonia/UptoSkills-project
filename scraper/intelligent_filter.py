"""Connects the scraper to the intelligent tool (leadscore-termux).

Every scraped lead is passed through the tool, which validates email / mobile, removes expired
and duplicate leads, scores each lead and gives a reason. Three ways to reach the tool, tried in order:

  1. HTTP   - env INTELLIGENT_TOOL_URL (e.g. http://127.0.0.1:5000), optional LEADSCORE_API_KEY
  2. Local  - import tools/leadscore-termux/app.py from this repo (or env LEADSCORE_DIR)
  3. Built-in - lead_validation.py rules (same selection rule: valid email or valid mobile)

The scraper never fails because the tool is unavailable: it falls back and says which one it used.
Set INTELLIGENT_FILTER=off to switch the filter off.
"""
import importlib.util
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lead_validation import is_blank, validate_email, validate_phone

HERE = Path(__file__).resolve().parent
MODES = ("any", "email", "mobile", "both")
_local_module = None


def filter_enabled() -> bool:
    return os.environ.get("INTELLIGENT_FILTER", "on").strip().lower() not in ("off", "0", "false", "no")


def to_tool_records(leads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Scraper lead -> row with the headers the tool understands. 'Not Disclosed' becomes blank."""
    def val(lead, key):
        v = lead.get(key)
        return "" if is_blank(v) else str(v).strip()
    return [{
        "Company": val(l, "COMPANY"), "Job Title": val(l, "JOB TITLE"), "Location": val(l, "AREA / LOCATION"),
        "Job URL": val(l, "JOB URL"), "HR Name": val(l, "HR NAME"), "HR Title": val(l, "HR TITLE"),
        "HR Email": val(l, "HR EMAIL"), "Mobile NO:": val(l, "HR PHONE"), "HR Profile URL": val(l, "HR PROFILE URL"),
        "Source": val(l, "SOURCE"), "Expiry Date": val(l, "EXPIRY DATE"),
    } for l in leads]


# ---------------------------------------------------------------- 1. HTTP
def _via_http(records, mode) -> Dict[str, Any]:
    url = os.environ["INTELLIGENT_TOOL_URL"].rstrip("/") + "/api/ingest"
    headers = {"Content-Type": "application/json"}
    if os.environ.get("LEADSCORE_API_KEY"):
        headers["X-Api-Key"] = os.environ["LEADSCORE_API_KEY"]
    body = json.dumps({"leads": records, "mode": mode, "source": "scraper"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=120) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------- 2. local import
def _load_local():
    global _local_module
    if _local_module is not None:
        return _local_module
    folder = Path(os.environ.get("LEADSCORE_DIR") or HERE.parent / "tools" / "leadscore-termux")
    app_py = folder / "app.py"
    if not app_py.exists():
        raise FileNotFoundError(f"intelligent tool not found at {app_py}")
    # keep the tool's database and log out of the repository folder
    os.environ.setdefault("LEADSCORE_DATA_DIR", os.path.join(tempfile.gettempdir(), "leadscore-scraper"))
    spec = importlib.util.spec_from_file_location("leadscore_app", app_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _local_module = module
    return module


def _via_local(records, mode) -> Dict[str, Any]:
    return _load_local().evaluate_leads(records, mode, persist=False, filename="scraper")


# ---------------------------------------------------------------- 3. built-in fallback
def _builtin(leads, mode) -> Dict[str, Any]:
    results = []
    for i, lead in enumerate(leads):
        email_ok = validate_email(lead.get("HR EMAIL")) in ("Valid", "Generic")
        mobile_ok = validate_phone(lead.get("HR PHONE"))[0] == "Valid"
        ok = {"any": email_ok or mobile_ok, "email": email_ok, "mobile": mobile_ok, "both": email_ok and mobile_ok}[mode]
        have = [x for x, f in (("valid email", email_ok), ("valid mobile", mobile_ok)) if f]
        results.append({
            "index": i, "selected": ok,
            "selection_reason": (f"Selected ({mode}): " + " and ".join(have)) if ok else
                                f"Not selected ({mode}): no usable contact",
            "score": round(float(lead.get("SCORE") or 0) / 100, 2),
            "lead_class": "Ready" if ok else "Rejected", "class_reason": "", "expiry_date": "", "is_duplicate": False})
    return {"mode": mode, "results": results}


def evaluate(leads: List[Dict[str, Any]], mode: str = "any") -> Tuple[List[Dict[str, Any]], str]:
    """Annotate every scraper lead with the tool's verdict. Returns (annotated leads, engine used)."""
    mode = mode if mode in MODES else "any"
    records = to_tool_records(leads)
    engine, verdict = "built-in", None
    attempts = []
    if os.environ.get("INTELLIGENT_TOOL_URL"):
        attempts.append(("tool-http", _via_http))
    attempts.append(("tool-local", _via_local))
    for name, fn in attempts:
        try:
            verdict, engine = fn(records, mode), name
            break
        except (urllib.error.URLError, OSError, ValueError, KeyError, FileNotFoundError, ImportError, SyntaxError) as e:
            print(f"[-] Intelligent tool via {name} unavailable: {e}")
    if verdict is None:
        verdict = _builtin(leads, mode)
    by_index = {r["index"]: r for r in verdict["results"]}
    annotated = []
    for i, lead in enumerate(leads):
        r = by_index.get(i, {})
        lead = dict(lead)
        lead.update({
            "TOOL_SELECTED": bool(r.get("selected")), "SELECTION_REASON": r.get("selection_reason", ""),
            "LEAD_CLASS": r.get("lead_class", ""), "CLASS_REASON": r.get("class_reason", ""),
            "TOOL_SCORE": r.get("score", 0.0), "TOOL_ENGINE": engine,
            "TOOL_EMAIL_STATUS": r.get("email_status", ""), "TOOL_PHONE_STATUS": r.get("phone_status", ""),
        })
        annotated.append(lead)
    return annotated, engine


def apply_filter(leads: List[Dict[str, Any]], mode: str = "any") -> Tuple[List[Dict[str, Any]], str]:
    """Keep only the leads the tool selected. Returns (selected leads best first, note about what was removed)."""
    if not leads or not filter_enabled():
        return leads, ""
    annotated, engine = evaluate(leads, mode)
    kept = [l for l in annotated if l["TOOL_SELECTED"]]
    kept.sort(key=lambda l: (l["TOOL_SCORE"], l.get("SCORE", 0)), reverse=True)
    removed = len(annotated) - len(kept)
    expired = sum(1 for l in annotated if l["LEAD_CLASS"] == "Expired")
    dupes = sum(1 for l in annotated if l["LEAD_CLASS"] == "Duplicate")
    note = ""
    if removed:
        nocontact = removed - expired - dupes
        parts = []
        if nocontact > 0:
            parts.append(f"{nocontact} no valid email or mobile")
        if expired:
            parts.append(f"{expired} expired")
        if dupes:
            parts.append(f"{dupes} duplicate")
        note = f"{removed} of {len(annotated)} leads removed by the intelligent tool: " + ", ".join(parts) + f" [{engine}]."
    return kept, note
