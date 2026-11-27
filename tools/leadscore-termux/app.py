#!/usr/bin/env python3
"""
Lead Intelligence & Qualification Tool for Android Termux
==========================================================
Isolated, self-contained, pure-Python lead qualification application.
Runs locally at http://127.0.0.1:5000 with SQLite persistent storage.

Zero Rust dependencies. Zero C-compiler dependencies.
Designed specifically for Android Termux stability and longevity.

Author: Senior Python Architect & QA Engineer
"""

import os
import sys
import re
import csv
import json
import time
import threading
import tempfile
import hmac
from concurrent.futures import ThreadPoolExecutor, as_completed
import socket
import sqlite3
import logging
import zipfile
import argparse
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ==============================================================================
# DIRECTORY & PERSISTENT STORAGE PATHS (Isolated Project Structure)
# ==============================================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("LEADSCORE_DATA_DIR") or os.path.join(APP_DIR, "data")  # override lets other programs import this file without touching the repo folder
DB_PATH = os.path.join(DATA_DIR, "leads.db")
LOG_PATH = os.path.join(DATA_DIR, "lead_intelligence.log")

os.makedirs(DATA_DIR, exist_ok=True)

# Configure logging to both console and data/lead_intelligence.log
logger = logging.getLogger("LeadIntel")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info(f"Initialized Lead Intelligence Engine. Root: {APP_DIR}")

# ==============================================================================
# DISPOSABLE DOMAINS & ROLE PREFIXES
# ==============================================================================
# Obvious fake mobile numbers (also from the team validator): reject them even though they are 10 digits.
DUMMY_PHONE_NUMBERS: Set[str] = {
    "1234567890", "0123456789", "0987654321", "9876543210", "9876543211", "1111111111", "0000000000",
}

DISPOSABLE_DOMAINS: Set[str] = {
    "getnada.com", "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "getairmail.com",
    "dispostable.com", "throwawaymail.com", "fakeinbox.com", "temp-mail.org",
    "nada.ltd", "mohmal.com", "crazymailing.com", "mytemp.email",
    "burnermail.io", "dropmail.me", "inboxkitten.com", "generator.email",
    "tempinbox.com", "tempail.com", "disposablemail.com", "trashmail.net",
    "mytempmail.com", "spam4.me", "grr.la", "guerrillamail.biz",
    "guerrillamail.de", "guerrillamail.net", "guerrillamail.org",
    "pokemail.net", "spamgourmet.com", "mailcatch.com", "maildrop.cc",
    "binkmail.com", "bobmail.info", "chammy.info", "devnullmail.com",
    "emailondeck.com", "fastmail.fm", "filzmail.com", "harakirimail.com",
    "incognitomail.org", "jetable.org", "kasmail.com", "mailnesia.com",
    "mailnull.com", "mintemail.com", "mytempemail.com", "noclickemail.com",
    "nobulk.com", "owlpic.com", "pookmail.com", "safetymail.info",
    "sendspamhere.com", "soodo.com", "spambox.us", "spamfree24.org",
    "spaml.com", "spamevader.com", "tempe-mail.com", "tmpmail.net",
    "trashymail.com", "wegwerfmail.de", "wegwerfmail.net", "whyspam.me",
    "zoemail.com", "zippymail.info", "0-mail.com", "anonbox.net"
}

ROLE_BASED_PREFIXES: Set[str] = {
    # General company mailboxes
    "info", "information", "contact", "hello", "general",
    "office", "admin", "mail", "team", "enquiry", "enquiries",
    "inquiry", "inquiries", "reception",

    # Customer support and care
    "support", "help", "helpdesk", "service", "services",
    "care", "customercare", "wecare", "customer-care",

    # HR and recruitment
    "hr", "humanresources", "careers", "career", "jobs", "job",
    "recruitment", "recruiting", "recruiter", "talent", "hiring",

    # Business departments
    "sales", "marketing", "billing", "accounts", "finance",
    "press", "media", "partners", "partnerships",

    # Automated or administrative mailboxes
    "feedback", "noreply", "no-reply", "postmaster",
    "webmaster", "infodesk", "desk", "apply"
}

# ==============================================================================
# CANONICAL SCHEMA & EXACT USER COLUMN MAPPINGS
# ==============================================================================
# Specifically accommodates exact spreadsheet headers:
# 'Job Title', 'Company', 'Location', 'Job URL', 'Posted', 'Company Website',
# 'Company Domain', 'Company LinkedIn', 'Source', 'HR Name', 'HR Title',
# 'HR Profile URL', 'HR Email', 'Mobile NO:'
EXACT_COLUMN_ALIASES: Dict[str, List[str]] = {
    "job_title": ["job title", "title", "position", "role", "designation"],
    "company": ["company", "company name", "employer", "organization", "firm"],
    "location": ["location", "city", "country", "job location", "address", "state"],
    "job_url": ["job url", "posting url", "url", "apply url", "link"],
    "posted": ["posted", "posting date", "date", "posted at", "scraped at"],
    "company_website": ["company website", "website", "company url", "web"],
    "company_domain": ["company domain", "domain"],
    "company_linkedin": ["company linkedin", "company linkedin url", "linkedin url", "linkedin"],
    "source": ["source", "job board", "platform", "origin", "scraped from"],
    "hr_name": ["hr name", "contact person", "recruiter name", "hiring manager", "contact name", "name"],
    "hr_title": ["hr title", "recruiter title", "contact title"],
    "hr_profile_url": ["hr profile url", "recruiter profile", "recruiter linkedin", "contact url"],
    "email": ["hr email", "email", "contact email", "recruiter email", "email address", "mail", "e-mail"],
    "phone": ["mobile no:", "mobile no", "mobile", "phone", "telephone", "contact phone", "phone number", "cell", "tel"]
}

EXPIRY_HEADER_TOKENS = (
    "expir", "deadline", "enddate", "endtime", "lastdate", "validtill", "validuntil", "validthrough",
    "closingdate", "closedate", "closesat", "applyby", "lastdatetoapply",
)
# True: a lead is also dropped on its expiry day. False (default): its last valid day is the expiry date itself.
EXPIRY_INCLUSIVE_TODAY = False


def normalize_header_token(h: str) -> str:
    """Normalizes header by stripping punctuation, extra spaces, and lowercase."""
    return re.sub(r"[^a-z0-9]", "", str(h).lower())

def map_column_name(header: str) -> Optional[str]:
    """
    Intelligently maps any spreadsheet header to canonical field.
    Guarantees mapping of 'HR Email' -> 'email' and 'Mobile NO:' -> 'phone'.
    """
    token = normalize_header_token(header)
    if not token:
        return None

    # Never mistake exported status/score/research columns for source contact fields.
    # Example: Email_Status must not overwrite HR_Email; Phone_Status must not
    # overwrite Mobile_NO. This also makes re-importing our own exports safe.
    non_input_suffixes = (
        'status', 'validation', 'validity', 'verified', 'score', 'breakdown',
        'explanation', 'evidence', 'retrievedat', 'qualificationstatus',
        'rejectionreason', 'researchsummary', 'researchsources', 'sourceurls',
        'duplicateof', 'duplicatereason', 'tier', 'leadid'
    )
    if any(token.endswith(suffix) for suffix in non_input_suffixes):
        return None
    if token.startswith(('research', 'companyresearch', 'emailverification', 'phoneverification')):
        return None
    # v1.6.0: an end / expiry / deadline column (checked before the generic "date" rule below).
    if any(key in token for key in EXPIRY_HEADER_TOKENS):
        return "expiry"

    # Check against known aliases
    for canonical, aliases in EXACT_COLUMN_ALIASES.items():
        for alias in aliases:
            if token == normalize_header_token(alias):
                return canonical

    # Substring heuristic checks
    if "hremail" in token or "email" in token or "mail" in token:
        return "email"
    if "mobileno" in token or "mobile" in token or "phone" in token or "cell" in token or "tel" in token:
        return "phone"
    if "jobtitle" in token or "title" in token or "role" in token or "position" in token:
        return "job_title"
    if "company" in token or "employer" in token or "org" in token:
        if "website" in token or "url" in token:
            return "company_website"
        if "domain" in token:
            return "company_domain"
        if "linkedin" in token:
            return "company_linkedin"
        return "company"
    if "hrprofile" in token:
        return "hr_profile_url"
    if "hrname" in token or "recruiter" in token:
        return "hr_name"
    if "hrtitle" in token:
        return "hr_title"
    if "location" in token or "city" in token:
        return "location"
    if "posted" in token or "date" in token:
        return "posted"
    if "source" in token:
        return "source"

    return None

