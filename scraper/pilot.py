"""Pilot workflow for new companies, with Apollo used by hand (no paid API).

  1. worksheet : LinkedIn jobs -> up to N companies that have no HR contact yet -> an Excel sheet.
                 Akshita Y fills HR Name / HR Title / HR Email / Mobile NO: / HR Profile URL from Apollo and
                 writes "Yes" in the 'Apollo Verified' column only for green-marked emails.
  2. ingest    : the filled sheet goes through the intelligent tool. Rows that pass are appended to
                 leads_with_hr.xlsx (so Find Leads can use them); phone-only rows go to a follow-up CSV;
                 everything else is reported with a reason.  Only individual, verified emails are saved.

  python pilot.py worksheet --query "Python Developer" --location Pune --max 20 --out pilot_worksheet.xlsx
  python pilot.py ingest pilot_worksheet.xlsx            (add --dry-run to only see the report)
"""
import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from company_discovery import collect_companies, find_domain
from intelligent_filter import apply_filter
from lead_validation import NOT_DISCLOSED, is_blank, validate_email
from linkedin_hr_scraper import HR_EXCEL_FILE, run_master_job_army

SHEET_COLUMNS = ["Company", "Company Domain", "Location", "Open Positions", "Job Title", "Job URL",
                 "HR Name", "HR Title", "HR Email", "Mobile NO:", "HR Profile URL", "Apollo Verified"]
YES = {"yes", "y", "true", "1", "green", "verified"}


def make_worksheet(scraped_jobs: List[Dict[str, Any]], max_companies: int, out_path: Path, find_dom=find_domain) -> int:
    rows = []
    for entry in collect_companies(scraped_jobs)[:max_companies]:
        try:
            domain = find_dom(entry["company"]) or ""
        except Exception:  # a flaky website must not stop the worksheet
            domain = ""
        rows.append({
            "Company": entry["company"], "Company Domain": domain,
            "Location": entry["locations"][0] if entry["locations"] else "",
            "Open Positions": len(entry["positions"]),
            "Job Title": entry["positions"][0] if entry["positions"] else "",
            "Job URL": entry["job_urls"][0] if entry["job_urls"] else "",
            "HR Name": "", "HR Title": "", "HR Email": "", "Mobile NO:": "", "HR Profile URL": "", "Apollo Verified": "",
        })
    pd.DataFrame(rows, columns=SHEET_COLUMNS).to_excel(out_path, index=False)
    return len(rows)


def _clean(v: Any) -> str:
    return "" if is_blank(v) else str(int(v)) if isinstance(v, float) and v == int(v) else str(v).strip()


