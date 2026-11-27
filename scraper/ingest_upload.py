"""Upload ingestion: validate and qualify an uploaded lead file (.xlsx, .xls, .csv).

Same rules as `pilot.py ingest` (they share lead_validation.py and the intelligent tool through
intelligent_filter.evaluate), applied to any file with name / email / phone columns instead of only
the Apollo worksheet:

  * only an individual, valid, non-disposable email can be *qualified* (it may go to the CRM)
  * generic mailboxes (hr@, careers@) are rejected
  * a valid mobile without a usable email is *phone_only* (follow-up list, never the CRM)
  * if the file has an "Apollo Verified" column, an email is only accepted when it says Yes
  * the intelligent tool adds the score, expiry/duplicate verdicts and the email check (MX)

Nothing is invented: every count in the summary is computed from the rows of the file.
"""
import io
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from intelligent_filter import evaluate, filter_enabled
from lead_validation import is_blank, lead_confidence, validate_email, validate_phone

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
CHUNK = 100
ALLOWED_EXT = (".xlsx", ".xls", ".csv")

ALIASES = {
    "name": {"name", "fullname", "hrname", "contactname", "leadname", "person"},
    "email": {"email", "emailaddress", "hremail", "mail", "workemail", "emailid"},
    "phone": {"phone", "mobile", "mobileno", "phonenumber", "hrphone", "contactnumber", "mobilenumber", "mobileno:"},
    "company": {"company", "companyname", "organization", "organisation", "employer"},
    "title": {"jobtitle", "title", "hrtitle", "designation", "position", "role"},
    "location": {"location", "arealocation", "city"},
    "verified": {"apolloverified", "verified"},
}