# ==============================================================================
# SQLITE PERSISTENT STORAGE ENGINE
# ==============================================================================
def init_database():
    """Initializes isolated SQLite schema for runs, leads, and research cache."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        total_records INTEGER NOT NULL,
        valid_leads INTEGER DEFAULT 0,
        duplicates_removed INTEGER DEFAULT 0,
        average_score REAL DEFAULT 0.0,
        imported_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        raw_id TEXT,
        job_title TEXT,
        company TEXT,
        location TEXT,
        job_url TEXT,
        posted TEXT,
        company_website TEXT,
        company_domain TEXT,
        company_linkedin TEXT,
        source TEXT,
        hr_name TEXT,
        hr_title TEXT,
        hr_profile_url TEXT,
        email TEXT,
        phone TEXT,
        
        email_valid INTEGER DEFAULT 0,
        email_status TEXT,
        is_role_based INTEGER DEFAULT 0,
        is_disposable INTEGER DEFAULT 0,
        normalized_email TEXT,
        
        phone_valid INTEGER DEFAULT 0,
        phone_status TEXT,
        phone_e164 TEXT,
        phone_country TEXT,
        
        company_researched INTEGER DEFAULT 0,
        company_status TEXT,
        company_industry TEXT,
        company_tech_stack TEXT,
        company_has_careers INTEGER DEFAULT 0,
        company_summary TEXT,
        research_evidence TEXT DEFAULT '[]',
        research_sources TEXT DEFAULT '[]',
        research_retrieved_at TEXT,

        qualification_score REAL DEFAULT 0.0,
        score_breakdown TEXT,
        score_explanation TEXT DEFAULT '',
        tier TEXT,
        is_duplicate INTEGER DEFAULT 0,
        duplicate_of_id TEXT,
        duplicate_reason TEXT,
        qualification_status TEXT DEFAULT 'pending',
        rejection_reason TEXT DEFAULT '',
        lead_class TEXT DEFAULT '',
        class_reason TEXT DEFAULT '',
        expiry_date TEXT DEFAULT '',
        created_at TEXT,
        FOREIGN KEY (run_id) REFERENCES import_runs(id)
    )
    """)

    # Safe schema migration for databases created by earlier releases.
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(leads)").fetchall()}
    if "qualification_status" not in existing_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN qualification_status TEXT DEFAULT 'pending'")
    if "rejection_reason" not in existing_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN rejection_reason TEXT DEFAULT ''")
    # Evidence and score explanation fields added in v1.2.0.
    for col, definition in (
        ("research_evidence", "TEXT DEFAULT '[]'"),
        ("research_sources", "TEXT DEFAULT '[]'"),
        ("research_retrieved_at", "TEXT"),
        ("score_explanation", "TEXT DEFAULT ''"),
        # v1.5.0: Ready / Needs review / Rejected / Duplicate and the reason for it.
        ("lead_class", "TEXT DEFAULT ''"),
        ("class_reason", "TEXT DEFAULT ''"),
        # v1.6.0: parsed end / expiry date of the lead ("" when the file has none).
        ("expiry_date", "TEXT DEFAULT ''"),
    ):
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS research_cache (
        domain TEXT PRIMARY KEY,
        status TEXT,
        industry TEXT,
        tech_stack TEXT,
        has_careers INTEGER,
        summary TEXT,
        updated_at TEXT,
        evidence TEXT DEFAULT '[]',
        sources TEXT DEFAULT '[]'
    )
    """)
    cache_cols = {row[1] for row in cursor.execute("PRAGMA table_info(research_cache)").fetchall()}
    if "evidence" not in cache_cols:
        cursor.execute("ALTER TABLE research_cache ADD COLUMN evidence TEXT DEFAULT '[]'")
    if "sources" not in cache_cols:
        cursor.execute("ALTER TABLE research_cache ADD COLUMN sources TEXT DEFAULT '[]'")

    conn.commit()
    conn.close()
    logger.info(f"SQLite database schema verified at {DB_PATH}")

# Ensure database tables exist immediately on import
init_database()

# ==============================================================================
# PURE-PYTHON FILE INGESTION (CSV & XLSX - Zero External Compiler Requirements)
# ==============================================================================
class PurePythonFileParser:
    """Parses CSV and Excel XLSX files without requiring openpyxl or Rust compilers."""

    @classmethod
    def parse_csv(cls, file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        text = None
        for enc in encodings:
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            raise ValueError(f"Could not decode CSV {filename} with standard encodings.")

        # Delimiter sniffing
        lines = text.splitlines()
        if not lines:
            return []

        sample = "\n".join(lines[:20])
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ","

        reader = csv.reader(lines, delimiter=delimiter)
        raw_rows = list(reader)
        if not raw_rows:
            return []

        headers = [h.strip() for h in raw_rows[0]]
        records = []
        for row in raw_rows[1:]:
            if not any(row):
                continue
            item = {}
            for idx, h in enumerate(headers):
                item[h] = row[idx].strip() if idx < len(row) else ""
            records.append(item)

        return records

    @classmethod
    def parse_xlsx(cls, file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
        """Pure-Python XLSX parser using standard library zipfile and XML ElementTree."""
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
                # 1. Parse shared strings table if present
                shared_strings = []
                if "xl/sharedStrings.xml" in z.namelist():
                    ss_xml = z.read("xl/sharedStrings.xml")
                    root = ET.fromstring(ss_xml)
                    # Namespace handling
                    ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    for si in root.findall(".//ns:si", ns) or root.findall(".//si"):
                        t_elems = si.findall(".//ns:t", ns) or si.findall(".//t")
                        shared_strings.append("".join(t.text or "" for t in t_elems))

                # 2. Parse active sheet (typically sheet1.xml)
                sheet_xml_name = "xl/worksheets/sheet1.xml"
                if sheet_xml_name not in z.namelist():
                    # Pick first sheet found
                    candidates = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
                    if candidates:
                        sheet_xml_name = candidates[0]
                    else:
                        raise ValueError("No worksheet XML found in XLSX file.")

                sheet_xml = z.read(sheet_xml_name)
                root = ET.fromstring(sheet_xml)
                ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

                rows_data = []
                row_elements = root.findall(".//ns:row", ns) or root.findall(".//row")

                for r in row_elements:
                    cell_dict = {}
                    cells = r.findall(".//ns:c", ns) or r.findall(".//c")
                    for c in cells:
                        ref = c.attrib.get("r", "")
                        col_letters = "".join(filter(str.isalpha, ref))
                        cell_type = c.attrib.get("t", "")
                        v_elem = c.find("ns:v", ns) if ns else c.find("v")
                        val = v_elem.text if v_elem is not None else ""
                        # XLSX writers commonly store text as inlineStr rather than sharedStrings.
                        if cell_type == "inlineStr":
                            inline_nodes = c.findall(".//ns:t", ns) or c.findall(".//t")
                            val = "".join(node.text or "" for node in inline_nodes)

                        if cell_type == "s" and val.isdigit():
                            idx = int(val)
                            val = shared_strings[idx] if idx < len(shared_strings) else val
                        cell_dict[col_letters] = val.strip()

                    if cell_dict:
                        rows_data.append(cell_dict)

                if not rows_data:
                    return []

                # Determine sorted column letters from row 1 headers
                header_row = rows_data[0]
                sorted_cols = sorted(header_row.keys(), key=lambda c: (len(c), c))
                headers = [header_row[c] for c in sorted_cols]

                records = []
                for r in rows_data[1:]:
                    item = {}
                    for col_idx, col_letter in enumerate(sorted_cols):
                        h = headers[col_idx]
                        item[h] = r.get(col_letter, "")
                    if any(item.values()):
                        records.append(item)

                return records

        except Exception as e:
            logger.error(f"Error parsing XLSX {filename}: {e}")
            raise ValueError(f"Failed to parse XLSX file: {e}")

    @classmethod
    def parse_file(cls, file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
        ext = os.path.splitext(filename)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            return cls.parse_xlsx(file_bytes, filename)
        if ext == ".xls":
            raise ValueError("Legacy .xls files are not supported. Save the workbook as .xlsx and import again.")
        return cls.parse_csv(file_bytes, filename)

# ==============================================================================
# VALIDATION, DEDUPLICATION, AND SCORING (0.00 to 1.00)
# ==============================================================================
# ==============================================================================
# SECTION 4 & 5: EMAIL & PHONE VALIDATION ENGINES
# ==============================================================================
class EmailValidator:
    """
    Validates existing email addresses using Syntax (RFC 5322), Domain, and DNS/MX checks.
    Does NOT search for or invent new email addresses.
    
    Classifies strictly into the 5 requested states:
    1. 'Valid format and MX found.'
    2. 'Invalid email format.'
    3. 'Domain has no MX records.'
    4. 'DNS verification unavailable.'
    5. 'Email missing.'
    
    Important: DNS/MX verification proves the domain has configured mail exchangers,
    but does NOT prove that an individual mailbox exists or is active.
    Never claims an email is guaranteed deliverable.
    """
    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )
    _mx_cache: Dict[str, Tuple[Optional[bool], str]] = {}

    @classmethod
    def clean(cls, email: Optional[str]) -> str:
        if not email:
            return ""
        email = str(email).strip().lower()
        email = re.sub(r"^(mailto:|['\"<\[\(])", "", email)
        email = re.sub(r"['\">\]\)]$", "", email)
        for sep in [",", ";", "/", "|", " or "]:
            if sep in email:
                email = email.split(sep)[0].strip()
        return email

    @classmethod
    def check_mx_records(cls, domain: str) -> Tuple[Optional[bool], str]:
        """
        Pure-Python UDP DNS query for Type 15 (MX) to Google (8.8.8.8) and Cloudflare (1.1.1.1).
        Returns:
            (True, "MX found") if MX records exist
            (False, "No MX records") if domain explicitly has no MX
            (None, "DNS unavailable") if network/timeout/offline
        """
        if domain in cls._mx_cache:
            return cls._mx_cache[domain]

        # 1. Pure-Python UDP DNS query (MX) to public resolvers.
        outcome, ancount = cls._udp_mx_query(domain)
        if outcome == "mx":
            res = (True, f"MX found ({ancount} records)")
            cls._mx_cache[domain] = res
            return res
        if outcome in ("nomx", "nxdomain"):
            # "Does not exist / no MX" is only believable when the resolver answers correctly for a domain
            # that certainly has mail servers. A sinkholed or filtered network can answer NXDOMAIN to everything.
            if not cls._dns_trustworthy():
                return (None, "DNS verification unavailable.")
            res = (False, "Domain does not exist (NXDOMAIN)" if outcome == "nxdomain" else "Domain has no MX records.")
            cls._mx_cache[domain] = res
            return res

        # 2. Fallback: Check if host domain is at least resolvable via system resolver
        try:
            socket.gethostbyname(domain)
            # Host resolves, but direct UDP MX query was blocked/unavailable
            return (None, "DNS verification unavailable.")
        except socket.gaierror:
            # A lookup failure only means "this domain does not exist" when DNS itself works.
            # If a known-good name cannot be resolved either, we are offline or DNS is blocked,
            # so the honest answer is "unavailable", not "no MX records".
            if not cls._resolver_works():
                return (None, "DNS verification unavailable.")
            res = (False, "Domain has no MX records.")
            cls._mx_cache[domain] = res
            return res
        except Exception:
            return (None, "DNS verification unavailable.")

    @classmethod
    def _udp_mx_query(cls, domain: str):
        """Returns (outcome, answer_count); outcome is 'mx', 'nomx', 'nxdomain' or None (no usable answer)."""
        import struct, random
        for dns_ip in ("8.8.8.8", "1.1.1.1"):
            sock = None
            try:
                tx_id = random.randint(0, 65535)
                header = struct.pack(">HHHHHH", tx_id, 0x0100, 1, 0, 0, 0)
                qname = b"".join(bytes([len(p)]) + p.encode("ascii") for p in domain.split(".")) + b"\x00"
                packet = header + qname + struct.pack(">HH", 15, 1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(1.5)
                sock.sendto(packet, (dns_ip, 53))
                data, _ = sock.recvfrom(1024)
                if len(data) >= 12:
                    _, flags, _, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
                    rcode = flags & 0x000F
                    if rcode == 3:
                        return "nxdomain", 0
                    if rcode == 0:
                        return ("mx", ancount) if ancount > 0 else ("nomx", 0)
                    # SERVFAIL / REFUSED etc.: this resolver cannot answer, try the next one.
            except Exception:
                continue
            finally:
                if sock is not None:
                    try: sock.close()
                    except Exception: pass
        return None, 0

    @classmethod
    def _dns_trustworthy(cls) -> bool:
        """True when DNS correctly answers for a domain that certainly has MX records (cached 30 s)."""
        import time as _t
        cached = getattr(cls, "_dns_probe", None)
        if cached and _t.time() - cached[0] < 30:
            return cached[1]
        ok = cls._udp_mx_query("gmail.com")[0] == "mx"
        if not ok:
            ok = cls._resolver_works()
        cls._dns_probe = (_t.time(), ok)
        return ok

    @classmethod
    def _resolver_works(cls) -> bool:
        """True when the system resolver can resolve a name that certainly exists."""
        import time as _t
        cached = getattr(cls, "_resolver_probe", None)
        if cached and _t.time() - cached[0] < 30:
            return cached[1]
        try:
            socket.gethostbyname("example.com")
            ok = True
        except Exception:
            ok = False
        cls._resolver_probe = (_t.time(), ok)
        return ok

    @classmethod
    def validate(cls, raw_email: Optional[str], check_dns: bool = True) -> Tuple[bool, str, bool, bool, str]:
        """
        Classifies email strictly into:
        - Valid format and MX found.
        - Invalid email format.
        - Domain has no MX records.
        - DNS verification unavailable.
        - Email missing.
        """
        cleaned = cls.clean(raw_email)
        if not cleaned:
            return False, "Email missing.", False, False, ""

        if not cls.EMAIL_REGEX.match(cleaned):
            return False, "Invalid email format.", False, False, cleaned

        parts = cleaned.split("@")
        if len(parts) != 2:
            return False, "Invalid email format.", False, False, cleaned

        local_part, domain = parts[0], parts[1]
        domain_parts = domain.split(".")
        if len(domain_parts) < 2 or any(len(p) == 0 for p in domain_parts) or len(domain_parts[-1]) < 2:
            return False, "Invalid email format.", False, False, cleaned

        is_disp = domain in DISPOSABLE_DOMAINS

        clean_local = re.sub(r"[._-]", "", local_part.lower())

        normalized_role_prefixes = {
            re.sub(r"[._-]", "", prefix.lower())
            for prefix in ROLE_BASED_PREFIXES
        }

        is_role = clean_local in normalized_role_prefixes

        if not check_dns:
            return True, "DNS verification unavailable.", is_role, is_disp, cleaned

        mx_found, mx_detail = cls.check_mx_records(domain)
        if mx_found is True:
            # Domain has active MX records
            return True, "Valid format and MX found.", is_role, is_disp, cleaned
        elif mx_found is False:
            # Domain explicitly failed MX check
            return False, "Domain has no MX records.", is_role, is_disp, cleaned
        else:
            # DNS/Network unavailable
            return True, "DNS verification unavailable.", is_role, is_disp, cleaned


class PhoneValidator:
    """
    Validates existing phone numbers from spreadsheets.
    Does NOT discover or fabricate phone numbers.
    
    Features:
    - Checks for reliable 'phonenumbers' library; otherwise uses fully documented pure-Python fallback.
    - Country code is NOT mandatory. Assumes India (+91) for numbers without an explicit country code.
    - Accepts spaces, hyphens, parentheses, and leading plus signs.
    - Validates Indian mobile numbers (10 digits starting with 6, 7, 8, 9).
    - Normalizes numbers into clean international format (e.g. +91 98765 43210 or +1 415-555-0192).
    - Rejects clearly invalid numbers (repeating digits, sequential digits, improper length).
    - Accurately states line activity is unconfirmed (never claims an unverified number is active).
    """

    KNOWN_COUNTRY_CODES = {
        "1": "US/CA", "44": "UK", "91": "India", "49": "Germany", "33": "France",
        "61": "Australia", "81": "Japan", "86": "China", "41": "Switzerland",
        "31": "Netherlands", "34": "Spain", "39": "Italy", "65": "Singapore",
        "971": "UAE", "55": "Brazil"
    }

    # Common Indian Landline STD Codes
    INDIAN_STD_CODES = {
        "11": "Delhi", "22": "Mumbai", "33": "Kolkata", "44": "Chennai",
        "80": "Bangalore", "40": "Hyderabad", "20": "Pune", "79": "Ahmedabad"
    }

    @classmethod
    def clean(cls, phone: Optional[str]) -> str:
        if not phone:
            return ""
        phone = str(phone).strip()
        # Remove extension suffix
        phone = re.split(r"(?i)\s*(?:ext|x|#|extension)\s*", phone)[0]
        # Keep leading '+' and all digits
        has_plus = phone.startswith("+")
        digits = re.sub(r"\D", "", phone)
        if not digits:
            return ""
        return f"+{digits}" if has_plus else digits

    @classmethod
    def validate(cls, raw_phone: Optional[str]) -> Tuple[bool, str, str, str]:
        """
        Returns: (is_valid, status_msg, normalized_international_format, country_name)
        """
        # Try optional phonenumbers library if user installed it in Termux
                       # Reject known dummy and placeholder numbers before using any validator
        cleaned_digits = re.sub(r"\D", "", str(raw_phone or ""))

        national_tail = cleaned_digits
        if national_tail.startswith("0091") and len(national_tail) == 14:
            national_tail = national_tail[4:]
        elif national_tail.startswith("91") and len(national_tail) == 12:
            national_tail = national_tail[2:]
        elif national_tail.startswith("0") and len(national_tail) == 11:
            national_tail = national_tail[1:]

        if national_tail in DUMMY_PHONE_NUMBERS or national_tail == "6000000000":
            return False, "Rejected: Dummy or placeholder number", "", ""

        if len(national_tail) == 10 and len(set(national_tail)) == 1:
            return False, "Rejected: Repeated dummy digits", "", ""

        # Try optional phonenumbers library if user installed it in Termux
        try:
            import phonenumbers
            from phonenumbers import PhoneNumberFormat, PhoneNumberType
            cleaned_raw = str(raw_phone or "").strip()
            if not cleaned_raw:
                return False, "Missing Phone.", "", ""

            # Assume India ("IN") if no country code provided
            parsed = phonenumbers.parse(cleaned_raw, "IN")
            if not phonenumbers.is_valid_number(parsed):
                return False, "Invalid number for region", "", ""

            num_type = phonenumbers.number_type(parsed)
            # v1.5.1: a true landline must be labelled as such so Ready / Needs review can tell it apart.
            # Numbers the library cannot place (fixed line OR mobile) stay "Phone" and are accepted.
            if num_type == PhoneNumberType.MOBILE:
                type_label = "Mobile"
            elif num_type == PhoneNumberType.FIXED_LINE:
                type_label = "Landline"
            else:
                type_label = "Phone"
            formatted = phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
            e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
            country = "India" if parsed.country_code == 91 else cls.KNOWN_COUNTRY_CODES.get(str(parsed.country_code), "International")

            status = f"Valid {country} {type_label} Format (Line activity unconfirmed)"
            return True, status, formatted, country

        except ImportError:
            # Pure-Python carefully documented fallback engine
            return cls._validate_pure_python_fallback(raw_phone)
        except Exception:
            return cls._validate_pure_python_fallback(raw_phone)

    @classmethod
    def _validate_pure_python_fallback(cls, raw_phone: Optional[str]) -> Tuple[bool, str, str, str]:
        """
        Fully documented pure-Python fallback for Android Termux.
        Assumes India (+91) when no international prefix is provided.
        """
        if not raw_phone:
            return False, "Missing Phone.", "", ""

        raw_str = str(raw_phone).strip()
        has_plus = raw_str.startswith("+")

        # Strip spaces, hyphens, parentheses, extensions
        cleaned_digits = re.sub(r"\D", "", raw_str)
        num_len = len(cleaned_digits)

        # Reject out-of-bounds lengths (ITU-T E.164: 7 to 15 digits)
        if num_len < 7 or num_len > 15:
            return False, f"Invalid length ({num_len} digits; expected 7-15)", "", ""

        # Reject repeating dummy digits (e.g. 9999999999, 5555555555, 0000000000)
        if len(set(cleaned_digits)) <= 1:
            return False, "Rejected: Repeated dummy digits", "", ""

        # Reject sequential dummy digits (e.g. 1234567890)
        if cleaned_digits in ("1234567890", "0123456789", "1234567", "12345678"):
            return False, "Rejected: Sequential dummy digits", "", ""
        # v1.6.0: also reject known fake numbers in any format (+91 98765 43210, 09876543210 ...).
        national_tail = cleaned_digits[-10:] if num_len >= 10 else cleaned_digits
        if national_tail in DUMMY_PHONE_NUMBERS or (num_len >= 10 and len(set(national_tail)) <= 1):
            return False, "Rejected: Dummy number", "", ""

        # CASE 1: International Prefix Present (+ or leading 00)
        if has_plus:
            # Check country code
            for code, name in sorted(cls.KNOWN_COUNTRY_CODES.items(), key=lambda x: len(x[0]), reverse=True):
                if cleaned_digits.startswith(code):
                    national = cleaned_digits[len(code):]
                    if code == "91":
                        # Validate Indian national portion
                        return cls._validate_indian_national(national, True)
                    elif code == "1" and len(national) == 10:
                        # US/CA NANPA
                        if national[0] in "01" or national[3] in "01":
                            return False, f"Invalid NANPA area code/exchange (+1 {national[:3]})", "", ""
                        formatted = f"+1 {national[:3]}-{national[3:6]}-{national[6:]}"
                        return True, "Valid US/CA Format (Line activity unconfirmed)", formatted, "US/CA"
                    elif code == "44" and len(national) in (10, 11):
                        formatted = f"+44 {national[:4]} {national[4:]}"
                        return True, "Valid UK Format (Line activity unconfirmed)", formatted, "UK"
                    else:
                        formatted = f"+{code} {national}"
                        return True, f"Valid {name} Format (Line activity unconfirmed)", formatted, name

            formatted = f"+{cleaned_digits}"
            return True, "Valid International Format (Line activity unconfirmed)", formatted, "International"

        # CASE 2: No Country Code Provided -> Assume India (+91)
        # Check if number already has domestic Indian prefix: 0XXXXXXXXXX or 91XXXXXXXXXX
        if num_len == 12 and cleaned_digits.startswith("91"):
            # Strips redundant 91, validate national 10 digits
            return cls._validate_indian_national(cleaned_digits[2:], False)
        elif num_len == 11 and cleaned_digits.startswith("0"):
            # Strips trunk prefix 0, validate national 10 digits
            return cls._validate_indian_national(cleaned_digits[1:], False)
        elif num_len == 10:
            # Standard 10-digit number -> validate directly as India
            return cls._validate_indian_national(cleaned_digits, False)
        elif num_len == 11 and cleaned_digits.startswith("1"):
            # North America without plus
            national = cleaned_digits[1:]
            formatted = f"+1 {national[:3]}-{national[3:6]}-{national[6:]}"
            return True, "Valid US/CA Format (Line activity unconfirmed)", formatted, "US/CA"
        else:
            # Generic international representation
            formatted = f"+91 {cleaned_digits}"
            return False, f"Invalid Indian phone length ({num_len} digits; expected 10)", formatted, "India"

    @classmethod
    def _validate_indian_national(cls, digits: str, had_plus: bool) -> Tuple[bool, str, str, str]:
        """
        Validates 10-digit Indian national number according to Department of Telecommunications (DoT) National Numbering Plan.
        Mobile: Starts with 6, 7, 8, 9.
        Landline: Starts with valid STD code (e.g. 11, 22, 33, 44, 80).
        """
        if len(digits) != 10:
            return False, f"Invalid Indian phone length ({len(digits)} digits; expected 10)", f"+91 {digits}", "India"

        first_digit = digits[0]

        # Indian Mobile Allocation: 6, 7, 8, 9
        if first_digit in ("6", "7", "8", "9"):
            # Format as: +91 XXXXX XXXXX (Standard Indian mobile display format)
            formatted = f"+91 {digits[:5]} {digits[5:]}"
            return True, "Valid Indian Mobile Format (Line activity unconfirmed)", formatted, "India"

        # Check Landline STD codes (e.g. 11 for Delhi, 22 for Mumbai, 80 for Bangalore)
        for std, city in cls.INDIAN_STD_CODES.items():
            if digits.startswith(std):
                sub = digits[len(std):]
                formatted = f"+91 {std} {sub[:4]} {sub[4:]}"
                return True, f"Valid Indian Landline ({city}) (Line activity unconfirmed)", formatted, "India"

        # Digits starting with 0-5 without valid STD are invalid Indian numbers
        return False, f"Invalid Indian mobile prefix '{first_digit}' (Indian mobiles must start with 6, 7, 8, or 9)", f"+91 {digits}", "India"

def clean_company_name(name: str) -> str:
    if not name:
        return ""
    norm = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    norm = " ".join(norm.split())
    suffixes = [" inc", " llc", " ltd", " corp", " corporation", " gmbh", " pvt ltd", " co", " company"]
    for s in suffixes:
        if norm.endswith(s):
            norm = norm[:-len(s)].strip()
    return norm

def compute_jaccard(s1: str, s2: str) -> float:
    t1 = set(re.sub(r"[^\w\s]", "", s1.lower()).split())
    t2 = set(re.sub(r"[^\w\s]", "", s2.lower()).split())
    if not t1 or not t2:
        return 0.0
    return len(t1.intersection(t2)) / len(t1.union(t2))

def _extract_search_results(html: str, limit: int = 8) -> List[Dict[str, str]]:
    """Parse DuckDuckGo's lightweight HTML results; this is a best-effort fallback, not an official API."""
    results: List[Dict[str, str]] = []
    anchors = re.findall(r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S)
    snippets = re.findall(r'<(?:a|td|div)[^>]+class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(.*?)</(?:a|td|div)>', html, re.I | re.S)
    def clean_markup(value: str) -> str:
        value = re.sub(r'<[^>]+>', ' ', value)
        value = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), value)
        value = value.replace('&amp;', '&').replace('&quot;', '"').replace('&#x27;', "'")
        return ' '.join(value.split()).strip()
    for idx, (href, title_html) in enumerate(anchors[:limit]):
        href = href.replace('&amp;', '&')
        parsed = urllib.parse.urlparse(href)
        if 'duckduckgo.com' in (parsed.netloc or '') and parsed.path.startswith('/l/'):
            href = urllib.parse.parse_qs(parsed.query).get('uddg', [href])[0]
        if urllib.parse.urlparse(href).scheme not in ('http', 'https'):
            continue
        title = clean_markup(title_html)
        snippet = clean_markup(snippets[idx]) if idx < len(snippets) else ''
        if title:
            results.append({'title': title[:240], 'url': href[:1000], 'snippet': snippet[:700], 'kind': 'search_result'})
    return results