def ingest_sheet(sheet_path: Path, hr_path: Path = None, dry_run: bool = False,
                 followup_path: Path = None) -> Dict[str, Any]:
    """Validate a filled worksheet and append the good rows to the HR workbook. Returns a report."""
    hr_path = Path(hr_path or HR_EXCEL_FILE)
    df = pd.read_excel(sheet_path)
    existing = pd.read_excel(hr_path) if hr_path.exists() else pd.DataFrame()
    known_emails = {str(e).strip().lower() for e in existing.get("HR Email", []) if not is_blank(e)}

    report: Dict[str, Any] = {"rows": 0, "added": [], "phone_only": [], "rejected": []}
    leads, src = [], []
    for _, row in df.iterrows():
        r = {c: _clean(row.get(c)) for c in SHEET_COLUMNS}
        if not (r["HR Email"] or r["Mobile NO:"]):
            continue  # row not filled yet
        report["rows"] += 1
        email_ok = r["HR Email"] and r["Apollo Verified"].lower() in YES
        if r["HR Email"] and not email_ok:
            report["rejected"].append((r["Company"], "email not marked Apollo-verified (green)"))
            r["HR Email"] = ""  # unverified email must not travel on; a valid phone can still count
        leads.append({"COMPANY": r["Company"], "JOB TITLE": r["Job Title"] or "HR", "AREA / LOCATION": r["Location"],
                      "JOB URL": r["Job URL"], "HR NAME": r["HR Name"] or NOT_DISCLOSED, "HR TITLE": r["HR Title"],
                      "HR EMAIL": r["HR Email"] or NOT_DISCLOSED, "HR PHONE": r["Mobile NO:"] or NOT_DISCLOSED,
                      "HR PROFILE URL": r["HR Profile URL"], "SOURCE": "Apollo (manual)"})
        src.append(r)

    kept, _ = apply_filter(leads, "any") if leads else ([], "")
    kept_keys = {(k["COMPANY"], k["HR EMAIL"], k["HR PHONE"]): k for k in kept}
    new_rows = []
    for lead, r in zip(leads, src):
        k = kept_keys.get((lead["COMPANY"], lead["HR EMAIL"], lead["HR PHONE"]))
        if k is None:
            if not any(c == r["Company"] for c, _ in report["rejected"]):
                report["rejected"].append((r["Company"], "no valid email or mobile"))
            continue
        email = r["HR Email"].lower()
        status = str(k.get("TOOL_EMAIL_STATUS") or "").lower()
        if email and any(w in status for w in ("no mx", "invalid", "disposable", "syntax")):
            report["rejected"].append((r["Company"], f"email failed the tool's check ({k['TOOL_EMAIL_STATUS']})"))
            continue
        if email and validate_email(email) == "Valid" and k["TOOL_SELECTED"]:
            if email in known_emails:
                report["rejected"].append((r["Company"], "duplicate: email already in HR file"))
                continue
            known_emails.add(email)
            new_rows.append({**r, "HR Email": email, "Source": "Apollo (manual)",
                             "Mobile NO:": k["HR PHONE"] if k["HR PHONE"] != NOT_DISCLOSED else r["Mobile NO:"]})
            report["added"].append((r["Company"], email))
        elif email and validate_email(email) == "Generic":
            report["rejected"].append((r["Company"], "generic mailbox (hr@/careers@) is not saved to the CRM"))
        else:
            report["phone_only"].append({"Company": r["Company"], "HR Name": r["HR Name"], "HR Phone": k["HR PHONE"],
                                         "Reason": k.get("SELECTION_REASON", "")})
    if not dry_run:
        if new_rows:
            add = pd.DataFrame(new_rows)
            for col in existing.columns:
                if col not in add.columns:
                    add[col] = ""
            out = pd.concat([existing, add[list(existing.columns)]], ignore_index=True) if len(existing.columns) else add
            out.to_excel(hr_path, index=False)
        if report["phone_only"]:
            fp = Path(followup_path or Path(sheet_path).with_name("pilot_phone_followup.csv"))
            with open(fp, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["Company", "HR Name", "HR Phone", "Reason"])
                w.writeheader()
                w.writerows(report["phone_only"])
            report["followup_file"] = str(fp)
    return report


def print_report(rep: Dict[str, Any]) -> None:
    print(f"[+] Rows filled in sheet: {rep['rows']}")
    print(f"[+] Added to HR file (email saved for CRM): {len(rep['added'])}")
    for c, e in rep["added"]:
        print(f"      {c}: {e}")
    print(f"[+] Phone-only follow-up (not for CRM): {len(rep['phone_only'])}")
    print(f"[-] Rejected: {len(rep['rejected'])}")
    for c, why in rep["rejected"]:
        print(f"      {c}: {why}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worksheet")
    w.add_argument("--query", required=True)
    w.add_argument("--location", default="")
    w.add_argument("--max", type=int, default=20)
    w.add_argument("--pages", type=int, default=3)
    w.add_argument("--out", default="pilot_worksheet.xlsx")
    w.add_argument("--no-domain", action="store_true", help="skip the website lookup (faster, domain column stays empty)")
    i = sub.add_parser("ingest")
    i.add_argument("sheet")
    i.add_argument("--hr-file", default=None)
    i.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "worksheet":
        jobs = run_master_job_army(search_query=a.query, limit=None, location=a.location, max_pages=a.pages)
        n = make_worksheet(jobs, a.max, Path(a.out), find_dom=(lambda c: "") if a.no_domain else find_domain)
        print(f"[+] {n} companies written to {a.out}. Fill the HR columns from Apollo, mark green emails 'Yes' in 'Apollo Verified'.")
    else:
        print_report(ingest_sheet(Path(a.sheet), a.hr_file, a.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
