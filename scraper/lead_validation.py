"""Contact validation + scoring shared by linkedin_hr_scraper.py and main.py.

Rules come from Akshita's validator.py (format check, disposable domains, Indian
mobile rules, dummy numbers) so the scraper, the HR search and the exports all
agree on what a *usable* contact is.
"""
import os
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
    # more shared mailboxes: never a person, so never an individual lead
    "sales", "marketing", "billing", "accounts", "account", "finance", "legal", "press", "media", "privacy",
    "abuse", "noreply", "no-reply", "webmaster", "postmaster", "feedback", "help", "service", "services",
    "customercare", "customer-care", "enquiries", "partners", "partnership", "business", "general", "reception",
}
# HR-team mailboxes (hr@, careers@, recruitment@ ...). With ACCEPT_HR_MAILBOX=1 they count as valid emails
# (they are the address a company itself publishes for hiring). info@, support@, admin@, sales@ ... never do.
HR_ROLE_RE = re.compile(r"^(hr|careers?|jobs?|recruit[a-z]*|talent[a-z]*|hiring|people|humanresources)([._-][a-z0-9._-]+)?$")
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
    base = local.split("+")[0].lower()
    if base in GENERIC_EMAIL_NAMES:
        return "Valid" if (accept_hr_mailbox() and HR_ROLE_RE.match(base)) else "Generic"
    return "Valid"


def accept_hr_mailbox() -> bool:
    return os.environ.get("ACCEPT_HR_MAILBOX", "0").strip().lower() in ("1", "true", "yes", "on")


def email_kind(value) -> str:
    """personal | hr_mailbox | generic | '' (for a missing / invalid email)."""
    if validate_email(value) in ("Missing", "Invalid", "Invalid (Disposable)"):
        return ""
    base = str(value).strip().rsplit("@", 1)[0].split("+")[0].lower()
    if HR_ROLE_RE.match(base):
        return "hr_mailbox"
    return "generic" if base in GENERIC_EMAIL_NAMES else "personal"


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
    if email_status == "Valid" and email_kind(email) == "hr_mailbox":
        return "Unverified (HR mailbox)"
    if email_status == "Valid":
        return "Unverified (HR data matched)" if matched_hr else "Unverified"
    if email_status == "Generic":
        return "Unverified (generic email)"
    if email_status.startswith("Invalid"):
        return "Not Disclosed (" + email_status.lower() + ")"
    return NOT_DISCLOSED


def lead_confidence(lead: Dict) -> tuple:
    """How sure we are that this lead can be reached: ("high" | "medium" | "low" | "none", reason).
    high   = valid personal email AND a named HR contact
    medium = valid personal email without a name, or a published HR mailbox (hr@, careers@)
    low    = no usable email, but a valid mobile (follow-up call list)
    none   = nothing usable
    A contact matched only by company name (not this exact job) is capped at medium."""
    email_status = validate_email(lead.get("HR EMAIL"))
    kind = email_kind(lead.get("HR EMAIL")) if email_status == "Valid" else ""
    named = not is_blank(lead.get("HR NAME"))
    phone_ok = validate_phone(lead.get("HR PHONE"))[0] == "Valid"
    if kind == "personal" and named:
        level, why = "high", "Personal email and a named HR contact"
        if lead.get("HR MATCH") == "company":
            level, why = "medium", "Personal email and named HR contact, matched by company only"
        return level, why
    if kind == "personal":
        return "medium", "Personal email, HR name not known"
    if kind == "hr_mailbox":
        return "medium", "Published HR mailbox (hr@ / careers@), not a named person"
    if phone_ok:
        return "low", "Valid mobile only: usable for follow-up calls, not for the CRM"
    return "none", "No usable email or mobile"


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