def _brave_search(query: str, count: int = 8) -> List[Dict[str, str]]:
    """Use the official Brave Search API when BRAVE_SEARCH_API_KEY is configured."""
    api_key = os.environ.get('BRAVE_SEARCH_API_KEY', '').strip()
    if not api_key:
        return []
    url = 'https://api.search.brave.com/res/v1/web/search?' + urllib.parse.urlencode({'q': query, 'count': min(20, count), 'country': 'IN', 'search_lang': 'en'})
    req = urllib.request.Request(url, headers={'Accept':'application/json', 'X-Subscription-Token':api_key, 'User-Agent':'LeadScoreTermux/1.4'})
    with urllib.request.urlopen(req, timeout=5) as response:
        payload = json.loads(response.read(700000).decode('utf-8', errors='replace'))
    out=[]
    for item in (payload.get('web') or {}).get('results', []):
        link=item.get('url','')
        if link.startswith(('http://','https://')):
            out.append({'title':str(item.get('title') or '')[:240], 'url':link[:1000], 'snippet':str(item.get('description') or '')[:700], 'kind':'search_result'})
    return out


def _search_web(query: str, limit: int = 8) -> Tuple[List[Dict[str, str]], str]:
    """Search through Brave API if keyed; otherwise use a best-effort public DDG HTML fallback."""
    if os.environ.get('BRAVE_SEARCH_API_KEY', '').strip():
        return _brave_search(query, limit), 'Brave Search API'
    search_url = 'https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': query, 'kl':'in-en'})
    req = urllib.request.Request(search_url, headers={'User-Agent':'Mozilla/5.0 (compatible; LeadScoreTermux/1.4; +local)'} )
    with urllib.request.urlopen(req, timeout=4) as response:
        html=response.read(350000).decode('utf-8', errors='replace')
    return _extract_search_results(html, limit), 'DuckDuckGo HTML (best-effort; unofficial, may rate-limit)'


def _plain_page_text(html: str) -> Tuple[str, str, str]:
    """Extract page title, description and visible-ish text without external packages."""
    title_match=re.search(r'<title[^>]*>(.*?)</title>', html, re.I|re.S)
    desc_match=re.search(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']', html, re.I|re.S)
    title=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',title_match.group(1))).strip() if title_match else ''
    desc=re.sub(r'\s+',' ',desc_match.group(1)).strip() if desc_match else ''
    text=re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', html)
    text=re.sub(r'(?s)<[^>]+>', ' ', text)
    text=re.sub(r'&nbsp;|&#160;', ' ', text, flags=re.I)
    text=text.replace('&amp;','&').replace('&quot;','"').replace('&#39;',"'")
    return title[:240], desc[:700], ' '.join(text.split())[:12000]


def _company_tokens(name: str) -> List[str]:
    ignored={'the','and','inc','llc','ltd','limited','company','corporation','corp','private','pvt','plc','group'}
    return [t for t in re.sub(r'[^a-z0-9 ]',' ',(name or '').lower()).split() if len(t)>2 and t not in ignored]


def research_company_online(domain_or_name: str, company_name: str = '', job_title: str = '', hr_name: str = '', hr_profile_url: str = '', force_refresh: bool = False) -> Dict[str, Any]:
    """Perform multi-angle company/job/HR research and retain evidence with source URLs.

    Search-result snippets are never treated as independently verified facts. For scoreable
    evidence, a result page is fetched and checked for company/domain relevance. No AI-generated
    claims or guessed company facts are introduced.
    """
    identity=(company_name or domain_or_name or '').strip()
    raw=(domain_or_name or '').strip()
    host=re.sub(r'^https?://','',raw,flags=re.I).split('/')[0].split(':')[0].lower()
    if not host or ' ' in host or '.' not in host: host=''
    # Versioned cache invalidates shallow v1.3 homepage-only evidence.
    base_key=host or re.sub(r'\W+','-',identity.lower()).strip('-')[:80]
    cache_key='deep14-' + base_key
    if not identity and not host:
        return {'status':'Research unavailable','industry':'Unverified','tech_stack':[],'has_careers':False,
                'summary':'No company identity or domain was supplied.','evidence':[],'sources':[], 'retrieved_at':datetime.now().astimezone().isoformat(timespec='seconds')}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            row=conn.execute('SELECT status,industry,tech_stack,has_careers,summary,evidence,sources,updated_at FROM research_cache WHERE domain=?',(cache_key,)).fetchone()
        if row and not force_refresh:
            ev=json.loads(row[5] or '[]')
            if any(x.get('kind') in ('verified_company_profile','verified_job_relevance','verified_hiring_evidence','verified_hr_association') for x in ev):
                return {'status':row[0],'industry':row[1],'tech_stack':json.loads(row[2] or '[]'),'has_careers':bool(row[3]),
                        'summary':row[4],'evidence':ev,'sources':json.loads(row[6] or '[]'),'retrieved_at':row[7] or ''}
    except Exception: pass

    now=datetime.now().astimezone().isoformat(timespec='seconds')
    tokens=_company_tokens(identity)
    job_tokens=_company_tokens(job_title)
    domain=host
    queries=[]
    if identity:
        queries.append(('company_profile', f'"{identity}" company official about products'))
        # One targeted second query covers the supplied role and (when available) HR contact.
        role_part=f' "{job_title}" jobs careers hiring' if job_title else ' careers jobs'
        hr_part=f' "{hr_name}" HR recruiter' if hr_name else ''
        queries.append(('job_relevance', f'"{identity}"{role_part}{hr_part}'))
    elif domain:
        queries.append(('company_profile', f'site:{domain} about company products'))
    evidence=[]; sources=[]; search_errors=[]; seen_urls=set(); query_provider=''
    for category, query in queries[:2]:
        try:
            hits, provider=_search_web(query, limit=3); query_provider=provider
            for hit in hits:
                u=hit.get('url','')
                if not u or u in seen_urls: continue
                seen_urls.add(u)
                hit.update({'query_category':category,'search_query':query,'retrieved_at':now,'evidence_level':'search_snippet_only','verified_for_company':False})
                evidence.append(hit); sources.append(u)
        except Exception as exc:
            search_errors.append(f'{category}: {str(exc)[:120]}')

    # Inspect a small, diverse set of result pages. A page only becomes scoreable evidence
    # after content fetch and a company/domain match. Never crawl login walls or forms.
    verified_categories=set(); profile_texts=[]; fetched_hosts=set()
    candidate_pages=sorted(evidence, key=lambda x: (x.get('query_category')!='company_profile', not bool(x.get('snippet'))))[:2]
    for hit in candidate_pages:
        u=hit['url']; parsed=urllib.parse.urlparse(u); page_host=(parsed.hostname or '').lower()
        if parsed.scheme not in ('http','https') or not page_host or page_host in fetched_hosts: continue
        if any(x in page_host for x in ('duckduckgo.com','google.com','bing.com','brave.com')): continue
        fetched_hosts.add(page_host)
        try:
            req=urllib.request.Request(u, headers={'User-Agent':'Mozilla/5.0 (compatible; LeadScoreTermux/1.4)'})
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.getcode() >= 400: continue
                final_url=response.geturl(); ctype=response.headers.get('Content-Type','')
                if ctype and not any(t in ctype.lower() for t in ('text/html','application/xhtml')): continue
                body=response.read(180000).decode('utf-8',errors='replace')
            page_title, page_desc, page_text=_plain_page_text(body)
            hay=(page_title+' '+page_desc+' '+page_text).lower()
            host_match=bool(domain and (domain==page_host or page_host.endswith('.'+domain)))
            token_hits=sum(1 for t in tokens if t in hay)
            company_match=host_match or (bool(tokens) and token_hits>=max(1, min(2, len(tokens))))
            if not company_match: continue
            cat=hit.get('query_category','company_context')
            job_hits=sum(1 for t in job_tokens if t in hay)
            job_match=bool(job_tokens and job_hits>=min(2,len(job_tokens)))
            hr_match=bool(hr_name and hr_name.lower() in hay)
            if cat in ('company_profile','company_context'):
                page_kind='verified_company_profile'
            elif cat=='job_relevance' and job_match:
                page_kind='verified_job_relevance'
            elif cat=='hr_association' and hr_match:
                page_kind='verified_hr_association'
            else:
                page_kind='verified_source_context'
            snippet=page_desc or 'Fetched source page; page text was checked for company identity. Review source for full context.'
            hit.update({'kind':page_kind,'title':page_title or hit.get('title',''),'url':final_url,'snippet':snippet[:700],
                        'evidence_level':'fetched_page_company_match','verified_for_company':True,
                        'company_token_hits':token_hits,'job_title_match':job_match,'hr_name_match':hr_match,
                        'page_host':page_host,'retrieved_at':now})
            verified_categories.add(page_kind); profile_texts.append((page_title+' '+page_desc+' '+page_text[:5000]).lower())
            sources.append(final_url)
            # Only explicit vacancy language on a fetched company-matching page AND a matching job title counts.
            vacancy_terms=('apply now','job id','job requisition','open position','current openings','view job','careers at','join our team','we are hiring')
            if cat=='job_relevance' and job_match and any(term in hay for term in vacancy_terms):
                hiring=dict(hit); hiring['kind']='verified_hiring_evidence'; hiring['title']='Hiring evidence: '+(page_title or hit.get('title','Company careers page'))
                hiring['snippet']=snippet+' Page content contained job-title match and explicit vacancy/application language; confirm the individual vacancy is current.'
                evidence.append(hiring); verified_categories.add('verified_hiring_evidence')
        except Exception as exc:
            hit['fetch_status']='Could not fetch source page: '+str(exc)[:100]

    # Inspect the supplied official website independently, but award no company-activity points
    # based on HTTP 200 alone. The page is contextual evidence only.
    website_status='Not checked'; website_url=''
    # Avoid an extra homepage fetch per lead: it duplicated work and dominated batch time.
    website_status='Not independently checked (fast research mode)'
    has_careers=any(any(x in (e.get('snippet','')+' '+e.get('title','')).lower() for x in ('careers','career opportunities','join our team','open positions','job openings')) for e in evidence)

    # Summaries are evidence inventories, not unsupported assertions about the company.
    counts={k:sum(1 for e in evidence if e.get('kind')==k) for k in ('verified_company_profile','verified_job_relevance','verified_hiring_evidence','verified_hr_association')}
    summary=(f'Research provider: {query_provider or "unavailable"}. ' if query_provider else '') + \
            f'Company-matched fetched sources: profile/context {counts["verified_company_profile"]}; job relevance {counts["verified_job_relevance"]}; explicit hiring evidence {counts["verified_hiring_evidence"]}; HR association {counts["verified_hr_association"]}. ' + \
            f'Website status: {website_status}. ' + ('Search errors: '+'; '.join(search_errors[:3]) if search_errors else 'Search completed without reported request errors.') + \
            'Search snippets alone are not treated as verified facts; open each source to confirm details.'
    status='Deep research completed' if evidence else 'Research unavailable'
    sources=list(dict.fromkeys(sources))
    result={'status':status,'industry':'Unverified','tech_stack':[],'has_careers':has_careers,'summary':summary,
            'evidence':evidence,'sources':sources,'retrieved_at':now,'research_provider':query_provider,
            'verified_counts':counts,'website_status':website_status}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO research_cache(domain,status,industry,tech_stack,has_careers,summary,updated_at,evidence,sources) VALUES (?,?,?,?,?,?,?,?,?)",(cache_key,status,'Unverified','[]',int(has_careers),summary,now,json.dumps(evidence,ensure_ascii=False),json.dumps(sources,ensure_ascii=False)))
    except Exception as exc: logger.warning('Could not cache deep research for %s: %s',cache_key,exc)
    return result


