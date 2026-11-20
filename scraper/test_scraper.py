"""Offline tests for the scraper (no internet, no browser). Run: python test_scraper.py"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SCRAPER_OUTPUT_DIR", tempfile.mkdtemp())
import linkedin_hr_scraper as m  # noqa: E402
if not os.path.exists(m.HR_EXCEL_FILE):  # the HR data holds personal contacts and is not in the repository
    print("[SKIP] leads_with_hr.xlsx not found next to main.py (or HR_EXCEL_PATH): these tests need the HR data file.")
    sys.exit(0)
import lead_validation as v  # noqa: E402

passed = total = 0


def check(name, cond):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("[PASS] " if cond else "[FAIL] ") + name)


def card(job_id, title, company, loc, posted="2026-11-01"):
    return (f'<li><div class="base-card"><a class="base-card__full-link" '
            f'href="https://in.linkedin.com/jobs/view/{title.lower().replace(" ", "-")}-at-{company.lower().replace(" ", "-")}-{job_id}?trk=x&refId=1">'
            f'</a><h3 class="base-search-card__title">{title}</h3><h4 class="base-search-card__subtitle">{company}</h4>'
            f'<span class="job-search-card__location">{loc}</span><time datetime="{posted}">x</time></div></li>')


LONG = "Build services in Python and cloud. " * 12
SEARCH_PAGE_1 = "<ul>" + card(4468591455, "Software Engineer III", "FactSet", "Hyderabad") + \
    card(1111111111, "Python Developer", "Unknown Startup", "Hyderabad") + \
    card(2222222222, "Data Analyst", "Old Co", "Hyderabad") + "</ul>"
POSTINGS = {
    "4468591455": f'<div class="show-more-less-html__markup">{LONG}</div>',
    "1111111111": f'<div class="show-more-less-html__markup">{LONG}</div>',
    "2222222222": '<div>This job is no longer accepting applications</div>',
}
calls = []


def fake_fetch(url):
    calls.append(url)
    if "seeMoreJobPostings" in url:
        return SEARCH_PAGE_1 if "start=0" in url else ""
    for jid, body in POSTINGS.items():
        if url.endswith(jid):
            return body
    return ""


# validation
check("email: valid / generic / disposable / invalid", [v.validate_email(x) for x in ("a.b@acme.com", "hr@acme.com", "x@getnada.com", "bad@@x")] == ["Valid", "Generic", "Invalid (Disposable)", "Invalid"])
check("phone: formats normalise to +91", v.validate_phone("98765 01234")[1] == "+919876501234" and v.validate_phone("+91-9876501234")[0] == "Valid")
check("phone: dummy + short rejected", v.validate_phone("9876543210")[0] == "Invalid (Dummy)" and v.validate_phone("12345")[0] == "Invalid")
# helpers
check("clean_job_url drops tracking", m.clean_job_url("https://in.linkedin.com/jobs/view/x-123456789?trk=a&refId=b") == "https://in.linkedin.com/jobs/view/x-123456789")
check("parse_query splits location", m.parse_query("Python Developer in Hyderabad") == ("Python Developer", "Hyderabad") and m.parse_query("Python", "Pune") == ("Python", "Pune") and m.parse_query("Python")[1] == "India")
check("company normaliser ignores suffixes", m.normalize_company("Capgemini Technology Services India Pvt. Ltd.") == m.normalize_company("Capgemini"))
# parsing
jobs = m.parse_search_cards(SEARCH_PAGE_1)
check("guest cards parsed", len(jobs) == 3 and jobs[0]["company"] == "FactSet" and jobs[0]["url"].endswith("4468591455") and "trk" not in jobs[0]["url"])
check("posting detail: description + expired", m.parse_posting_detail(POSTINGS["4468591455"])["description"].startswith("Build") and m.parse_posting_detail(POSTINGS["2222222222"])["expired"])
# HR index from the real HR workbook
idx = m.load_existing_hr_data()
check("HR workbook loaded (at least 49 rows)", idx["count"] >= 49 and len(idx["by_url"]) >= 40)
lead = m.match_existing_hr({"JOB TITLE": "Software Engineer III -Python AI/ML", "COMPANY": "FactSet", "JOB URL": "https://in.linkedin.com/jobs/view/software-engineer-iii-python-ai-ml-at-factset-4468591455?x=1"}, idx)
check("match by URL gives valid email + phone", lead["HR MATCH"] == "url" and lead["EMAIL STATUS"] == "Valid" and lead["PHONE STATUS"] == "Valid" and "@factset.com" in lead["HR CONTACT"] and lead["HR PHONE"].startswith("+91"))
lead2 = m.match_existing_hr({"JOB TITLE": "Other role", "COMPANY": "FactSet India Pvt Ltd", "JOB URL": "https://x/jobs/view/o-999999999"}, idx)
check("fallback match by company", lead2["HR MATCH"] == "company" and lead2["HR EMAIL"] != m.NOT_DISCLOSED)
none = m.match_existing_hr({"JOB TITLE": "T", "COMPANY": "No Such Company"}, idx)
check("no match -> Not Disclosed contact", none["HR CONTACT"] == m.NOT_DISCLOSED and none["VERIFICATION"] == m.NOT_DISCLOSED)
bad = m.match_existing_hr({"COMPANY": "Z", "JOB TITLE": "T", "HR EMAIL": "x@getnada.com", "HR PHONE": "9876543210"}, None)
check("disposable email and dummy phone are dropped", bad["HR EMAIL"] == m.NOT_DISCLOSED and bad["HR PHONE"] == m.NOT_DISCLOSED and bad["HR CONTACT"] == m.NOT_DISCLOSED and "not disclosed" in bad["VERIFICATION"].lower())
gen = m.match_existing_hr({"COMPANY": "Z", "JOB TITLE": "T", "HR EMAIL": "careers@z.com"}, None)
check("generic mailbox keeps the 'generic email' label", gen["VERIFICATION"] == "Unverified (generic email)")

# placeholder HR rows ("Not found") must not count as HR data
fake_idx = {"by_url": {"https://x/jobs/view/a-123456789": {"HR NAME": "", "HR TITLE": "", "HR EMAIL": "", "HR PHONE": "", "HR PROFILE URL": ""}},
            "by_company_job": {}, "by_company": {}, "count": 1}
nf = m.match_existing_hr({"JOB TITLE": "T", "COMPANY": "Z", "JOB URL": "https://x/jobs/view/a-123456789", "HR NAME": "Not found"}, fake_idx)
_full = {"COMPANY": "Z", "JOB TITLE": "T", "AREA / LOCATION": "X", "FULL DESCRIPTION": "d" * 250, "HR NAME": "Ann Lee", "HR EMAIL": "ann.lee@zcorp.com", "HR PHONE": "+919876501234"}
check("company-only HR match is capped at 90, exact matches keep 100", m.score_lead({**_full, "HR MATCH": "company"}) == 90 and m.score_lead({**_full, "HR MATCH": "url"}) == 100 and m.score_lead(_full) == 100)
check("'Not found' HR name is not scored and gives no match", "HR MATCH" not in nf and nf["HR NAME"] == m.NOT_DISCLOSED and m.score_lead({"COMPANY": "Z", "JOB TITLE": "T", "HR NAME": "Not found"}) == 20)
# end to end with fake network
out = m.run_master_job_army("Python Developer in Hyderabad", limit=5, fetch=fake_fetch, hr_index=idx, use_browser_fallback=False, pause=0)
names = [x["COMPANY"] for x in out]
check("e2e: expired job removed", "Old Co" not in names and len(out) == 2)
check("e2e: HR-matched lead ranks first with a high score", out[0]["COMPANY"] == "FactSet" and out[0]["SCORE"] >= 80 and out[1]["SCORE"] < out[0]["SCORE"])
check("e2e: lead has every key the UI/CRM needs", all(k in out[0] for k in ("SCORE", "COMPANY", "JOB TITLE", "AREA / LOCATION", "SALARY", "HR NAME", "HR CONTACT", "VERIFICATION", "SOURCE", "JOB URL", "FULL DESCRIPTION", "DISCOVERED")))
check("e2e: limit respected", len(m.run_master_job_army("Python", limit=1, fetch=fake_fetch, hr_index=idx, use_browser_fallback=False, pause=0)) == 1)
check("e2e: empty network returns [] (no crash)", m.run_master_job_army("Python", fetch=lambda u: "", hr_index=idx, use_browser_fallback=False, pause=0) == [])
try:
    m.run_master_job_army("  ")
    check("empty query raises", False)
except ValueError:
    check("empty query raises", True)
path = m.save_to_excel(out)
import openpyxl  # noqa: E402
ws = openpyxl.load_workbook(path).active
check("Excel export has header + 2 rows", ws.max_row == 3 and ws.cell(1, 1).value == "SCORE")

# FastAPI layer
try:
    from fastapi.testclient import TestClient
    import main
    main.run_master_job_army = lambda **kw: out  # stub the network part
    c = TestClient(main.app)
    check("API health", c.get("/").json()["status"] == "ok")
    for stype, q, expect in (("company", "factset", 1), ("name", "anupma", 1), ("email", "@capgemini.com", 1)):
        jid = c.post("/scrape", json={"query": q, "search_type": stype, "limit": 5}).json()["job_id"]
        for _ in range(50):
            r = c.get(f"/scrape/{jid}").json()
            if r["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        check(f"API HR search by {stype}", r["status"] == "done" and len(r["results"]) >= expect and r["results"][0]["VERIFICATION"].startswith("Unverified"))
    jid = c.post("/scrape", json={"query": "Python Developer", "search_type": "all", "limit": 5}).json()["job_id"]
    time.sleep(0.5)
    r = c.get(f"/scrape/{jid}").json()
    check("API job search ('all') keeps only leads the intelligent tool selects", r["status"] == "done" and len(r["results"]) == 1 and r["results"][0]["TOOL_SELECTED"] is True and "removed by the intelligent tool" in r["note"])
    jid = c.post("/scrape", json={"query": "*", "search_type": "all"}).json()["job_id"]
    for _ in range(100):
        r = c.get(f"/scrape/{jid}").json()
        if r["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    check("API '*' lists every available lead, all screened by the tool, no LinkedIn call", r["status"] == "done" and len(r["results"]) >= 10 and all(x["TOOL_SELECTED"] for x in r["results"]) and len({x["HR EMAIL"] for x in r["results"]}) == len(r["results"]))
    check("API rejects bad search_type", c.post("/scrape", json={"query": "x", "search_type": "zzz"}).status_code == 400)
    # smart search: never a silent "0 leads"
    class Req:  # minimal stand-in for ScrapeRequest
        def __init__(self, q, t="all"):
            self.query, self.search_type, self.limit, self.location, self.max_pages, self.headful = q, t, 10, "", 2, False
            self.selection = "any"
    main.run_master_job_army = lambda **kw: []
    res, note = main.smart_search(Req("factset"))
    check("smart search: empty LinkedIn falls back to HR company match + note", len(res) >= 1 and "HR records matching the company" in note)
    res, note = main.smart_search(Req("someone-who-does-not-exist-zzz"))
    check("smart search: nothing anywhere -> empty list with an explaining note", res == [] and "No jobs found on LinkedIn" in note)
    res, note = main.smart_search(Req(idx["by_company"][m.normalize_company("FactSet")]["HR EMAIL"]))
    check("smart search: an email query looks up the HR data", len(res) == 1 and note == "")
    def boom(**kw):
        raise RuntimeError("HTTP 429")
    main.run_master_job_army = boom
    res, note = main.smart_search(Req("zzz-nothing-zzz"))
    check("smart search: LinkedIn error is reported in the note, no crash", res == [] and "429" in note)
    res, note = main.smart_search(Req("zzz-nothing-zzz", "company"))
    check("smart search: HR search with no match explains why", res == [] and "No HR record" in note)
    # intelligent-tool connection
    import intelligent_filter as ifl
    mixed = [
        {"COMPANY": "A", "JOB TITLE": "Dev", "HR EMAIL": "a.b@acme.com", "HR PHONE": "+919876501234", "SCORE": 100},
        {"COMPANY": "B", "JOB TITLE": "Dev", "HR EMAIL": "Not Disclosed", "HR PHONE": "Not Disclosed", "SCORE": 35},
        {"COMPANY": "C", "JOB TITLE": "Dev", "HR EMAIL": "x@getnada.com", "HR PHONE": "9876543210", "SCORE": 60},
        {"COMPANY": "D", "JOB TITLE": "Dev", "HR EMAIL": "Not Disclosed", "HR PHONE": "+919123456780", "SCORE": 50},
    ]
    kept, fnote = ifl.apply_filter(mixed)
    check("filter keeps leads with a valid email or mobile, drops the rest", [k["COMPANY"] for k in kept] == ["A", "D"] or [k["COMPANY"] for k in kept] == ["D", "A"])
    check("every kept lead carries reason, tool score, class and engine", all(k["SELECTION_REASON"].startswith("Selected") and k["TOOL_SCORE"] > 0 and k["LEAD_CLASS"] and k["TOOL_ENGINE"] for k in kept))
    check("filter note says how many were removed", "2 of 4 leads removed by the intelligent tool" in fnote)
    # A's domain may or may not have MX records depending on the network (real DNS lookup), so only
    # assert what must hold everywhere: a phone-only, disposable or contact-less lead never passes 'email'.
    check("selection mode 'email' never keeps phone-only, disposable or contact-less leads", not ({k["COMPANY"] for k in ifl.apply_filter(mixed, "email")[0]} & {"B", "C", "D"}))
    os.environ["INTELLIGENT_FILTER"] = "off"
    check("INTELLIGENT_FILTER=off passes every lead through unchanged", ifl.apply_filter(mixed) == (mixed, ""))
    del os.environ["INTELLIGENT_FILTER"]
    os.environ["LEADSCORE_DIR"] = "/nonexistent/dir"
    ifl._local_module = None
    ann, eng = ifl.evaluate(mixed)
    check("tool missing -> built-in rules are used, same selection", eng == "built-in" and [a["TOOL_SELECTED"] for a in ann] == [True, False, False, True])
    del os.environ["LEADSCORE_DIR"]
    ifl._local_module = None
    # tool reached over HTTP (a tiny fake tool server)
    import json as _json, threading, http.server
    class Fake(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            res = [{"index": i, "selected": bool(r["HR Email"]), "selection_reason": "fake " + r["Company"], "score": 0.9, "lead_class": "Ready"} for i, r in enumerate(body["leads"])]
            data = _json.dumps({"results": res}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)
    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["INTELLIGENT_TOOL_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
    ann, eng = ifl.evaluate(mixed)
    check("tool reached over HTTP when INTELLIGENT_TOOL_URL is set", eng == "tool-http" and ann[0]["SELECTION_REASON"] == "fake A" and ann[0]["TOOL_SELECTED"] and not ann[1]["TOOL_SELECTED"])
    srv.shutdown(); srv.server_close()
    check("tool URL down -> falls back to the local tool, no crash", ifl.evaluate(mixed)[1] in ("tool-local", "built-in"))
    del os.environ["INTELLIGENT_TOOL_URL"]
    # company discovery (fake website fetcher, no network)
    import company_discovery as cd
    sites = {
        "https://www.zentechsolutions.com": "<title>Zentech Solutions - IT services</title>",
        "https://www.zentechsolutions.com/contact": 'Mail <a href="mailto:careers@zentechsolutions.com">us</a>, sales@zentechsolutions.com, other@elsewhere.com, logo@zentechsolutions.com.png call +91 98765 01234',
        "https://www.phoneonlyco.com": "<title>PhoneOnly Co</title>",
        "https://www.phoneonlyco.com/contact-us": "Reach us +91 91234 56780",
    }
    fake = lambda url: sites.get(url, "")
    jobs_in = [
        {"COMPANY": "Zentech Solutions Pvt Ltd", "JOB TITLE": "Python Dev", "AREA / LOCATION": "Pune", "JOB URL": "u1", "HR CONTACT": m.NOT_DISCLOSED},
        {"COMPANY": "Zentech Solutions", "JOB TITLE": "QA", "AREA / LOCATION": "Pune", "JOB URL": "u2", "HR CONTACT": m.NOT_DISCLOSED},
        {"COMPANY": "PhoneOnly Co", "JOB TITLE": "Dev", "HR CONTACT": m.NOT_DISCLOSED},
        {"COMPANY": "Ghost Corp", "JOB TITLE": "Dev", "HR CONTACT": m.NOT_DISCLOSED},
        {"COMPANY": "HasHR Inc", "JOB TITLE": "Dev", "HR CONTACT": "a.b@hashr.com"},
    ]
    cos = cd.collect_companies(jobs_in)
    check("discovery: companies deduplicated, ones with an HR contact skipped", [c["company"] for c in cos] == ["Zentech Solutions Pvt Ltd", "PhoneOnly Co", "Ghost Corp"] and len(cos[0]["positions"]) == 2)
    check("discovery: domain found by homepage name match, unknown company gives None", cd.find_domain("Zentech Solutions Pvt Ltd", fake) == "zentechsolutions.com" and cd.find_domain("Ghost Corp", fake) is None)
    pc = cd.extract_public_contacts("zentechsolutions.com", fake)
    check("discovery: only same-domain emails, HR-like first, no image names, phone normalised", pc["emails"][0] == "careers@zentechsolutions.com" and "other@elsewhere.com" not in pc["emails"] and not any(e.endswith(".png") for e in pc["emails"]) and pc["phones"] == ["+919876501234"])
    found, st = cd.discover(jobs_in, 20, fake, pause=0)
    by = {l["COMPANY"]: l for l in found}
    check("discovery: stats count discovered / domain not found", st["discovered"] == 2 and st["domain_not_found"] == 1 and st["companies_without_contact"] == 3)
    check("discovery: public mailbox is generic (not CRM-savable) and score is capped", by["Zentech Solutions Pvt Ltd"]["EMAIL STATUS"] == "Generic" and "generic email" in by["Zentech Solutions Pvt Ltd"]["VERIFICATION"] and all(l["SCORE"] <= 70 for l in found))
    kept, dn = ifl.apply_filter(found)
    check("discovery: leads pass through the intelligent tool, source is the company website", len(kept) == 2 and all(k["SOURCE"] == "Company website" and k["TOOL_SELECTED"] for k in kept))
    check("discovery: phone-only company has no email contact", by["PhoneOnly Co"]["HR EMAIL"] == m.NOT_DISCLOSED and by["PhoneOnly Co"]["HR PHONE"] == "+919123456780")
    # Apollo-by-hand pilot: worksheet + ingest
    import pilot, shutil, tempfile, pandas as _pd
    from pathlib import Path
    _tmp = Path(tempfile.mkdtemp())
    ws = _tmp / "ws.xlsx"
    n = pilot.make_worksheet(jobs_in, 20, ws, find_dom=lambda c: "zentechsolutions.com" if "Zentech" in c else "")
    wdf = _pd.read_excel(ws)
    check("pilot worksheet: unique companies without HR contact, domain filled when known", n == 3 and list(wdf["Company"])[0] == "Zentech Solutions Pvt Ltd" and wdf.loc[0, "Company Domain"] == "zentechsolutions.com" and wdf.loc[0, "Open Positions"] == 2)
    hr_copy = _tmp / "hr.xlsx"
    shutil.copy(m.HR_EXCEL_FILE, hr_copy)
    base = _pd.read_excel(hr_copy)
    known = next(str(e) for e in base["HR Email"] if isinstance(e, str) and "@" in e)
    filled = _pd.DataFrame([
        {"Company": "Zentech Solutions", "HR Name": "Priya Sharma", "HR Title": "Talent Acquisition", "HR Email": "priya.sharma@gmail.com", "Mobile NO:": "9123456780", "Apollo Verified": "Yes", "Job Title": "Python Dev"},
        {"Company": "Beta Labs", "HR Name": "Ravi K", "HR Email": "ravi.k@betalabs.com", "Mobile NO:": "9123456781", "Apollo Verified": "", "Job Title": "Dev"},
        {"Company": "Gamma Corp", "HR Email": "hr@gammacorp.com", "Apollo Verified": "Yes", "Job Title": "Dev"},
        {"Company": "Delta Inc", "HR Name": "Dee", "HR Email": known, "Mobile NO:": "9123456782", "Apollo Verified": "Yes", "Job Title": "Dev"},
        {"Company": "Empty Co"},
    ])
    sheet = _tmp / "filled.xlsx"
    filled.to_excel(sheet, index=False)
    dry = pilot.ingest_sheet(sheet, hr_copy, dry_run=True)
    check("pilot ingest dry-run changes nothing", len(_pd.read_excel(hr_copy)) == len(base) and len(dry["added"]) == 1)
    rep = pilot.ingest_sheet(sheet, hr_copy)
    after = _pd.read_excel(hr_copy)
    check("pilot ingest: only the verified individual email is added to the HR file", rep["rows"] == 4 and [a[0] for a in rep["added"]] == ["Zentech Solutions"] and len(after) == len(base) + 1 and "priya.sharma@gmail.com" in set(after["HR Email"]))
    check("pilot ingest: unverified-email row keeps only its phone -> follow-up list, not the HR file", [p["Company"] for p in rep["phone_only"]] == ["Beta Labs"] and "ravi.k@betalabs.com" not in set(after["HR Email"].astype(str)) and Path(rep["followup_file"]).exists())
    reasons = dict(rep["rejected"])
    check("pilot ingest: generic mailbox and duplicate email are rejected with a reason", "generic" in reasons.get("Gamma Corp", "") or "no valid" in reasons.get("Gamma Corp", ""))
    check("pilot ingest: duplicate email already in the HR file is not added twice", "duplicate" in reasons.get("Delta Inc", "") and len(after) == len(base) + 1)
    check("pilot: added contact is found by the scraper's HR lookup", m.load_existing_hr_data(str(hr_copy))["by_company"].get(m.normalize_company("Zentech Solutions"), {}).get("HR EMAIL") == "priya.sharma@gmail.com")
    r = c.post("/discover", json={"query": " "})
    check("API /discover rejects an empty query", r.status_code == 400)
    # both engines: Serper (master_job_army.py) is kept next to the LinkedIn engine
    import types
    fake = types.ModuleType("master_job_army")
    fake.run_master_job_army = lambda **kw: [{"COMPANY": "Zenith Corp", "JOB TITLE": "Python Dev", "SOURCE": "Naukri",
                                              "JOB URL": "https://naukri.com/j/1", "SCORE": 70, "VERIFICATION": "Unverified",
                                              "HR CONTACT": "Email: Rina.Shah@zenithcorp.com | Phone: 98221 45678"}]
    sys.modules["master_job_army"] = fake
    main.run_master_job_army = lambda **kw: []
    old_key = os.environ.pop("SERPER_API_KEY", None)
    main.SCRAPER_ENGINE = "serper"
    res, note = main.smart_search(Req("python developer"))
    check("engine=serper without SERPER_API_KEY explains the missing key", res == [] and "SERPER_API_KEY" in note)
    os.environ["SERPER_API_KEY"] = "test"
    adapted = main.serper_search(Req("python developer"))
    check("serper engine: HR CONTACT is split into HR EMAIL / HR PHONE", adapted[0]["HR EMAIL"] == "rina.shah@zenithcorp.com" and adapted[0]["HR PHONE"].endswith("9822145678"))
    main.SCRAPER_ENGINE = "both"
    res, note = main.smart_search(Req("python developer"))
    check("engine=both: LinkedIn empty -> Serper leads go through the intelligent tool", len(res) == 1 and res[0]["COMPANY"] == "Zenith Corp" and res[0]["TOOL_SELECTED"] is True)
    main.SCRAPER_ENGINE = "linkedin"
    res, note = main.smart_search(Req("python developer"))
    check("engine=linkedin (default) never calls Serper", all(x.get("COMPANY") != "Zenith Corp" for x in res))
    os.environ.pop("SERPER_API_KEY", None)
    if old_key:
        os.environ["SERPER_API_KEY"] = old_key
    del sys.modules["master_job_army"]
    # automatic discovery (free sources): LinkedIn jobs + company websites, merged and screened by the tool
    jobs_li = [{"COMPANY": "Alpha Soft", "JOB TITLE": "Dev", "JOB URL": "https://l/1", "HR NAME": "Meera Rao", "HR EMAIL": "meera.rao@alphasoft.com",
                "HR PHONE": "Not Disclosed", "HR CONTACT": "meera.rao@alphasoft.com", "SOURCE": "LinkedIn"},
               {"COMPANY": "Beta Labs", "JOB TITLE": "Dev", "JOB URL": "https://l/2", "HR NAME": "Not Disclosed", "HR EMAIL": "Not Disclosed",
                "HR PHONE": "Not Disclosed", "HR CONTACT": "Not Disclosed", "SOURCE": "LinkedIn"}]
    site_lead = {"COMPANY": "Beta Labs", "JOB TITLE": "Dev", "JOB URL": "https://l/2", "HR NAME": "Not Disclosed", "HR EMAIL": "hiring.lead@betalabs.com",
                 "HR PHONE": "+919822145678", "HR CONTACT": "hiring.lead@betalabs.com", "SOURCE": "Company website"}
    seen_args = {}
    def fake_li(**kw):
        seen_args.update(kw)
        return jobs_li
    main.run_master_job_army = fake_li
    main.discover = lambda leads, n: ([site_lead], {"companies_without_contact": 1, "discovered": 1, "domain_not_found": 0, "nothing_public": 0})
    main.SCRAPER_ENGINE = "linkedin"
    r_disc = Req("*", "discover")
    res, note = main.smart_search(r_disc)
    check("discover: empty query uses the default keywords + location", seen_args.get("search_query") == main.DEFAULT_DISCOVERY_QUERY and seen_args.get("location") == main.DEFAULT_DISCOVERY_LOCATION)
    check("discover: LinkedIn HR-matched lead and the company-website lead are both returned, all tool-selected", {x["COMPANY"] for x in res} == {"Alpha Soft", "Beta Labs"} and all(x["TOOL_SELECTED"] for x in res))
    check("discover: note explains jobs read and websites used", "jobs read" in note and "company websites" in note)
    def li_down(**kw):
        raise RuntimeError("HTTP 429")
    main.run_master_job_army = li_down
    res, note = main.smart_search(Req("python", "discover"))
    check("discover: LinkedIn down -> company-website leads still returned, problem noted", len(res) == 1 and "429" in note)
    jid = c.post("/scrape", json={"query": "*", "search_type": "discover"}).status_code
    check("API accepts search_type 'discover'", jid == 200)
except ImportError as e:
    print("[SKIP] FastAPI tests:", e)

print(f"\nRESULT: {passed}/{total} passed; {total - passed} failed")
sys.exit(0 if passed == total else 1)
