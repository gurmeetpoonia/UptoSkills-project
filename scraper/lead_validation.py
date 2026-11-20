"""Contact validation + scoring shared by linkedin_hr_scraper.py and main.py.

Rules come from Akshita's validator.py (format check, disposable domains, Indian
mobile rules, dummy numbers) so the scraper, the HR search and the exports all
agree on what a *usable* contact is.
"""
import re
from typing import Dict, Tuple

NOT_DISCLOSED = "Not Disclosed"

DISPOSABLE_DOMAINS = {
    "10minutemail.com", "guerrillamail.com", "guerrillamail.biz", "mailinator.com",
    "tempmail.com", "yopmail.com", "throwawaymail.com", "getnada.com", "trashmail.com",
    "sharklasers.com", "maildrop.cc", "dispostable.com", "temp-mail.org",
}
GENERIC_EMAIL_NAMES = {
    "careers", "career", "jobs", "job", "hr", "info", "contact", "hello", "support",
    "admin", "recruitment", "recruiter", "talent", "hiring", "office", "mail",
    "enquiry", "inquiry", "apply", "team",
}
DUMMY_NUMBERS = {
    "0000000000", "1111111111", "2222222222", "3333333333", "4444444444",
    "5555555555", "6666666666", "7777777777", "8888888888", "9999999999",
    "1234567890", "0987654321", "0123456789", "9876543210",
}

_LOCAL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")
_LABEL_RE = re.compile(r"[A-Za-z0-9-]+")


def is_blank(value) -> bool:
    return str(value if value is not None else "").strip().lower() in (
        "", "nan", "none", "null", "not disclosed", "not found", "n/a", "na", "-", "--", "unknown")


def validate_email(value) -> str:
    """Missing | Invalid | Invalid (Disposable) | Generic | Valid"""
    if is_blank(value):
        return "Missing"
    email = str(value).strip()
    if len(email) > 254 or email.count("@") != 1 or re.search(r"\s", email):
        return "Invalid"
    local, domain = email.rsplit("@", 1)
    if not local or len(local) > 64 or not domain or "." not in domain or not _LOCAL_RE.fullmatch(local):
        return "Invalid"
    labels = domain.split(".")
    if any(not l or len(l) > 63 or l.startswith("-") or l.endswith("-") or not _LABEL_RE.fullmatch(l) for l in labels):
        return "Invalid"
    if labels[-1].isdigit() or len(labels[-1]) < 2:
        return "Invalid"
    if domain.lower() in DISPOSABLE_DOMAINS:
        return "Invalid (Disposable)"
    if local.split("+")[0].lower() in GENERIC_EMAIL_NAMES:
        return "Generic"
    return "Valid"


def validate_phone(value) -> Tuple[str, str]:
    """(status, +91XXXXXXXXXX). status: Missing | Invalid | Invalid (Dummy) | Valid"""
    if is_blank(value):
        return "Missing", ""
    if isinstance(value, float) and value == int(value):
        raw = str(int(value))
    else:
        raw = str(value).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return "Invalid", ""
    if digits in DUMMY_NUMBERS or len(set(digits)) == 1:
        return "Invalid (Dummy)", ""
    return "Valid", "+91" + digits


def verification_label(email: str, email_status: str, matched_hr: bool) -> str:
    """Text the CRM controller understands (it skips 'generic email' and 'Not Disclosed')."""
    if email_status == "Valid":
        return "Unverified (HR data matched)" if matched_hr else "Unverified"
    if email_status == "Generic":
        return "Unverified (generic email)"
    if email_status.startswith("Invalid"):
        return "Not Disclosed (" + email_status.lower() + ")"
    return NOT_DISCLOSED


def score_lead(lead: Dict) -> int:
    """0-100. Contact quality dominates: a lead nobody can reach is not a good lead."""
    score = 0
    if not is_blank(lead.get("COMPANY")):
        score += 10
    if not is_blank(lead.get("JOB TITLE")):
        score += 10
    if not is_blank(lead.get("AREA / LOCATION")):
        score += 5
    if len(str(lead.get("FULL DESCRIPTION") or "")) >= 200:
        score += 10
    if not is_blank(lead.get("HR NAME")):
        score += 10
    if validate_email(lead.get("HR EMAIL")) == "Valid":
        score += 35
    elif validate_email(lead.get("HR EMAIL")) == "Generic":
        score += 10
    if validate_phone(lead.get("HR PHONE"))[0] == "Valid":
        score += 20
    # HR contact found only by company name (not this exact job) is less certain.
    if lead.get("HR MATCH") == "company":
        return min(score, 90)
    return min(score, 100)