def score_lead(lead_dict: Dict[str, Any]) -> Tuple[float, Dict[str, float], str, Dict[str, str]]:
    """Conservative evidence-weighted lead priority score; never equates field completeness with quality."""
    breakdown={k:0.0 for k in ('contact_email','contact_phone','role_seniority','hr_directness','company_web_presence',
                                'public_web_evidence','company_profile_evidence','job_relevance_evidence','hiring_evidence',
                                'hr_public_association','data_completeness')}
    reasons={}
    if lead_dict.get('email_valid') and not lead_dict.get('is_disposable'):
        if lead_dict.get('is_role_based'):
            breakdown['contact_email'] = 0.0
            reasons['contact_email'] = " +0.00: generic or role-based mailbox; excluded from CRM contact scoring."
        else:
            breakdown['contact_email'] = 0.18
            reasons['contact_email'] = " +0.18: supplied personal email passed the available technical checks."
    elif lead_dict.get('email'):
        reasons['contact_email'] = (
            ' +0.00: email supplied but technical status is '
            + str(lead_dict.get('email_status') or 'not verified')
            + '. It earns no score points.'
        )
    else:
        reasons['contact_email'] = ' +0.00: no email supplied.'

    if lead_dict.get('phone_valid'):
        breakdown['contact_phone']=0.12
        reasons['contact_phone']=' +0.12: phone passed number-format validation. This does not prove the line is active.'
    elif lead_dict.get('phone'):
        reasons['contact_phone']=' +0.00: phone supplied but format validation status is '+str(lead_dict.get('phone_status') or 'not verified')+'. It earns no score points.'
    else: reasons['contact_phone']=' +0.00: no phone supplied.'

    title=(lead_dict.get('job_title') or '').lower()
    if any(w in title for w in ('chief','c-level','cto','ceo','cmo','vp','vice president','head of','founder')): breakdown['role_seniority']=0.20
    elif any(w in title for w in ('director','principal')): breakdown['role_seniority']=0.16
    elif any(w in title for w in ('lead','senior','sr','staff','architect','manager')): breakdown['role_seniority']=0.12
    elif title: breakdown['role_seniority']=0.08
    reasons['role_seniority']=f" +{breakdown['role_seniority']:.2f}: heuristic based only on supplied job title '{lead_dict.get('job_title') or 'not supplied'}'; not independently verified."

    hr=0.0
    if lead_dict.get('hr_name'): hr+=0.08
    if lead_dict.get('hr_profile_url'): hr+=0.07
    breakdown['hr_directness']=hr
    reasons['hr_directness']=f" +{hr:.2f}: imported HR name/profile fields are present; they have not been independently verified unless the separate HR association evidence below exists."

    company_status=(lead_dict.get('company_status') or '').lower()
    # Website reachability is displayed as a diagnostic only; it never adds score points.
    breakdown['company_web_presence']=0.0
    reasons['company_web_presence']=f" +0.00: website status '{lead_dict.get('company_status') or 'not checked'}' is diagnostic only. HTTP success is not proof of active operations, size, revenue, or legitimacy, so it earns no points."

    evidence=lead_dict.get('research_evidence') or []
    if isinstance(evidence,str):
        try: evidence=json.loads(evidence)
        except Exception: evidence=[]
    if not isinstance(evidence,list): evidence=[]
    verified=[e for e in evidence if isinstance(e,dict) and e.get('verified_for_company') is True and str(e.get('kind','')).startswith('verified_')]
    distinct_hosts={urllib.parse.urlparse(e.get('url','')).hostname for e in verified if e.get('url')}
    if verified:
        breakdown['public_web_evidence']=min(0.10,0.05*len(distinct_hosts))
        reasons['public_web_evidence']=f" +{breakdown['public_web_evidence']:.2f}: {len(verified)} fetched page(s) were checked for company-name/domain relevance across {len(distinct_hosts)} source host(s). Search snippets alone earn no points."
    else: reasons['public_web_evidence']=' +0.00: no fetched source page passed the company identity check. Search snippets/website HTTP status alone earn no public research points.'

    category_specs=[('company_profile_evidence','verified_company_profile',0.10,'company profile/context'),
                    ('job_relevance_evidence','verified_job_relevance',0.10,'job-title relevance'),
                    ('hiring_evidence','verified_hiring_evidence',0.10,'explicit hiring/vacancy language'),
                    ('hr_public_association','verified_hr_association',0.10,'public HR-name association')]
    for key,kind,cap,label in category_specs:
        matches=[e for e in verified if e.get('kind')==kind]
        # One source per host prevents duplicate search queries from inflating scores.
        hosts={urllib.parse.urlparse(e.get('url','')).hostname for e in matches if e.get('url')}
        pts=cap if hosts else 0.0
        breakdown[key]=pts
        if hosts:
            links=', '.join(dict.fromkeys(e.get('url','') for e in matches if e.get('url')))[:420]
            reasons[key]=f' +{pts:.2f}: {label} supported by {len(hosts)} company-matched fetched source host(s). Evidence: {links}'
        else: reasons[key]=f' +0.00: no fetched, company-matched source substantiated {label}; no points awarded.'

    completeness_fields=[f for f in ('location','job_url','source') if lead_dict.get(f)]
    breakdown['data_completeness']=min(0.10,0.04*len(completeness_fields))
    reasons['data_completeness']=f" +{breakdown['data_completeness']:.2f}: {', '.join(completeness_fields) if completeness_fields else 'no location/job URL/source'} supplied. This small completeness factor is not treated as evidence of lead quality."
    score=round(min(1.0,sum(breakdown.values())),2)
    if score>=0.75: tier='High evidence score (0.75-1.00)'
    elif score>=0.55: tier='Medium evidence score (0.55-0.74)'
    elif score>=0.35: tier='Developing evidence (0.35-0.54)'
    else: tier='Limited evidence (0.00-0.34)'
    return score,breakdown,tier,reasons


# ==============================================================================
# PIPELINE EXECUTION (Integrated with SQLite Persistence)
# ==============================================================================

def phone_dedupe_key(phone: str) -> str:
    """Comparable phone identity: '98765 43210', '09876543210' and '+91 9876543210' all map to '9876543210'."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _name_tokens(name: str) -> set:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split() if len(t) > 1}


def same_person_name(a: str, b: str) -> bool:
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta and tb and compute_jaccard(" ".join(sorted(ta)), " ".join(sorted(tb))) >= 0.85)


def conflicting_contacts(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True when both records carry an email (or phone) and they differ: different people, not a repeat."""
    ea = (a.get("normalized_email") or a.get("email") or "").strip().lower()
    eb = (b.get("normalized_email") or b.get("email") or "").strip().lower()
    pa, pb = phone_dedupe_key(a.get("phone", "")), phone_dedupe_key(b.get("phone", ""))
    return bool((ea and eb and ea != eb) or (pa and pb and pa != pb))


def classify_lead(item: Dict[str, Any]) -> Tuple[str, str]:
    """Classify leads. Ready requires a verified personal email.
    Phone-only and generic-mailbox leads remain available for follow-up.
    """
    email = (item.get("email") or "").strip()
    phone = (item.get("phone") or "").strip()

    if not email and not phone:
        return "Rejected", "Both email and phone are missing"

    email_ok = (
        bool(email)
        and bool(item.get("email_valid"))
        and not item.get("is_disposable")
    )
    phone_ok = bool(phone) and bool(item.get("phone_valid"))

    if not email_ok and not phone_ok:
        if not email:
            e_part = "No email"
        elif item.get("is_disposable"):
            e_part = "Email is a disposable address"
        else:
            e_part = "Email not usable (" + str(
                item.get("email_status") or "invalid"
            ).rstrip(".") + ")"

        p_part = (
            "no phone" if not phone
            else "phone not usable (" + str(
                item.get("phone_status") or "invalid"
            ).rstrip(".") + ")"
        )
        return "Rejected", f"{e_part}; {p_part}"

    email_status = str(item.get("email_status") or "")
    phone_status = str(item.get("phone_status") or "").lower()
    email_good = email_ok and not item.get("is_role_based") and "MX found" in email_status
    phone_good = phone_ok and "landline" not in phone_status
    notes = []
    if not (email_good or phone_good):
        if email_ok and item.get("is_role_based"):
            notes.append("Only a role-based email (such as info@ or hr@)")
        elif email_ok:
            notes.append("Email domain could not be verified (DNS unavailable)")
        if phone_ok and "landline" in phone_status:
            notes.append("Only a landline phone")
    missing = []
    if not (item.get("company") or "").strip():
        missing.append("company")
    if not ((item.get("hr_name") or "").strip() or (item.get("job_title") or "").strip()):
        missing.append("HR name or job title")
    if missing:
        notes.append("Missing details: " + ", ".join(missing))
    if notes:
        return "Needs review", "; ".join(notes)
    return "Ready", "Valid contact and basic details present"


# ------------------------------------------------------------------------------
# v1.6.0: end / expiry date of a lead
# ------------------------------------------------------------------------------
_EXPIRY_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
                        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y", "%m/%d/%Y")
_EXPIRY_TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I:%M:%S %p")


def _now() -> datetime:
    """Current time (a function so tests can fix 'today')."""
    return datetime.now()


def parse_expiry(value: Any) -> Optional[Tuple[datetime, bool]]:
    """Parse an expiry / end date. Returns (datetime, has_time) or None when it cannot be understood.

    Day-first is assumed for 05/11/2026 (India); a value such as 11/15/2026 falls back to month-first.
    Excel serial numbers (46000) and ISO timestamps are understood too.
    """
    s = str(value or "").strip()
    if not s:
        return None
    s = re.sub(r"(?i)\b(\d{1,2})(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"(?i)\bsept\b", "Sep", s)
    s = re.sub(r"\s+", " ", s.replace(",", " ")).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        serial = float(s)
        if 20000 <= serial <= 80000:
            return datetime(1899, 12, 30) + timedelta(days=serial), serial != int(serial)
    s = re.sub(r"(?i)\s*(z|utc|gmt|ist)$", "", s)
    s = re.sub(r"(?<=\d{2}:\d{2}:\d{2})\.\d+", "", s)
    if re.match(r"\d{4}-\d{2}-\d{2}T", s):
        s = s.replace("T", " ", 1)
    for fmt in _EXPIRY_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt), False
        except ValueError:
            pass
    for fd in _EXPIRY_DATE_FORMATS:
        for ft in _EXPIRY_TIME_FORMATS:
            try:
                return datetime.strptime(s, fd + " " + ft), True
            except ValueError:
                pass
    return None


def lead_is_expired(expiry: datetime, has_time: bool, now: Optional[datetime] = None) -> bool:
    now = now or _now()
    if has_time:
        return expiry <= now
    if EXPIRY_INCLUSIVE_TODAY:
        return expiry.date() <= now.date()
    return expiry.date() < now.date()


# ------------------------------------------------------------------------------
# v1.6.0: choose leads by contact type (captain's five results)
# ------------------------------------------------------------------------------
SELECT_MODES = ("any", "email", "mobile", "both")
SELECT_LABELS = {"any": "Valid personal email (CRM)", "email": "Valid email", "mobile": "Valid mobile number",
                 "both": "Valid email and valid mobile"}

def selection_flags(item: Dict[str, Any]) -> Tuple[bool, bool]:
    """Only valid personal emails qualify for CRM selection."""
    email_ok = (
        bool(item.get("email_valid"))
        and not item.get("is_disposable")
        and not item.get("is_role_based")
        and bool((item.get("email") or "").strip())
    )

    mobile_ok = (
        bool(item.get("phone_valid"))
        and "landline" not in str(item.get("phone_status") or "").lower()
    )

    return email_ok, mobile_ok


def _email_phrase(item: Dict[str, Any]) -> str:
    shown = item.get("normalized_email") or item.get("email") or ""
    status = str(item.get("email_status") or "")
    check = "domain verified, MX found" if "MX found" in status else "format valid, domain not verified"
    role = ", role-based address" if item.get("is_role_based") else ""
    return f"valid email {shown} ({check}{role})"


def _no_email_phrase(item: Dict[str, Any]) -> str:
    if not (item.get("email") or "").strip():
        return "no email"
    if item.get("is_disposable"):
        return "disposable email address"
    return "email not valid (" + str(item.get("email_status") or "invalid").rstrip(".") + ")"


def _no_mobile_phrase(item: Dict[str, Any]) -> str:
    if not (item.get("phone") or "").strip():
        return "no phone number"
    if item.get("phone_valid"):
        return "only a landline number"
    return "phone not valid (" + str(item.get("phone_status") or "invalid").rstrip(".") + ")"



def selection_result(item: Dict[str, Any], mode: str = "any") -> Tuple[bool, str]:
    """Return whether a lead is selected for the requested mode."""
    mode = mode if mode in SELECT_MODES else "any"
    label = SELECT_LABELS[mode]
    cls = item.get("lead_class")

    if cls == "Expired":
        return False, f"Not selected: lead expired ({item.get('expiry_date') or 'end date passed'})"

    if cls == "Duplicate" or item.get("is_duplicate"):
        return False, "Not selected: duplicate lead"

    if item.get("qualification_status") != "qualified":
        return False, "Not selected: " + str(
            item.get("class_reason") or item.get("rejection_reason") or "no usable contact"
        )

    email_ok, mobile_ok = selection_flags(item)
    mobile_text = f"valid mobile {item.get('phone_e164') or item.get('phone')}"

    if mode == "any":
        ok = email_ok or mobile_ok
        have = [x for x in ((_email_phrase(item) if email_ok else ""), (mobile_text if mobile_ok else "")) if x]
        missing = [x for x in ((_no_email_phrase(item) if not email_ok else ""), (_no_mobile_phrase(item) if not mobile_ok else "")) if x]

    elif mode == "email":
        ok = email_ok
        have = [_email_phrase(item)] if email_ok else []
        missing = [] if email_ok else [_no_email_phrase(item)]

    elif mode == "mobile":
        # Keep phone-only leads available for follow-up.
        ok = mobile_ok
        have = [mobile_text] if mobile_ok else []
        missing = [] if mobile_ok else [_no_mobile_phrase(item)]

    else:
        ok = email_ok and mobile_ok
        have = [
            x for x in (
                _email_phrase(item) if email_ok else "",
                mobile_text if mobile_ok else ""
            ) if x
        ]
        missing = [
            x for x in (
                _no_email_phrase(item) if not email_ok else "",
                _no_mobile_phrase(item) if not mobile_ok else ""
            ) if x
        ]

    if ok:
        extra = ("; also: " + "; ".join(missing)) if (missing and mode == "any") else ""
        return True, f"Selected ({label}): " + " and ".join(have) + extra

    return False, f"Not selected ({label}): " + "; ".join(missing)


def selection_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    return {m: sum(1 for i in items if selection_result(i, m)[0]) for m in SELECT_MODES}