class UploadError(Exception):
    """A problem with the uploaded file itself. `code` is stable so the UI can react to it."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(header: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def _read(filename: str, data: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    if not name.endswith(ALLOWED_EXT):
        raise UploadError("invalid_format", "Unsupported file type. Upload a .xlsx, .xls or .csv file.")
    if not data:
        raise UploadError("empty_file", "The file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadError("too_large", f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    try:
        if name.endswith(".csv"):
            text = None
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=None, engine="python")
        elif name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(data), dtype=str, engine="openpyxl")
        else:
            try:
                df = pd.read_excel(io.BytesIO(data), dtype=str, engine="xlrd")
            except ImportError:
                raise UploadError("xls_unsupported", "Reading .xls needs the xlrd package on the scraper service. "
                                                     "Save the file as .xlsx or .csv and upload again.")
    except UploadError:
        raise
    except pd.errors.EmptyDataError:
        raise UploadError("empty_file", "The file has no rows.")
    except Exception as exc:  # corrupted file, wrong extension, password protected ...
        raise UploadError("unreadable", f"Could not read the file: {str(exc)[:160]}")
    df = df.dropna(how="all")
    if df.empty:
        raise UploadError("empty_file", "The file has a header but no data rows.")
    return df


def _map_columns(columns) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for col in columns:
        key = _norm(col)
        for field, names in ALIASES.items():
            if field not in found and key in {_norm(n) for n in names}:
                found[field] = col
    if "email" not in found and "phone" not in found:
        raise UploadError(
            "missing_columns",
            "No email or phone column found. Add a column named Email (or HR Email) and, optionally, "
            "Name, Phone / Mobile, Company, Job Title.",
        )
    return found


def _cell(row, col: Optional[str]) -> str:
    if not col:
        return ""
    v = row.get(col)
    return "" if is_blank(v) else str(v).strip()


def _score100(score: Any) -> int:
    try:
        s = float(score or 0)
    except (TypeError, ValueError):
        return 0
    return int(round(s * 100 if s <= 1 else s))


def run_ingest(filename: str, data: bytes, progress: Optional[Callable[[Dict[str, Any]], None]] = None,
               mode: str = "any") -> Dict[str, Any]:
    """Validate an uploaded file. Raises UploadError for file-level problems. Returns the full report."""
    df = _read(filename, data)
    if len(df) > MAX_ROWS:
        raise UploadError("too_many_rows", f"The file has {len(df)} rows; the limit is {MAX_ROWS}.")
    cols = _map_columns(df.columns)
    has_verified = "verified" in cols

    rows: List[Dict[str, Any]] = []
    pending: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []  # (result row, tool lead)
    seen: Dict[str, int] = {}
    stats = {"total": 0, "qualified": 0, "phone_only": 0, "rejected": 0, "duplicates": 0,
             "invalid_email": 0, "invalid_phone": 0, "failed": 0}
    warnings: List[str] = []
    if "email" not in cols:
        warnings.append("No email column: every row can only be a phone-only follow-up.")
    if "name" not in cols:
        warnings.append("No name column: leads are named after the company.")

    def add(row: Dict[str, Any]):
        rows.append(row)

    for pos, (_, src) in enumerate(df.iterrows()):
        excel_row = pos + 2  # row 1 is the header
        email_raw, phone_raw = _cell(src, cols.get("email")), _cell(src, cols.get("phone"))
        name, company = _cell(src, cols.get("name")), _cell(src, cols.get("company"))
        title, location = _cell(src, cols.get("title")), _cell(src, cols.get("location"))
        if not any((email_raw, phone_raw, name, company)):
            continue  # blank line
        stats["total"] += 1
        email_state = validate_email(email_raw)
        phone_state, phone_e164 = validate_phone(phone_raw)
        row = {"row": excel_row, "name": name or (f"HR — {company}" if company else ""), "email": email_raw.lower(),
               "phone": phone_e164 or phone_raw, "company": company, "title": title, "location": location,
               "email_status": email_state if email_raw else "Missing",
               "phone_status": phone_state if phone_raw else "Missing",
               "score": 0, "status": "rejected", "reasons": []}
        if email_raw and email_state.startswith("Invalid"):
            stats["invalid_email"] += 1
        if phone_raw and phone_state.startswith("Invalid"):
            stats["invalid_phone"] += 1

        reasons: List[str] = []
        email_ok = email_state == "Valid"
        if email_raw and not email_ok:
            reasons.append({"Generic": "Generic mailbox (hr@, careers@) is not saved to the CRM",
                            "Invalid (Disposable)": "Disposable email domain"}.get(email_state, "Invalid email format"))
        if email_ok and has_verified and _cell(src, cols["verified"]).lower() not in {"yes", "y", "true", "1", "verified", "green"}:
            email_ok = False
            reasons.append("Email not marked Apollo-verified")
        if email_ok and email_raw.lower() in seen:
            row.update(status="duplicate", reasons=[f"Duplicate of row {seen[email_raw.lower()]} in this file"])
            stats["duplicates"] += 1
            add(row)
            continue
        if email_ok and not row["name"]:
            email_ok = False
            reasons.append("Name and company are both missing")
        if email_ok:
            seen[email_raw.lower()] = excel_row
            lead = {"COMPANY": company, "JOB TITLE": title or "HR", "AREA / LOCATION": location, "HR NAME": name,
                    "HR TITLE": title, "HR EMAIL": email_raw, "HR PHONE": phone_raw, "SOURCE": "Upload"}
            row["reasons"] = reasons
            pending.append((row, lead))
            add(row)
            continue
        # no usable email: a valid mobile still makes a follow-up lead
        if phone_state == "Valid":
            row.update(status="phone_only", reasons=reasons + ["No usable email: kept as phone-only follow-up"])
            stats["phone_only"] += 1
        else:
            if phone_raw and not phone_state == "Valid":
                reasons.append("Invalid phone number" if phone_state != "Invalid (Dummy)" else "Dummy phone number")
            if not email_raw and not phone_raw:
                reasons.append("No email or phone")
            row.update(status="rejected", reasons=reasons or ["No usable contact"])
            stats["rejected"] += 1
        add(row)

    if stats["total"] == 0:
        raise UploadError("empty_file", "The file has no usable rows.")

    # Intelligent tool: score, expiry, MX / email check. Done in chunks so progress is real.
    done = stats["phone_only"] + stats["rejected"] + stats["duplicates"]
    if progress:
        progress({"processed": done, "total": stats["total"]})
    for i in range(0, len(pending), CHUNK):
        part = pending[i:i + CHUNK]
        try:
            annotated, engine = evaluate([lead for _, lead in part], mode) if filter_enabled() else (None, "off")
        except Exception as exc:  # partial failure: keep going, mark these rows
            annotated, engine = None, "error"
            warnings.append(f"Intelligent tool failed for rows {part[0][0]['row']}-{part[-1][0]['row']}: {str(exc)[:120]}")
            for row, _ in part:
                row.update(status="rejected", reasons=["Processing error: the intelligent tool failed for this row"])
                stats["rejected"] += 1
                stats["failed"] += 1
            done += len(part)
            if progress:
                progress({"processed": done, "total": stats["total"]})
            continue
        for k, (row, _) in enumerate(part):
            verdict = annotated[k] if annotated else {}
            klass = str(verdict.get("LEAD_CLASS") or "")
            e_status = str(verdict.get("TOOL_EMAIL_STATUS") or "")
            row["tool_engine"] = engine
            if annotated:
                row["score"] = _score100(verdict.get("TOOL_SCORE"))
                if e_status:
                    row["email_status"] = e_status
            if klass == "Expired":
                row.update(status="rejected", reasons=row["reasons"] + ["Lead expired"])
                stats["rejected"] += 1
            elif klass == "Duplicate":
                row.update(status="duplicate", reasons=row["reasons"] + ["Duplicate detected by the intelligent tool"])
                stats["duplicates"] += 1
            elif annotated and any(w in e_status.lower() for w in ("no mx", "invalid", "disposable", "syntax")):
                stats["invalid_email"] += 1
                row.update(status="rejected", reasons=row["reasons"] + [f"Email failed the check ({e_status})"])
                stats["rejected"] += 1
            elif annotated and not verdict.get("TOOL_SELECTED"):
                row.update(status="rejected", reasons=row["reasons"] + [verdict.get("SELECTION_REASON") or "Not selected"])
                stats["rejected"] += 1
            else:
                row["status"] = "qualified"
                stats["qualified"] += 1
        done += len(part)
        if progress:
            progress({"processed": done, "total": stats["total"]})

    for r in rows:  # how sure we are, shown next to every row
        r["confidence"], r["confidence_reason"] = (
            lead_confidence({"HR EMAIL": r["email"], "HR NAME": r["name"] if "name" in cols else "", "HR PHONE": r["phone"]})
            if r["status"] in ("qualified", "phone_only") else ("none", "; ".join(r["reasons"]) or "Not usable"))
    return {"summary": stats, "rows": rows, "warnings": warnings, "columns": cols}