def apply_contact_checks(item: Dict[str, Any]) -> None:
    """Validate email/phone and classify the lead (also re-run when a duplicate fills a missing field)."""
    item["has_contact"] = bool((item.get("email") or "").strip() or (item.get("phone") or "").strip())
    e_valid, e_stat, is_role, is_disp, norm_email = EmailValidator.validate(item["email"])
    item.update(email_valid=int(e_valid), email_status=e_stat, is_role_based=int(is_role),
                is_disposable=int(is_disp), normalized_email=norm_email)
    p_valid, p_stat, e164, country = PhoneValidator.validate(item["phone"])
    item.update(phone_valid=int(p_valid), phone_status=p_stat, phone_e164=e164, phone_country=country)
    cls, reason = classify_lead(item)
    item["lead_class"], item["class_reason"] = cls, reason
    item["qualification_status"] = "rejected" if cls == "Rejected" else "qualified"
    item["rejection_reason"] = reason if cls == "Rejected" else ""
    # v1.6.0: a lead whose end / expiry date has passed is removed (class Expired, never selected).
    item["expiry_date"] = ""
    raw_expiry = str(item.get("expiry") or "").strip()
    if raw_expiry:
        parsed = parse_expiry(raw_expiry)
        if parsed is None:
            item["class_reason"] = (item["class_reason"] + "; " if item["class_reason"] else "") + f"Expiry date not understood: {raw_expiry}"
        else:
            when, has_time = parsed
            item["expiry_date"] = when.strftime("%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d")
            if lead_is_expired(when, has_time):
                item["lead_class"] = "Expired"
                item["class_reason"] = f"Expired on {item['expiry_date']} (end date has passed)"
                item["qualification_status"] = "rejected"
                item["rejection_reason"] = item["class_reason"]


def process_leads_dataset(raw_records: List[Dict[str, str]], filename: str, min_score: float = 0.0, enable_research: bool = True) -> Dict[str, Any]:
    """Import, classify, deduplicate, research and score leads.

    v1.5.0 qualification: a record qualifies only when it has at least one USABLE contact
    (a syntactically valid, non-disposable email, or a valid phone). Records are classed
    Ready / Needs review / Rejected with a reason; a low score never changes the class.
    Duplicates (same email, same phone in any format, or the same HR person / same posting
    at the same company with no conflicting contact details) are separated and not scored.
    """
    logger.info("Processing %s records from %s", len(raw_records), filename)
    header_mapping = {}
    if raw_records:
        for header in raw_records[0].keys():
            mapped = map_column_name(header)
            if mapped:
                header_mapping[header] = mapped

    standardized = []
    for idx, raw in enumerate(raw_records, start=1):
        item = {"raw_id": str(idx), "job_title": "", "company": "", "location": "", "job_url": "",
                "posted": "", "company_website": "", "company_domain": "", "company_linkedin": "",
                "source": "", "hr_name": "", "hr_title": "", "hr_profile_url": "", "email": "", "phone": "", "expiry": ""}
        for orig_key, val in raw.items():
            canonical = map_column_name(orig_key)
            if canonical and val is not None and str(val).strip():
                item[canonical] = str(val).strip()
        apply_contact_checks(item)
        standardized.append(item)

    # Duplicate classification is separate from qualification/rejection.
    unique_items, duplicates = [], []
    seen_emails, seen_phones, seen_comp_jobs = {}, {}, []
    for item in standardized:
        if item.get("lead_class") == "Expired":
            # An expired lead is kept for the audit list but must not hide a later live lead as its "duplicate".
            item["is_duplicate"], item["duplicate_of_id"], item["duplicate_reason"] = 0, "", ""
            unique_items.append(item)
            continue
        matched = None
        reason = ""
        # Use normalized supplied contact values even when their validation flags fail;
        # exact duplicate data should still be auditable.
        duplicate_email = (item.get("normalized_email") or EmailValidator.clean(item.get("email"))).lower()
        duplicate_phone = phone_dedupe_key(item.get("phone", ""))
        # Records with no contact at all are rejected, not "duplicates" of something else.
        has_any_contact = bool(duplicate_email or duplicate_phone)
        if duplicate_email and duplicate_email in seen_emails:
            matched = seen_emails[duplicate_email]
            reason = f"Duplicate email matches Lead #{matched['raw_id']}"
        if not matched and duplicate_phone and duplicate_phone in seen_phones:
            matched = seen_phones[duplicate_phone]
            reason = f"Duplicate phone matches Lead #{matched['raw_id']}"
        if not matched and has_any_contact and item.get("company"):
            c_clean, t_norm = clean_company_name(item["company"]), (item.get("job_title") or "").lower()
            for past_c, past_t, past in seen_comp_jobs:
                if compute_jaccard(c_clean, past_c) < 0.85 or conflicting_contacts(item, past):
                    continue  # another company, or a different contact person: keep both leads
                if t_norm and past_t and compute_jaccard(t_norm, past_t) >= 0.70:
                    matched, reason = past, f"Duplicate company/job matches Lead #{past['raw_id']} (same posting, no different contact)"
                    break
                if same_person_name(item.get("hr_name", ""), past.get("hr_name", "")):
                    matched, reason = past, f"Same HR person at the same company as Lead #{past['raw_id']}"
                    break
        if matched:
            item["is_duplicate"] = 1
            item["duplicate_of_id"] = matched["raw_id"]
            item["duplicate_reason"] = reason
            item["qualification_status"] = "duplicate"
            item["lead_class"], item["class_reason"] = "Duplicate", reason
            duplicates.append(item)
            # Fill gaps on canonical record without overwriting original non-empty data.
            filled_contact = False
            for field in ("phone", "email", "company_website", "hr_name", "hr_profile_url", "company_linkedin"):
                if not matched.get(field) and item.get(field):
                    matched[field] = item[field]
                    filled_contact = filled_contact or field in ("phone", "email")
            if filled_contact:
                apply_contact_checks(matched)  # re-validate and re-classify with the merged contact
        else:
            item["is_duplicate"] = 0
            item["duplicate_of_id"] = ""
            item["duplicate_reason"] = ""
            unique_items.append(item)
            if duplicate_email: seen_emails[duplicate_email] = item
            if duplicate_phone: seen_phones[duplicate_phone] = item
            if item.get("company") and has_any_contact:
                seen_comp_jobs.append((clean_company_name(item["company"]), (item.get("job_title") or "").lower(), item))

    # Research only eligible, canonical leads. Rejected records remain untouched.
    for item in unique_items:
        if item["qualification_status"] != "qualified":
            item.update(company_researched=0, company_status="Not researched: " + ("lead expired" if item.get("lead_class") == "Expired" else "no usable contact" if item.get("qualification_status") == "rejected" else "not eligible"),
                        company_industry="Unverified", company_tech_stack="[]", company_has_careers=0, company_summary="",
                        research_evidence="[]", research_sources="[]", research_retrieved_at="")
            continue
        if enable_research:
            dom = item.get("company_domain") or item.get("company_website") or item.get("company")
            try:
                res = research_company_online(dom, item.get("company", ""), item.get("job_title", ""), item.get("hr_name", ""), item.get("hr_profile_url", ""))
            except Exception as exc:
                logger.warning("Research failed for %s: %s", item.get("company"), exc)
                res = {"status": "Research unavailable", "industry": "Unverified", "tech_stack": [], "has_careers": False, "summary": str(exc), "evidence": [], "sources": [], "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds")}
            item.update(company_researched=int(res.get("status") not in ("Research unavailable", "Not Probed")),
                        company_status=res.get("status", "Research unavailable"), company_industry=res.get("industry", "Unspecified"),
                        company_tech_stack=json.dumps(res.get("tech_stack", [])), company_has_careers=int(bool(res.get("has_careers"))),
                        company_summary=res.get("summary", ""),
                        research_evidence=json.dumps(res.get("evidence", []), ensure_ascii=False),
                        research_sources=json.dumps(res.get("sources", []), ensure_ascii=False),
                        research_retrieved_at=res.get("retrieved_at", ""))
        else:
            item.update(company_researched=0, company_status="Not Probed", company_industry="Unspecified",
                        company_tech_stack="[]", company_has_careers=0, company_summary="",
                        research_evidence="[]", research_sources="[]", research_retrieved_at="")

    tier_counts = {}
    qualified_leads, rejected_leads = [], []
    scores_for_qualified = []
    for item in unique_items:
        if item["qualification_status"] == "qualified":
            sc, breakdown, tier, factor_reasons = score_lead(item)
            item["qualification_score"] = sc
            item["score_breakdown"] = json.dumps(breakdown, ensure_ascii=False)
            item["score_explanation"] = json.dumps(factor_reasons, ensure_ascii=False)
            item["tier"] = tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            qualified_leads.append(item)
            scores_for_qualified.append(sc)
        else:
            item["qualification_score"] = 0.0
            item["score_breakdown"] = json.dumps({})
            item["score_explanation"] = json.dumps({"qualification": "Rejected: " + str(item.get("class_reason") or "no usable contact")})
            item["tier"] = "Expired" if item.get("lead_class") == "Expired" else "Rejected: No usable contact"
            rejected_leads.append(item)

    avg_score = round(sum(scores_for_qualified) / len(scores_for_qualified), 2) if scores_for_qualified else 0.0
    ready_count = sum(1 for x in qualified_leads if x.get("lead_class") == "Ready")
    review_count = sum(1 for x in qualified_leads if x.get("lead_class") == "Needs review")
    expired_count = sum(1 for x in rejected_leads if x.get("lead_class") == "Expired")
    select_counts = selection_counts(qualified_leads)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO import_runs (filename,total_records,valid_leads,duplicates_removed,average_score,imported_at) VALUES (?,?,?,?,?,?)",
                       (filename, len(raw_records), len(qualified_leads), len(duplicates), avg_score, datetime.now().isoformat()))
        run_id = cursor.lastrowid
        for item in standardized:
            cursor.execute("""INSERT INTO leads (
                run_id,raw_id,job_title,company,location,job_url,posted,company_website,company_domain,company_linkedin,source,
                hr_name,hr_title,hr_profile_url,email,phone,email_valid,email_status,is_role_based,is_disposable,normalized_email,
                phone_valid,phone_status,phone_e164,phone_country,company_researched,company_status,company_industry,company_tech_stack,
                company_has_careers,company_summary,research_evidence,research_sources,research_retrieved_at,
                qualification_score,score_breakdown,score_explanation,tier,is_duplicate,duplicate_of_id,duplicate_reason,
                qualification_status,rejection_reason,lead_class,class_reason,expiry_date,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                run_id,item.get("raw_id"),item.get("job_title"),item.get("company"),item.get("location"),item.get("job_url"),item.get("posted"),
                item.get("company_website"),item.get("company_domain"),item.get("company_linkedin"),item.get("source"),item.get("hr_name"),
                item.get("hr_title"),item.get("hr_profile_url"),item.get("email"),item.get("phone"),item.get("email_valid",0),item.get("email_status"),
                item.get("is_role_based",0),item.get("is_disposable",0),item.get("normalized_email"),item.get("phone_valid",0),item.get("phone_status"),
                item.get("phone_e164"),item.get("phone_country"),item.get("company_researched",0),item.get("company_status"),item.get("company_industry"),
                item.get("company_tech_stack"),item.get("company_has_careers",0),item.get("company_summary"),
                item.get("research_evidence","[]"),item.get("research_sources","[]"),item.get("research_retrieved_at"),
                item.get("qualification_score",0.0),item.get("score_breakdown"),item.get("score_explanation",""),
                item.get("tier"),item.get("is_duplicate",0),item.get("duplicate_of_id"),item.get("duplicate_reason"),
                item.get("qualification_status"),item.get("rejection_reason"),item.get("lead_class"),item.get("class_reason"),item.get("expiry_date") or "",datetime.now().isoformat()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    qualified_leads.sort(key=lambda x: x["qualification_score"], reverse=True)
    return {"run_id":run_id,"filename":filename,"total_records":len(raw_records),"qualified_count":len(qualified_leads),
            "rejected_count":len(rejected_leads),"duplicates_count":len(duplicates),"average_score":avg_score,
            "ready_count":ready_count,"review_count":review_count,"expired_count":expired_count,"select_counts":select_counts,
            "tier_counts":tier_counts,"qualified_leads":qualified_leads,"rejected_leads":rejected_leads,
            "duplicates":duplicates,"mapped_columns":header_mapping}

_EVALUATE_LOCK = threading.Lock()


def evaluate_leads(records: List[Dict[str, Any]], mode: str = "any", persist: bool = True,
                   filename: str = "api-ingest") -> Dict[str, Any]:
    """Run leads through the full intelligent pipeline (validate, dedupe, expiry, score, select).

    `records` use the same headers as an uploaded file (HR Email, Mobile NO:, Company, Job Title,
    Expiry Date ...). Returns one verdict per input record, in input order:
    selected, selection_reason, score (0-1), lead_class, class_reason, tier, email/phone status.
    persist=True also records the run in the dashboard database; persist=False uses a throw-away
    database so a library user leaves no trace.
    """
    global DB_PATH
    mode = mode if mode in SELECT_MODES else "any"
    records = [r for r in (records or []) if isinstance(r, dict)]
    if not records:
        return {"mode": mode, "total": 0, "selected_count": 0, "results": [], "counts": {m: 0 for m in SELECT_MODES}}
    with _EVALUATE_LOCK:
        original_path, temp_path = DB_PATH, None
        try:
            if not persist:
                fd, temp_path = tempfile.mkstemp(prefix="leadscore-", suffix=".db")
                os.close(fd)
                DB_PATH = temp_path
                init_database()
            result = process_leads_dataset(records, filename, 0.0, False)
        finally:
            DB_PATH = original_path
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    items = result["qualified_leads"] + result["rejected_leads"] + result["duplicates"]
    verdicts: List[Dict[str, Any]] = []
    for item in sorted(items, key=lambda x: int(x.get("raw_id") or 0)):
        selected, reason = selection_result(item, mode)
        verdicts.append({
            "index": int(item.get("raw_id") or 0) - 1,
            "selected": bool(selected),
            "selection_reason": reason,
            "score": float(item.get("qualification_score") or 0.0),
            "lead_class": item.get("lead_class") or "",
            "class_reason": item.get("class_reason") or "",
            "tier": item.get("tier") or "",
            "email_status": item.get("email_status") or "",
            "phone_status": item.get("phone_status") or "",
            "email": item.get("normalized_email") or item.get("email") or "",
            "phone": item.get("phone_e164") or item.get("phone") or "",
            "expiry_date": item.get("expiry_date") or "",
            "is_duplicate": bool(item.get("is_duplicate")),
        })
    return {"mode": mode, "label": SELECT_LABELS[mode], "total": len(records),
            "selected_count": sum(1 for v in verdicts if v["selected"]),
            "counts": result["select_counts"], "run_id": result["run_id"] if persist else None,
            "results": verdicts}


# ==============================================================================
# EMBEDDED LIGHTWEIGHT WEB INTERFACE (HTML / CSS / JS)
# ==============================================================================
EMBEDDED_HTML_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LeadScore Termux v1.7.0</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --border: #1f2937;
      --accent: #10b981;
      --accent-hover: #059669;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding-bottom: 60px;
    }
    header {
      background: #0f172a;
      border-bottom: 1px solid var(--border);
      padding: 14px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand { font-size: 16px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
    .brand-badge { background: #064e3b; color: #34d399; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); }
    .nav-links { display: flex; gap: 12px; }
    .nav-btn { background: none; border: none; color: var(--text-muted); font-size: 13px; font-weight: 500; cursor: pointer; padding: 6px 12px; border-radius: 6px; }
    .nav-btn.active { background: #1e293b; color: var(--accent); }
    .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 20px; }
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .stat-card { background: #131c2e; border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .stat-val { font-size: 26px; font-weight: 800; font-family: var(--font-mono); color: #fff; margin-top: 4px; }
    .btn { background: var(--accent); color: #000; font-weight: 600; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; transition: background 0.15s; }
    .btn:hover { background: var(--accent-hover); }
    .btn-secondary { background: #1f2937; color: #e5e7eb; border: 1px solid #374151; }
    .btn-secondary:hover { background: #374151; }
    .dropzone { border: 2px dashed #374151; border-radius: 8px; padding: 32px; text-align: center; cursor: pointer; background: #0c1322; }
    .dropzone:hover { border-color: var(--accent); }
    table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
    th { background: #0b1120; color: #94a3b8; padding: 10px 12px; font-weight: 600; border-bottom: 1px solid var(--border); }
    td { padding: 10px 12px; border-bottom: 1px solid #1e293b; color: #e2e8f0; }
    tr:hover { background: #172033; }
    .score-badge { display: inline-block; font-family: var(--font-mono); font-weight: 700; padding: 2px 6px; border-radius: 4px; }
    .score-high { background: #064e3b; color: #34d399; }
    .score-med { background: #0c4a6e; color: #38bdf8; }
    .score-low { background: #451a03; color: #fbbf24; }
    .score-bad { background: #4c0519; color: #f43f5e; }
    .mapped-tag { background: #1e293b; border: 1px solid #334155; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; margin-bottom: 4px; display: inline-block; font-family: var(--font-mono); }
    .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 16px; }
    .modal-content { background: var(--card); border: 1px solid var(--border); border-radius: 8px; max-width: 800px; width: 100%; max-height: 90vh; overflow-y: auto; padding: 24px; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>Termux Lead Intelligence</span>
      <span class="brand-badge">Android Local</span>
    </div>
    <div class="nav-links">
      <button class="nav-btn active" onclick="switchTab('import')">Import & Preview</button>
      <button class="nav-btn" onclick="switchTab('leads')">Qualified Leads</button>
      <button class="nav-btn" onclick="switchTab('selected')">Selected Leads</button>
      <button class="nav-btn" onclick="switchTab('rejected')">Rejected Leads</button>
      <button class="nav-btn" onclick="switchTab('duplicates')">Duplicates Log</button>
      <button class="nav-btn" onclick="switchTab('logs')">Activity Logs</button>
    </div>
  </header>

  <div class="container">
    <!-- View 1: Import & Preview -->
    <div id="tab-import" class="tab-view">
      <div class="card">
        <h2 style="font-size: 16px; font-weight: 700; margin-bottom: 8px;">Import Scraped Job Postings (CSV / XLSX)</h2>
        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
          Automatically recognizes column variations including exact headers: <code>HR Email</code>, <code>Mobile NO:</code>, <code>Job Title</code>, <code>Company</code>, <code>Company LinkedIn</code>, <code>HR Profile URL</code>.
        </p>

        <div class="dropzone" id="dropzone" onclick="document.getElementById('file-input').click()">
          <input type="file" id="file-input" accept=".csv,.xlsx,.xlsm" style="display:none;" >
          <div style="font-size: 14px; font-weight: 600; color: #e5e7eb;">Tap to browse or drop CSV / Excel file here</div>
          <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">Supports files directly from /sdcard/Download/</div>
        </div>

      </div>

      <!-- Preview Section before Processing -->
      <div id="preview-section" class="card hidden">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <div>
            <h3 style="font-size: 15px; font-weight: 700;">Import Preview & Column Mapping</h3>
            <div id="preview-count" style="font-size: 12px; color: var(--accent); font-family: var(--font-mono); margin-top: 2px;"></div>
          </div>
          <button class="btn" id="btn-run-pipeline" onclick="executePipeline()">Run Lead Qualification & Scoring</button>
        </div>

        <div style="margin-bottom: 16px;">
          <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 6px;">Automatically Mapped Headers:</div>
          <div id="mapped-badges"></div>
        </div>

        <div style="overflow-x: auto;">
          <table id="preview-table">
            <thead id="preview-thead"></thead>
            <tbody id="preview-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- View 2: Qualified Leads Grid -->
    <div id="tab-leads" class="tab-view hidden">
      <div class="stat-grid" id="stats-strip">
        <div class="stat-card">
          <div style="font-size: 12px; color: #9ca3af;">Total Ingested</div>
          <div class="stat-val" id="stat-total">0</div>
        </div>
        <div class="stat-card">
          <div style="font-size: 12px; color: #34d399;">Qualified Leads</div>
          <div class="stat-val" id="stat-qualified" style="color: #34d399;">0</div>
        </div>
        <div class="stat-card">
          <div style="font-size: 12px; color: #f43f5e;">Expired (removed)</div>
          <div class="stat-val" id="stat-expired" style="color: #f43f5e;">0</div>
        </div>
        <div class="stat-card">
          <div style="font-size: 12px; color: #f59e0b;">Duplicates Purged</div>
          <div class="stat-val" id="stat-dups" style="color: #f59e0b;">0</div>
        </div>
        <div class="stat-card">
          <div style="font-size: 12px; color: #38bdf8;">Average Score</div>
          <div class="stat-val" id="stat-avg" style="color: #38bdf8;">0.00</div>
        </div>
      </div>

      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
          <h2 style="font-size: 16px; font-weight: 700;">Qualified Lead Intelligence Matrix (Score 0.00 - 1.00)</h2>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary" onclick="exportData('csv','ready')">Ready CSV</button>
            <button class="btn btn-secondary" onclick="exportData('xlsx','ready')">Ready XLSX</button>
            <button class="btn btn-secondary" onclick="exportData('csv','qualified')">Qualified CSV</button>
            <button class="btn btn-secondary" onclick="exportData('xlsx','qualified')">Qualified XLSX</button>
            <button class="btn btn-secondary" onclick="exportData('json','qualified')">Qualified JSON</button>
            <button class="btn btn-primary" id="deep-research-btn" onclick="rerunDeepResearch()">Research all qualified leads</button>
          </div>
        </div>

        <div style="overflow-x: auto;">
          <table>
            <thead>
              <tr>
                <th>Score</th>
                <th>Company</th>
                <th>Job Title</th>
                <th>HR Name / Title</th>
                <th>HR Email (Validated)</th>
                <th>Mobile NO (E.164)</th>
                <th>Company Research</th><th>Score Explanation</th>
              </tr>
            </thead>
            <tbody id="leads-tbody">
              <tr><td colspan="8" style="text-align:center; padding: 20px; color: #64748b;">No leads qualified yet. Import a CSV or Excel file to begin.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- View: Selected Leads (choose by contact type) -->
    <div id="tab-selected" class="tab-view hidden">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <h2 style="font-size:16px;font-weight:700;">Selected Leads &mdash; choose by contact type</h2>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <select id="sel-mode" onchange="loadSelected()" style="background:#0b1120;color:#e5e7eb;border:1px solid #374151;border-radius:6px;padding:8px;font-size:13px;">
              <option value="any">Valid mobile or email</option>
              <option value="email">Valid email</option>
              <option value="mobile">Valid mobile number</option>
              <option value="both">Valid email and mobile</option>
            </select>
            <button class="btn btn-secondary" onclick="exportData('csv','selected')">Selected CSV</button>
            <button class="btn btn-secondary" onclick="exportData('xlsx','selected')">Selected XLSX</button>
          </div>
        </div>
        <div id="sel-summary" style="font-size:12px;color:#9ca3af;margin-bottom:10px;">Import a file to see selected leads.</div>
        <div style="overflow-x:auto;"><table><thead><tr><th>Score</th><th>Company</th><th>HR Name</th><th>Email</th><th>Mobile</th><th>Why selected</th></tr></thead>
        <tbody id="sel-tbody"><tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b;">No leads selected yet.</td></tr></tbody></table></div>
      </div>
    </div>

    <!-- View 3: Rejected Leads -->
    <div id="tab-rejected" class="tab-view hidden">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <h2 style="font-size:16px;font-weight:700;">Rejected Leads — no usable contact, or expired</h2>
          <button class="btn btn-secondary" onclick="exportData('csv','rejected')">Rejected CSV</button>
          <button class="btn btn-secondary" onclick="exportData('xlsx','rejected')">Rejected XLSX</button>
          <button class="btn btn-secondary" onclick="exportData('csv','expired')">Expired CSV</button>
        </div>
        <div style="overflow-x:auto;"><table><thead><tr><th>Company</th><th>Job Title</th><th>HR Email</th><th>Phone</th><th>Reason</th></tr></thead>
        <tbody id="rejected-tbody"><tr><td colspan="5">No rejected records.</td></tr></tbody></table></div>
      </div>
    </div>

    <!-- View 4: Duplicates Audit Log -->
    <div id="tab-duplicates" class="tab-view hidden">
      <div class="card">
        <h2 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Removed Duplicates & Discarded Records</h2>
        <div style="overflow-x: auto;">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Job Title</th>
                <th>HR Email</th>
                <th>Mobile NO</th>
                <th>Deduplication Target & Reason</th>
              </tr>
            </thead>
            <tbody id="dups-tbody">
              <tr><td colspan="5" style="text-align:center; padding: 20px; color: #64748b;">No duplicates removed.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- View 4: Logs View -->
    <div id="tab-logs" class="tab-view hidden">
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h2 style="font-size: 16px; font-weight: 700;">Termux SQLite & Pipeline Activity Log</h2>
          <button class="btn btn-secondary" onclick="loadLogs()">Refresh Log</button>
        </div>
        <pre id="log-content" style="background: #0b1120; border: 1px solid var(--border); padding: 14px; border-radius: 6px; font-family: var(--font-mono); font-size: 11px; color: #94a3b8; max-height: 480px; overflow-y: auto; white-space: pre-wrap;"></pre>
      </div>
    </div>
  </div>


  <div id="score-modal" class="modal hidden" role="dialog" aria-modal="true" aria-labelledby="score-modal-title">
    <div class="modal-content">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;">
        <h2 id="score-modal-title" style="font-size:18px;">Why this lead received its score</h2>
        <button class="btn btn-secondary" onclick="closeScoreDetails()">Close</button>
      </div>
      <div id="score-modal-body"></div>
    </div>
  </div>

  <script>
    let currentParsedData = null;
    let currentFilename = '';
    let latestQualifiedLeads = [];

    function switchTab(tabId, triggerEl = null) {
      // This function is called both by navigation buttons and programmatically
      // after a successful import. Never depend on the browser's implicit
      // global `event`, because it is undefined for programmatic calls.
      document.querySelectorAll('.tab-view').forEach(el => el.classList.add('hidden'));
      document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
      const targetView = document.getElementById('tab-' + tabId);
      if (targetView) targetView.classList.remove('hidden');
      let activeButton = triggerEl;
      if (!activeButton) {
        activeButton = Array.from(document.querySelectorAll('.nav-btn')).find(btn =>
          (btn.getAttribute('onclick') || '').includes("switchTab('" + tabId + "')")
        );
      }
      if (activeButton) activeButton.classList.add('active');
      if (tabId === 'logs') loadLogs();
    }

    // Explicit event listener avoids Android browser implicit `event` issues.
    function handleFileSelect(fileInput) {
      if (!fileInput || !fileInput.files || !fileInput.files.length) return;
      const file = fileInput.files[0];
      currentFilename = file.name;
      const reader = new FileReader();
      reader.onload = function() {
        if (!(reader.result instanceof ArrayBuffer)) { alert('Could not read the selected file. Please select it again.'); return; }
        uploadRawFile(file.name, new Uint8Array(reader.result));
      };
      reader.onerror = function() { alert('File read failed. Please try the file again.'); };
      reader.readAsArrayBuffer(file);
      fileInput.value = '';
    }
    document.addEventListener('DOMContentLoaded', function() {
      const fileInput = document.getElementById('file-input');
      if (fileInput) fileInput.addEventListener('change', function() { handleFileSelect(fileInput); });
    });

    function uploadRawFile(filename, bytes) {
      // Send to local API
      fetch('/api/preview-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': filename },
        body: bytes
      })
      .then(async res => {
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || ('HTTP ' + res.status));
        }
        renderPreview(data);
      })
      .catch(err => alert('CSV/Excel upload failed: ' + err.message));
    }


    function renderPreview(data) {
      // Keep the COMPLETE parsed dataset for processing. Only the table preview is limited.
      currentParsedData = Array.isArray(data.records) ? data.records : [];
      currentFilename = data.filename || 'scraped_jobs.csv';

      document.getElementById('preview-section').classList.remove('hidden');
      document.getElementById('preview-count').innerText = 'Total records detected: ' + data.total_records;

      // Render column badges
      const badgesContainer = document.getElementById('mapped-badges');
      badgesContainer.innerHTML = '';
      for (const [orig, canonical] of Object.entries(data.mapped_columns)) {
        const span = document.createElement('span');
        span.className = 'mapped-tag';
        span.innerHTML = `<strong>${orig}</strong> &rarr; <span style="color:var(--accent)">${canonical}</span>`;
        badgesContainer.appendChild(span);
      }

      // Render table preview (first 5 rows)
      const thead = document.getElementById('preview-thead');
      const tbody = document.getElementById('preview-tbody');
      thead.innerHTML = '';
      tbody.innerHTML = '';

      const previewRows = data.preview_records || currentParsedData.slice(0, 5);
      const headers = Object.keys(currentParsedData[0] || {});
      const trH = document.createElement('tr');
      headers.forEach(h => {
        const th = document.createElement('th');
        th.innerText = h;
        trH.appendChild(th);
      });
      thead.appendChild(trH);

      previewRows.slice(0, 5).forEach(row => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
          const td = document.createElement('td');
          td.innerText = row[h] || '—';
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    function executePipeline() {
      if (!currentParsedData) return;
      document.getElementById('btn-run-pipeline').innerText = 'Processing on SQLite...';

      const runButton = document.getElementById('btn-run-pipeline');
      runButton.disabled = true;
      runButton.innerText = 'Importing records into SQLite...';
      fetch('/api/process-leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: currentParsedData,
          filename: currentFilename,
          min_score: 0.00
        })
      })
      .then(async r => {
        const result = await r.json();
        if (!r.ok || result.error) throw new Error(result.error || ('HTTP ' + r.status));
        return result;
      })
      .then(result => {
        renderResults(result);
        switchTab('leads');
        alert('Import complete: ' + result.total_records + ' records saved. Online research is separate; use “Research all qualified leads” when you are ready.');
      })
      .catch(err => {
        alert('Import failed: ' + (err && err.message ? err.message : String(err)) + '. Your original file is still available; check Activity Logs for details.');
      })
      .finally(() => {
        runButton.disabled = false;
        runButton.innerText = 'Run Lead Qualification & Scoring';
      });
    }

    function renderResults(res) {
      document.getElementById('stat-total').innerText = res.total_records;
      document.getElementById('stat-qualified').innerText = res.qualified_count;
      document.getElementById('stat-qualified').title = 'Ready ' + (res.ready_count || 0) + ' / Needs review ' + (res.review_count || 0);
      document.getElementById('stat-dups').innerText = res.duplicates_count;
      document.getElementById('stat-expired').innerText = res.expired_count || 0;
      loadSelected();
      document.getElementById('stat-avg').innerText = res.average_score.toFixed(2);

      // Render leads table
      const leadsTbody = document.getElementById('leads-tbody');
      leadsTbody.innerHTML = '';
      latestQualifiedLeads = res.qualified_leads || [];
      (res.qualified_leads || []).forEach((lead, leadIndex) => {
        const tr = document.createElement('tr');
        const scoreClass = lead.qualification_score >= 0.8 ? 'score-high' : (lead.qualification_score >= 0.6 ? 'score-med' : 'score-low');
        tr.innerHTML = `
          <td><span class="score-badge ${scoreClass}">${lead.qualification_score.toFixed(2)}</span></td>
          <td><strong>${lead.company || '—'}</strong><br><span title="${safeText(lead.class_reason)}" style="font-size:11px;color:${lead.lead_class === 'Ready' ? '#34d399' : '#f59e0b'}">${safeText(lead.lead_class || '')}${lead.lead_class === 'Needs review' ? ': ' + safeText(lead.class_reason) : ''}</span></td>
          <td>${lead.job_title || '—'}</td>
          <td>${lead.hr_name ? lead.hr_name + (lead.hr_title ? ' (' + lead.hr_title + ')' : '') : '—'}</td>
          <td><span style="color:#34d399">${lead.normalized_email || lead.email || '—'}</span></td>
          <td><span style="color:#38bdf8">${lead.phone_e164 || lead.phone || '—'}</span></td>
          <td><span style="font-size:11px; color:#9ca3af">${lead.company_status || 'Not researched'}</span></td>
          <td><div style="font-size:12px;line-height:1.45;color:#cbd5e1;max-width:320px;">${safeText(scoreReasonPreview(lead))}</div><button class="btn btn-secondary" style="margin-top:7px;" onclick="showScoreDetails(${leadIndex})">Full score & internet evidence</button></td>
        `;
        leadsTbody.appendChild(tr);
      });

      // Render rejected records separately (not duplicates).
      const rejectedTbody = document.getElementById('rejected-tbody');
      rejectedTbody.innerHTML = '';
      (res.rejected_leads || []).forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${item.company || '—'}</td><td>${item.job_title || '—'}</td><td>${item.email || '—'}</td><td>${item.phone || '—'}</td><td style="color:#f43f5e">${item.rejection_reason || 'Both contact fields missing'}</td>`;
        rejectedTbody.appendChild(tr);
      });

      // Render duplicates
      const dupsTbody = document.getElementById('dups-tbody');
      dupsTbody.innerHTML = '';
      (res.duplicates || []).forEach(dup => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${dup.company || '—'}</td>
          <td>${dup.job_title || '—'}</td>
          <td>${dup.email || '—'}</td>
          <td>${dup.phone || '—'}</td>
          <td style="color:#f59e0b; font-family:var(--font-mono); font-size:11px;">${dup.duplicate_reason || 'Duplicate'}</td>
        `;
        dupsTbody.appendChild(tr);
      });
    }

    function safeText(value) {
      return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function parseJsonObject(value, fallback) {
      if (value && typeof value === 'object') return value;
      try { return JSON.parse(value || (Array.isArray(fallback) ? '[]' : '{}')); } catch (e) { return fallback; }
    }
    function scoreReasonPreview(lead) {
      const reasons = parseJsonObject(lead.score_explanation, {});
      const positive = Object.entries(reasons).filter(([k,v]) => typeof v === 'string' && /^\s*\+0\.(?!00)\d+/.test(v));
      if (positive.length) return positive.slice(0, 2).map(([k,v]) => v.replace(/^\s*/, '')).join(' ');
      const fallback = Object.values(reasons).find(v => typeof v === 'string');
      return fallback || 'Score breakdown and research evidence are available in the detail view.';
    }
    function showScoreDetails(index) {
      const lead = latestQualifiedLeads[index];
      if (!lead) return;
      let breakdown = {}, explanations = {}, evidence = [], sources = [];
      try { breakdown = typeof lead.score_breakdown === 'string' ? JSON.parse(lead.score_breakdown || '{}') : (lead.score_breakdown || {}); } catch(e) {}
      try { explanations = typeof lead.score_explanation === 'string' ? JSON.parse(lead.score_explanation || '{}') : (lead.score_explanation || {}); } catch(e) {}
      try { evidence = typeof lead.research_evidence === 'string' ? JSON.parse(lead.research_evidence || '[]') : (lead.research_evidence || []); } catch(e) {}
      try { sources = typeof lead.research_sources === 'string' ? JSON.parse(lead.research_sources || '[]') : (lead.research_sources || []); } catch(e) {}
      const factorNames = {
        contact_email:'Email quality', contact_phone:'Phone quality', role_seniority:'Job-title relevance',
        hr_directness:'HR contact details', company_web_presence:'Company website reachability',
        public_web_evidence:'Verified public sources', company_profile_evidence:'Company profile evidence', job_relevance_evidence:'Job relevance evidence', hiring_evidence:'Hiring evidence', hr_public_association:'Public HR association', careers_evidence:'Careers indicator',
        data_completeness:'Record completeness'
      };
      let html = `<div style="margin-bottom:14px;"><strong>${safeText(lead.company || 'Unknown company')}</strong> — ${safeText(lead.job_title || '')}<div style="font-size:28px;font-weight:800;color:#34d399;margin-top:6px;">${Number(lead.qualification_score || 0).toFixed(2)} / 1.00</div><div style="color:#9ca3af;font-size:12px;">${safeText(lead.tier || '')}</div></div>`;
      html += '<h3 style="margin:12px 0 8px;">How the score was calculated</h3><table><thead><tr><th>Factor</th><th>Points</th><th>Reason</th></tr></thead><tbody>';
      Object.keys(factorNames).forEach(key => {
        html += `<tr><td>${factorNames[key]}</td><td>${Number(breakdown[key] || 0).toFixed(2)}</td><td>${safeText(explanations[key] || 'No points awarded / no explanation recorded.')}</td></tr>`;
      });
      html += '</tbody></table>';
      html += `<h3 style="margin:18px 0 8px;">What internet research found</h3><p style="font-size:13px;color:#cbd5e1;margin-bottom:8px;">${safeText(lead.company_summary || 'No research summary available.')}</p>`;
      if (lead.research_retrieved_at) html += `<p style="font-size:11px;color:#94a3b8;">Retrieved: ${safeText(lead.research_retrieved_at)}</p>`;
      if (evidence.length) {
        html += '<div style="display:grid;gap:10px;margin-top:10px;">';
        evidence.forEach(ev => {
          const url = String(ev.url || '');
          const safeUrl = /^https?:\/\//i.test(url) ? url : '';
          html += `<div style="border:1px solid #334155;border-radius:6px;padding:10px;"><div style="font-weight:700;">${safeText(ev.title || 'Research finding')}</div><div style="font-size:12px;color:#cbd5e1;margin:5px 0;">${safeText(ev.snippet || 'No snippet available.')}</div><div style="font-size:11px;color:#94a3b8;">Type: ${safeText(ev.kind || 'web result')} · ${safeText(ev.evidence_level || 'unclassified evidence')} · ${ev.verified_for_company ? 'Company match checked' : 'Not independently matched'} · ${safeText(ev.retrieved_at || '')}</div>${safeUrl ? `<a href="${safeText(safeUrl)}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8;word-break:break-all;">${safeText(safeUrl)}</a>` : '<span>Source URL unavailable</span>'}</div>`;
        });
        html += '</div>';
      } else {
        html += '<p style="color:#fbbf24;font-size:13px;">No public web evidence was retrieved. Research-related points should therefore be zero.</p>';
      }
      html += '<h3 style="margin:18px 0 8px;">How online findings affected the score</h3>';
      const webPoints = Number(breakdown.public_web_evidence || 0);
      const profilePoints = Number(breakdown.company_profile_evidence || 0);
      const jobPoints = Number(breakdown.job_relevance_evidence || 0);
      const hiringPoints = Number(breakdown.hiring_evidence || 0);
      const hrPoints = Number(breakdown.hr_public_association || 0);
      if (webPoints > 0 || profilePoints > 0 || jobPoints > 0 || hiringPoints > 0 || hrPoints > 0) {
        html += `<p style="font-size:13px;color:#cbd5e1;">Verified public-source evidence: ${webPoints.toFixed(2)}; company profile: ${profilePoints.toFixed(2)}; job relevance: ${jobPoints.toFixed(2)}; hiring evidence: ${hiringPoints.toFixed(2)}; public HR association: ${hrPoints.toFixed(2)}. Points require fetched pages with company identity matching. Open the source URLs to verify context.</p>`;
      } else {
        html += '<p style="font-size:13px;color:#fbbf24;">No public internet evidence points were awarded. The score comes from supplied contact details, job-title heuristics, HR fields and limited imported-data completeness. Website HTTP reachability alone earns no research points.</p>';
      }
      html += '<h3 style="margin:18px 0 8px;">Source links</h3>';
      if (sources.length) sources.forEach(url => { if (/^https?:\/\//i.test(url)) html += `<div style="margin:5px 0;"><a href="${safeText(url)}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8;word-break:break-all;">${safeText(url)}</a></div>`; });
      else html += '<p style="font-size:13px;color:#9ca3af;">No source links saved.</p>';
      html += '<p style="font-size:11px;color:#9ca3af;margin-top:16px;">Important: search snippets are third-party summaries, not verified facts. Open the source to confirm. A reachable website does not prove a company is currently operating. Search snippets alone earn no research points. Scores are conservative heuristic lead-priority scores, not conversion probabilities.</p>';
      document.getElementById('score-modal-body').innerHTML = html;
      document.getElementById('score-modal').classList.remove('hidden');
    }
    function closeScoreDetails() { document.getElementById('score-modal').classList.add('hidden'); }

    function loadLogs() {
      fetch('/api/logs')
        .then(r => r.text())
        .then(txt => document.getElementById('log-content').innerText = txt);
    }

    function exportData(format, status='qualified') {
      let url = '/api/export?format=' + encodeURIComponent(format) + '&status=' + encodeURIComponent(status);
      if (status === 'selected') url += '&select=' + encodeURIComponent(document.getElementById('sel-mode').value);
      window.location.href = url;
    }
    function loadSelected() {
      const sel = document.getElementById('sel-mode');
      fetch('/api/selected?mode=' + encodeURIComponent(sel.value)).then(r => r.json()).then(data => {
        const names = {any: 'Valid mobile or email', email: 'Valid email', mobile: 'Valid mobile number', both: 'Valid email and mobile'};
        Array.from(sel.options).forEach(o => { o.text = names[o.value] + ' (' + ((data.counts || {})[o.value] || 0) + ')'; });
        document.getElementById('sel-summary').innerText = data.count + ' lead(s) selected: ' + data.label + '. Expired, duplicate and rejected leads are never selected.';
        const tbody = document.getElementById('sel-tbody');
        tbody.innerHTML = '';
        if (!data.leads.length) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b;">No leads match this selection.</td></tr>'; return; }
        data.leads.forEach(lead => {
          const sc = Number(lead.qualification_score || 0);
          const cls = sc >= 0.8 ? 'score-high' : (sc >= 0.6 ? 'score-med' : 'score-low');
          const tr = document.createElement('tr');
          tr.innerHTML = '<td><span class="score-badge ' + cls + '">' + sc.toFixed(2) + '</span></td>' +
            '<td><strong>' + safeText(lead.company || '—') + '</strong><br><span style="font-size:11px;color:#9ca3af">' + safeText(lead.lead_class || '') + '</span></td>' +
            '<td>' + safeText(lead.hr_name || '—') + '</td>' +
            '<td><span style="color:#34d399">' + safeText(lead.normalized_email || lead.email || '—') + '</span></td>' +
            '<td><span style="color:#38bdf8">' + safeText(lead.phone_e164 || lead.phone || '—') + '</span></td>' +
            '<td style="font-size:12px;color:#cbd5e1;max-width:360px;">' + safeText(lead.selection_reason) + '</td>';
          tbody.appendChild(tr);
        });
      }).catch(() => {});
    }
    async function rerunDeepResearch() {
      const btn=document.getElementById('deep-research-btn');
      if (!confirm('Run public-web research for every qualified lead? This runs in the background and may take several minutes.')) return;
      btn.disabled=true; btn.textContent='Starting research…';
      try {
        const response=await fetch('/api/research-latest',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
        const result=await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not start research');
        btn.textContent='Researching 0 / '+result.total+'…';
        const poll=async()=>{
          const r=await fetch('/api/research-status'); const state=await r.json();
          btn.textContent=state.running ? `Researching ${state.completed} / ${state.total}…` : 'Research all qualified leads';
          if (state.running) { setTimeout(poll,1500); return; }
          const latest=await fetch('/api/latest').then(x=>x.json());
          if (latest && latest.has_data) renderResults(latest);
          btn.disabled=false;
          const errors=(state.errors||[]).length;
          alert(`Research finished. Updated ${state.updated} of ${state.total} leads. ${errors} errors. Leads without verified supporting evidence receive no research points.`);
        };
        poll();
      } catch(err) { btn.disabled=false; btn.textContent='Research all qualified leads'; alert('Research error: '+err.message); }
    }

    // Restore the latest saved run after refresh. This never loads demo/sample records.
    fetch('/api/latest').then(r => r.json()).then(saved => {
      if (saved && saved.has_data) {
        renderResults(saved);
        switchTab('leads');
      }
    }).catch(err => console.warn('Could not restore saved lead results:', err));
  </script>
</body>
</html>
"""

def build_xlsx_bytes(headers: List[str], rows: List[Tuple[Any, ...]]) -> bytes:
    """Create a standards-compliant minimal XLSX using only Python stdlib."""
    import io
    from xml.sax.saxutils import escape
    def col_name(n: int) -> str:
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out
    all_rows = [headers] + [list(r) for r in rows]
    xml_rows = []
    for ridx, row in enumerate(all_rows, 1):
        cells = []
        for cidx, value in enumerate(row, 1):
            ref = f"{col_name(cidx)}{ridx}"
            val = "" if value is None else str(value)
            # Store all values as inline strings to preserve phone numbers/leading zeros.
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(val)}</t></is></c>')
        xml_rows.append(f'<row r="{ridx}">{"".join(cells)}</row>')
    sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(xml_rows) + '</sheetData></worksheet>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Leads" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    rootrels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', types)
        z.writestr('_rels/.rels', rootrels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet)
    return out.getvalue()

# ==============================================================================
# PURE-PYTHON HTTP SERVER HANDLER (Runs on http://127.0.0.1:5000)
# ==============================================================================
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# Background research state: network requests must never hold an HTTP request open.
RESEARCH_JOB_LOCK = threading.Lock()
RESEARCH_JOB = {"running": False, "total": 0, "completed": 0, "updated": 0, "errors": [], "message": "Idle", "run_id": None, "started_at": None, "finished_at": None}

def _research_latest_worker(run_id: int, lead_ids: List[int]) -> None:
    global RESEARCH_JOB
    with RESEARCH_JOB_LOCK:
        RESEARCH_JOB.update({"running": True, "total": len(lead_ids), "completed": 0, "updated": 0, "errors": [], "message": "Research started", "run_id": run_id, "started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "finished_at": None})
    def process_one(lead_id: int) -> None:
        try:
            with sqlite3.connect(DB_PATH, timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM leads WHERE id=? AND run_id=?", (lead_id, run_id)).fetchone()
            if not row: raise RuntimeError("Lead record disappeared before research.")
            lead = dict(row)
            domain = lead.get('company_domain') or lead.get('company_website') or lead.get('company')
            research = research_company_online(domain, lead.get('company',''), lead.get('job_title',''), lead.get('hr_name',''), lead.get('hr_profile_url',''), force_refresh=True)
            lead.update(company_researched=int(bool(research.get('evidence'))), company_status=research.get('status','Research unavailable'),
                        company_industry=research.get('industry','Unverified'), company_tech_stack=json.dumps(research.get('tech_stack',[])),
                        company_has_careers=int(bool(research.get('has_careers'))), company_summary=research.get('summary',''),
                        research_evidence=json.dumps(research.get('evidence',[]),ensure_ascii=False), research_sources=json.dumps(research.get('sources',[]),ensure_ascii=False),
                        research_retrieved_at=research.get('retrieved_at',''))
            score, breakdown, tier, reasons = score_lead(lead)
            with sqlite3.connect(DB_PATH, timeout=30) as conn:
                conn.execute("UPDATE leads SET company_researched=?,company_status=?,company_industry=?,company_tech_stack=?,company_has_careers=?,company_summary=?,research_evidence=?,research_sources=?,research_retrieved_at=?,qualification_score=?,score_breakdown=?,score_explanation=?,tier=? WHERE id=? AND run_id=?",
                    (lead['company_researched'],lead['company_status'],lead['company_industry'],lead['company_tech_stack'],lead['company_has_careers'],lead['company_summary'],lead['research_evidence'],lead['research_sources'],lead['research_retrieved_at'],score,json.dumps(breakdown,ensure_ascii=False),json.dumps(reasons,ensure_ascii=False),tier,lead_id,run_id))
                conn.commit()
            with RESEARCH_JOB_LOCK: RESEARCH_JOB['updated'] += 1
        except Exception as exc:
            logger.exception("Research failed for lead id %s", lead_id)
            with RESEARCH_JOB_LOCK: RESEARCH_JOB['errors'].append({"lead_id": lead_id, "error": str(exc)[:240]})
        finally:
            with RESEARCH_JOB_LOCK:
                RESEARCH_JOB['completed'] += 1
                RESEARCH_JOB['message'] = f"Processed {RESEARCH_JOB['completed']} of {RESEARCH_JOB['total']} leads"
    # Ten concurrent lead workers keep typical 40-50 lead batches within about a minute
    # on a responsive network, while each lead has only two searches and two short fetches.
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix='lead-research') as pool:
        futures=[pool.submit(process_one, lead_id) for lead_id in lead_ids]
        for future in as_completed(futures):
            try: future.result()
            except Exception as exc: logger.exception('Unexpected research worker error: %s', exc)
    with RESEARCH_JOB_LOCK:
        RESEARCH_JOB['running'] = False
        RESEARCH_JOB['finished_at'] = datetime.now().astimezone().isoformat(timespec="seconds")
        RESEARCH_JOB['message'] = "Research finished" if not RESEARCH_JOB['errors'] else "Research finished with errors"


def fetch_latest_leads(run_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """All leads of the newest import run (or run_id) as dicts, best score first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if run_id is None:
            run_id = conn.execute("SELECT MAX(id) FROM import_runs").fetchone()[0]
        rows = conn.execute("SELECT * FROM leads WHERE run_id = ? ORDER BY qualification_score DESC, id ASC", (run_id or 0,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


EXPORT_COLUMNS = [
    ("Lead_ID", "raw_id"), ("Qualification_Score", "qualification_score"), ("Tier", "tier"), ("Company", "company"),
    ("Job_Title", "job_title"), ("HR_Email", "normalized_email|email"), ("Mobile_NO", "phone_e164|phone"), ("HR_Name", "hr_name"),
    ("HR_Title", "hr_title"), ("Website", "company_website"), ("Location", "location"), ("Source", "source"),
    ("Email_Status", "email_status"), ("Phone_Status", "phone_status"), ("Qualification_Status", "qualification_status"),
    ("Rejection_Reason", "rejection_reason"), ("Lead_Class", "lead_class"), ("Class_Reason", "class_reason"),
    ("Expiry_Date", "expiry_date"), ("Selection_Mode", "selection_mode"), ("Selection_Reason", "selection_reason"),
    ("Score_Breakdown_JSON", "score_breakdown"), ("Score_Explanation", "score_explanation"),
    ("Company_Research_Status", "company_status"), ("Company_Research_Summary", "company_summary"),
    ("Research_Evidence_JSON", "research_evidence"), ("Research_Source_URLs_JSON", "research_sources"),
    ("Research_Retrieved_At", "research_retrieved_at"),
]


def build_export(leads: List[Dict[str, Any]], status_filter: str, mode: str = "any") -> Tuple[List[str], List[Tuple[Any, ...]], str]:
    """Rows for /api/export. status_filter: qualified | rejected | duplicate | expired | ready | review | selected | all."""
    chosen: List[Dict[str, Any]] = []
    for x in leads:
        if status_filter == "selected":
            if x.get("qualification_status") != "qualified" or x.get("is_duplicate"):
                continue
            ok, reason = selection_result(x, mode)
            if not ok:
                continue
            x = dict(x, selection_mode=SELECT_LABELS[mode], selection_reason=reason)
        elif status_filter in ("ready", "review"):
            if x.get("lead_class") != ("Ready" if status_filter == "ready" else "Needs review"):
                continue
        elif status_filter == "expired":
            if x.get("lead_class") != "Expired":
                continue
        elif status_filter != "all" and x.get("qualification_status") != status_filter:
            continue
        chosen.append(x)
    columns = [(h, k) for h, k in EXPORT_COLUMNS if status_filter == "selected" or h not in ("Selection_Mode", "Selection_Reason")]
    rows = []
    for x in chosen:
        row = []
        for _, key in columns:
            value = ""
            for k in key.split("|"):
                if x.get(k) not in (None, ""):
                    value = x.get(k)
                    break
            row.append(value)
        rows.append(tuple(row))
    stem = f"selected_{mode}" if status_filter == "selected" else status_filter
    return [h for h, _ in columns], rows, stem


class LeadIntelligenceHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Route HTTP server logs to logger
        logger.info(f"{self.client_address[0]} - {format % args}")

    def send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            body = EMBEDDED_HTML_DASHBOARD.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/latest":
            # Restore the most recent processed run after a browser refresh/restart.
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            run_row = conn.execute("SELECT id, filename, total_records FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
            if not run_row:
                conn.close()
                self.send_json({"has_data": False})
                return
            rows = conn.execute("SELECT * FROM leads WHERE run_id = ? ORDER BY qualification_score DESC, id ASC", (run_row["id"],)).fetchall()
            conn.close()
            qualified, rejected, duplicates = [], [], []
            tier_counts = {}
            for row in rows:
                item = dict(row)
                status = item.get("qualification_status")
                if status == "duplicate" or item.get("is_duplicate"):
                    duplicates.append(item)
                elif status == "rejected":
                    rejected.append(item)
                else:
                    qualified.append(item)
                    tier = item.get("tier")
                    tier_counts[tier] = tier_counts.get(tier, 0) + 1
            scores = [float(x.get("qualification_score") or 0) for x in qualified]
            self.send_json({"has_data": True, "run_id": run_row["id"], "filename": run_row["filename"],
                            "total_records": run_row["total_records"], "qualified_count": len(qualified),
                            "rejected_count": len(rejected), "duplicates_count": len(duplicates),
                            "ready_count": sum(1 for x in qualified if x.get("lead_class") == "Ready"),
                            "review_count": sum(1 for x in qualified if x.get("lead_class") == "Needs review"),
                            "expired_count": sum(1 for x in rejected if x.get("lead_class") == "Expired"),
                            "select_counts": selection_counts(qualified),
                            "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
                            "tier_counts": tier_counts, "qualified_leads": qualified,
                            "rejected_leads": rejected, "duplicates": duplicates})
            return


        if path == "/api/selected":
            query = urllib.parse.parse_qs(parsed.query)
            mode = query.get("mode", ["any"])[0]
            if mode not in SELECT_MODES:
                mode = "any"
            live = [x for x in fetch_latest_leads() if x.get("qualification_status") == "qualified" and not x.get("is_duplicate")]
            picked = []
            for x in live:
                ok, reason = selection_result(x, mode)
                if ok:
                    picked.append(dict(x, selection_reason=reason))
            self.send_json({"mode": mode, "label": SELECT_LABELS[mode], "count": len(picked),
                            "counts": selection_counts(live), "leads": picked})
            return

        if path == "/api/logs":
            try:
                with open(LOG_PATH, "r", encoding="utf-8") as f:
                    content = f.read()[-10000:]
            except Exception:
                content = "No logs yet."
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/export":
            # Export latest qualified leads from SQLite
            query = urllib.parse.parse_qs(parsed.query)
            fmt = query.get("format", ["csv"])[0]

            status_filter = query.get("status", ["qualified"])[0]
            if status_filter not in ("qualified", "rejected", "duplicate", "all", "ready", "review", "expired", "selected"):
                status_filter = "qualified"
            mode = query.get("select", ["any"])[0]
            if mode not in SELECT_MODES:
                mode = "any"
            headers, rows, file_stem = build_export(fetch_latest_leads(), status_filter, mode)

            if fmt == "xlsx":
                body = build_xlsx_bytes(headers, rows)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f'attachment; filename="{file_stem}_leads.xlsx"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if fmt == "csv":
                import io
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([str(v or "") for v in r])
                body = out.getvalue().encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{file_stem}_leads.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                leads_json = []
                for r in rows:
                    leads_json.append(dict(zip(headers, r)))
                self.send_json(leads_json)
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))

        if path == "/api/preview-file":
            filename = self.headers.get("X-Filename", "uploaded_file.csv")
            file_bytes = self.rfile.read(length)

            try:
                records = PurePythonFileParser.parse_file(file_bytes, filename)
                if not records:
                    self.send_json({"error": "File is empty or could not be parsed."}, 400)
                    return

                # Build column mapping
                mapping = {}
                for k in records[0].keys():
                    mapped = map_column_name(k)
                    if mapped: mapping[k] = mapped

                self.send_json({
                    "filename": filename,
                    "total_records": len(records),
                    "mapped_columns": mapping,
                    # Send every parsed record for processing. The browser table is only a preview.
                    "records": records,
                    "preview_records": records[:5]
                })
            except Exception as e:
                logger.error(f"Error previewing file: {e}")
                self.send_json({"error": str(e)}, 500)
            return

        if path == "/api/ingest":
            # JSON API for other programs (the scraper): {"leads": [...], "mode": "any|email|mobile|both"}
            required_key = os.environ.get("LEADSCORE_API_KEY", "")
            if required_key and not hmac.compare_digest(self.headers.get("X-Api-Key", ""), required_key):
                self.send_json({"error": "Invalid or missing X-Api-Key"}, 401)
                return
            if length > 20 * 1024 * 1024:
                self.send_json({"error": "Request too large"}, 413)
                return
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                leads = payload.get("leads")
                if not isinstance(leads, list):
                    self.send_json({"error": "'leads' must be a list of objects"}, 400)
                    return
                self.send_json(evaluate_leads(leads, str(payload.get("mode") or "any"),
                                              persist=bool(payload.get("persist", True)),
                                              filename=str(payload.get("source") or "api-ingest")))
            except ValueError:
                self.send_json({"error": "Body must be valid JSON"}, 400)
            except Exception as e:
                logger.error(f"Error in /api/ingest: {e}")
                self.send_json({"error": str(e)}, 500)
            return

        if path == "/api/research-latest":
            try:
                with RESEARCH_JOB_LOCK:
                    if RESEARCH_JOB.get("running"):
                        self.send_json({"error":"Research is already running.","running":True},409); return
                with sqlite3.connect(DB_PATH, timeout=30) as conn:
                    row=conn.execute("SELECT MAX(id) FROM import_runs").fetchone()
                    run_id=row[0] if row else None
                    if not run_id:
                        self.send_json({"error":"No imported run is available."},400); return
                    ids=[r[0] for r in conn.execute("SELECT id FROM leads WHERE run_id=? AND qualification_status='qualified' AND is_duplicate=0 ORDER BY id",(run_id,)).fetchall()]
                if not ids:
                    self.send_json({"error":"There are no qualified non-duplicate leads to research."},400); return
                thread=threading.Thread(target=_research_latest_worker,args=(run_id,ids),daemon=True,name="lead-research-worker")
                thread.start()
                self.send_json({"ok":True,"started":True,"total":len(ids),"run_id":run_id})
            except Exception as exc:
                logger.exception("Could not start research worker")
                self.send_json({"error":str(exc)},500)
            return

        if path == "/api/research-status":
            with RESEARCH_JOB_LOCK:
                self.send_json(dict(RESEARCH_JOB))
            return

        if path == "/api/process-leads":
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
            records = payload.get("records", [])
            filename = payload.get("filename", "batch.csv")
            min_score = float(payload.get("min_score", 0.0))

            try:
                # Keep import fast and reliable on Android. Network research is an explicit
                # follow-up action from the dashboard after the SQLite transaction commits.
                res = process_leads_dataset(records, filename, min_score=min_score, enable_research=False)
                self.send_json(res)
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                self.send_json({"error": str(e)}, 500)
            return

        self.send_response(404)
        self.end_headers()

# ==============================================================================
# ENTRY POINT
# ==============================================================================
def run_local_server(port: int = 5000):
    init_database()
    bind_host = os.environ.get("LEADSCORE_HOST", "127.0.0.1")  # set 0.0.0.0 (+ LEADSCORE_API_KEY) to let the scraper reach it over a network
    server_address = (bind_host, port)
    logger.info(f"Starting Termux Local Web Server at http://127.0.0.1:{port}")
    print(f"\n========================================================")
    print(f"  TERMUX LEAD INTELLIGENCE ENGINE ONLINE")
    print(f"  Local Web Interface: http://127.0.0.1:{port}")
    print(f"  SQLite Database:     {DB_PATH}")
    print(f"  Logs:                {LOG_PATH}")
    print(f"========================================================\n")

    httpd = ThreadedHTTPServer(server_address, LeadIntelligenceHTTPHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        httpd.server_close()

def main():
    parser = argparse.ArgumentParser(description="Lead Intelligence & Qualification for Android Termux")
    parser.add_argument("--web", action="store_true", help="Launch local web dashboard on http://127.0.0.1:5000")
    parser.add_argument("--port", type=int, default=5000, help="Web server port (default: 5000)")
    parser.add_argument("--input", "-i", help="Run in CLI mode with input CSV/XLSX file")
    parser.add_argument("--output", "-o", default="qualified_leads.csv", help="CLI output CSV path")
    parser.add_argument("--min-score", "-s", type=float, default=0.40, help="Cutoff score (0.00 - 1.00)")
    parser.add_argument("--test", action="store_true", help="Run automated self-tests")

    args = parser.parse_args()

    init_database()

    if args.test:
        from test_suite import run_all_tests
        success = run_all_tests()
        sys.exit(0 if success else 1)

    if args.input:
        with open(args.input, "rb") as f:
            raw_bytes = f.read()
        records = PurePythonFileParser.parse_file(raw_bytes, args.input)
        res = process_leads_dataset(records, args.input, min_score=args.min_score)
        print(f"Processed {res['total_records']} records: {res['ready_count']} Ready, {res['review_count']} Needs review, "
              f"{res['rejected_count']} Rejected ({res['expired_count']} expired), {res['duplicates_count']} Duplicate. "
              f"Selected: any {res['select_counts']['any']}, email {res['select_counts']['email']}, mobile {res['select_counts']['mobile']}, both {res['select_counts']['both']}.")
        return

    # Default to web server
    run_local_server(port=args.port)

if __name__ == "__main__":
    main()
