"""Offline tests for the scraper (no internet, no browser). Run: python test_scraper.py"""
import os
import json
os.environ.setdefault("ENABLE_OSM", "0")
os.environ["ACCEPT_HR_MAILBOX"] = "0"  # the strict team rule is the default; the switch is tested below  # tests never touch the network
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
    main.discover = lambda leads, n=None, **kw: ([site_lead], {"companies_without_contact": 1, "discovered": 1, "domain_not_found": 0, "nothing_public": 0})
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
    # optional Apollo API: off without a key, credit-guarded and verified-only with one
    import apollo_client as ap
    os.environ.pop("APOLLO_API_KEY", None)
    check("apollo: disabled without APOLLO_API_KEY", not ap.apollo_enabled() and ap.find_hr_contacts("X", "x.com") == [])
    os.environ["APOLLO_API_KEY"] = "test-key"
    calls = []
    def fake_post(path, params, headers):
        calls.append(path)
        if path.endswith("api_search"):
            return {"people": [{"id": "p1", "title": "Talent Acquisition Lead", "has_email": True},
                               {"id": "p2", "title": "HR Manager", "has_email": True},
                               {"id": "p3", "title": "Recruiter", "has_email": True}]}
        pid = params["id"]
        return {"person": {"p1": {"first_name": "Asha", "last_name": "Rao", "title": "Talent Acquisition Lead", "email": "Asha.Rao@alphasoft.com", "email_status": "verified", "linkedin_url": "https://linkedin.com/in/asha"},
                           "p2": {"first_name": "Dev", "last_name": "K", "email": "dev@alphasoft.com", "email_status": "unverified"},
                           "p3": {"first_name": "Zed", "last_name": "L", "email": "zed@alphasoft.com", "email_status": "verified"}}[pid]}
    got = ap.find_hr_contacts("Alpha Soft", "alphasoft.com", [10], post=fake_post)
    check("apollo: only verified emails are kept, lowercased, lead has the shared keys", [g["HR EMAIL"] for g in got] == ["asha.rao@alphasoft.com", "zed@alphasoft.com"] and got[0]["SOURCE"] == "Apollo (API)" and got[0]["HR PHONE"] == "Not Disclosed")
    calls.clear()
    ap.find_hr_contacts("Alpha Soft", "alphasoft.com", [1], post=fake_post)
    check("apollo: credit guard stops enrichment when the budget is used up", calls.count("/people/match") == 1)
    main.apollo_enabled = lambda: True
    main.find_domain = lambda company: "alphasoft.com"
    main.find_hr_contacts = lambda company, domain, budget=None: [{"COMPANY": company, "HR NAME": "Asha Rao", "HR TITLE": "TA Lead", "HR EMAIL": "asha.rao@alphasoft.com",
                                                                "HR PHONE": "Not Disclosed", "HR CONTACT": "asha.rao@alphasoft.com", "SOURCE": "Apollo (API)"}]
    main.run_master_job_army = lambda **kw: [dict(jobs_li[1])]
    main.discover = lambda leads, n=None, **kw: ([], {"companies_without_contact": 1, "discovered": 0, "domain_not_found": 0, "nothing_public": 1})
    res, note = main.smart_search(Req("*", "discover"))
    check("discover + Apollo key: Apollo-verified HR lead reaches the list through the tool", len(res) == 1 and res[0]["HR EMAIL"] == "asha.rao@alphasoft.com" and res[0]["TOOL_SELECTED"] and "Apollo" in note)
    os.environ.pop("APOLLO_API_KEY", None)
except ImportError as e:
    print("[SKIP] FastAPI tests:", e)


# ---- time budget + parallel detail fetch -------------------------------------
import threading  # noqa: E402
import osm_discovery as osm  # noqa: E402
slow_calls = []
def slow_fetch(url):
    if "jobPosting" in url or "jobs-guest/jobs/api/jobPosting" in url:
        slow_calls.append(url)
        time.sleep(0.6)
    return fake_fetch(url)
t0 = time.monotonic()
budget_leads = m.run_master_job_army("python developer", limit=None, fetch=slow_fetch, hr_index={}, use_browser_fallback=False,
                                     pause=0, time_budget=1.0, workers=4)
elapsed = time.monotonic() - t0
check("time budget: the search returns quickly and still gives leads from the cards", elapsed < 8 and len(budget_leads) >= 1)
t0 = time.monotonic()
m.run_master_job_army("python developer", limit=None, fetch=slow_fetch, hr_index={}, use_browser_fallback=False, pause=0, time_budget=0.01, workers=4)
check("time budget: an exhausted budget skips the detail pages instead of waiting", time.monotonic() - t0 < 6)

# ---- OpenStreetMap (free map source) ------------------------------------------
payload = {"elements": [
    {"tags": {"name": "Alpha Soft", "office": "it", "website": "https://alphasoft.com", "phone": "+91 40 1234 5678", "addr:city": "Hyderabad"}},
    {"tags": {"name": "alpha soft"}},
    {"tags": {"office": "it"}},
    {"tags": {"name": "Beta Labs", "contact:email": "hello@betalabs.in"}},
]}
parsed = osm.parse_elements(payload)
check("osm: elements are parsed, unnamed and duplicate names are dropped", [c["company"] for c in parsed] == ["Alpha Soft", "Beta Labs"] and parsed[0]["website"] == "https://alphasoft.com" and parsed[1]["email"] == "hello@betalabs.in")
os.environ["ENABLE_OSM"] = "1"
got = osm.osm_companies("software developer", "Hyderabad", 10, post=lambda url, q: json.dumps(payload))
check("osm: companies come back through an injected poster, query uses the city", len(got) == 2 and "Hyderabad" in osm.build_query("software developer", "Hyderabad", 10))
check("osm: a network error returns [] (fail-soft)", osm.osm_companies("x", "y", 5, post=lambda url, q: (_ for _ in ()).throw(OSError("down"))) == [])
os.environ["ENABLE_OSM"] = "0"
check("osm: ENABLE_OSM=0 turns it off", osm.osm_companies("software", "Pune", 5, post=lambda url, q: json.dumps(payload)) == [])
rows = osm.as_job_rows(parsed, "software developer", "Hyderabad")
check("osm: rows look like job leads (company, title, no HR contact)", rows[0]["COMPANY"] == "Alpha Soft" and rows[0]["HR CONTACT"] == "Not disclosed")

# ---- Upload ingestion (Leads page: Upload Excel / Run Scraper) -------------------
import base64 as _b64
import ingest_upload as iu

csv_text = ("Name,Email,Mobile,Company,Job Title\n"
            "Asha Rao,asha.rao@acmetech.in,9876501234,Acme Tech,HR Manager\n"
            "Asha Again,asha.rao@acmetech.in,,Acme Tech,HR\n"
            "Careers Desk,careers@acmetech.in,,Acme Tech,\n"
            "Temp Guy,temp@mailinator.com,,Temp Co,\n"
            "Bad Mail,not-an-email,9123456780,Beta,HR\n"
            "Phone Only,,9812345670,Gamma,HR\n"
            "Dummy,,12345,Delta,HR\n"
            ",,,,\n")
rep = iu.run_ingest("leads.csv", csv_text.encode())
st = {r["name"]: r for r in rep["rows"]}
sm = rep["summary"]
check("ingest: total counts only non-blank rows", sm["total"] == 7)
check("ingest: valid individual email is qualified with a score", st["Asha Rao"]["status"] == "qualified" and st["Asha Rao"]["score"] > 0)
check("ingest: same email twice is a duplicate with the row number", st["Asha Again"]["status"] == "duplicate" and "row 2" in st["Asha Again"]["reasons"][0])
check("ingest: generic and disposable emails are rejected with reasons", st["Careers Desk"]["status"] == "rejected" and "Generic" in st["Careers Desk"]["reasons"][0] and st["Temp Guy"]["status"] == "rejected" and "Disposable" in st["Temp Guy"]["reasons"][0])
check("ingest: bad email with a valid mobile is phone-only, never qualified", st["Bad Mail"]["status"] == "phone_only")
check("ingest: no email + valid mobile is phone-only", st["Phone Only"]["status"] == "phone_only")
check("ingest: dummy number is rejected and counted as invalid phone", st["Dummy"]["status"] == "rejected" and sm["invalid_phone"] >= 1)
check("ingest: invalid emails are counted", sm["invalid_email"] >= 2)
check("ingest: counts add up (no invented numbers)", sm["qualified"] + sm["phone_only"] + sm["rejected"] + sm["duplicates"] == sm["total"])

def ingest_error(name, data):
    try:
        iu.run_ingest(name, data)
    except iu.UploadError as e:
        return e.code
    return None
check("ingest: wrong file type", ingest_error("leads.pdf", b"x") == "invalid_format")
check("ingest: empty file", ingest_error("leads.csv", b"") == "empty_file")
check("ingest: header only", ingest_error("leads.csv", b"Name,Email\n") == "empty_file")
check("ingest: missing email/phone columns", ingest_error("leads.csv", b"Foo,Bar\n1,2\n") == "missing_columns")
check("ingest: corrupted xlsx", ingest_error("leads.xlsx", b"not a zip") == "unreadable")
import pandas as _pd, io as _io
buf = _io.BytesIO()
_pd.DataFrame({"HR Name": ["Ravi K"], "HR Email": ["ravi.k@zenithsoft.in"], "Mobile NO:": ["9876501234"], "Apollo Verified": ["Yes"]}).to_excel(buf, index=False)
x = iu.run_ingest("sheet.xlsx", buf.getvalue())
check("ingest: .xlsx with the pilot worksheet headers works", x["summary"]["qualified"] == 1)
buf = _io.BytesIO()
_pd.DataFrame({"HR Name": ["Ravi K"], "HR Email": ["ravi.k@zenithsoft.in"], "Apollo Verified": [""]}).to_excel(buf, index=False)
check("ingest: Apollo column present but not Yes is rejected", iu.run_ingest("sheet.xlsx", buf.getvalue())["summary"]["rejected"] == 1)

try:
    from fastapi.testclient import TestClient
    import main as _main
    client = TestClient(_main.app)
    r = client.post("/ingest", json={"filename": "leads.csv", "content_base64": _b64.b64encode(csv_text.encode()).decode()})
    jid = r.json().get("job_id")
    got = client.get(f"/ingest/{jid}").json()
    check("api: /ingest starts a job and /ingest/{id} returns a finished report", r.status_code == 200 and got["status"] == "done" and got["summary"]["qualified"] == 1 and got["processed"] == got["total"] == 7)
    bad = client.post("/ingest", json={"filename": "leads.csv", "content_base64": "###"})
    check("api: invalid base64 is a 400", bad.status_code == 400)
    jid2 = client.post("/ingest", json={"filename": "a.pdf", "content_base64": _b64.b64encode(b"x").decode()}).json()["job_id"]
    e = client.get(f"/ingest/{jid2}").json()
    check("api: file errors come back as status=error with a code", e["status"] == "error" and e["error_code"] == "invalid_format")
    check("api: unknown job is 404", client.get("/ingest/nope").status_code == 404)
except ImportError as _e:
    print(f"SKIP api tests: {_e}")

# ---- Crawler: page parser, HR-mailbox switch, parallel discovery ------------------
import page_contacts as pcn
import lead_validation as lv
import company_discovery as cd2

def _cf(email, key=0x42):
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)

page = f'''<div><h3>Priya Sharma</h3><p>Head of Talent Acquisition</p><a href="mailto:priya.sharma@zentech.in">Email</a></div>
<a data-cfemail="{_cf("hr@zentech.in")}">[email protected]</a>
<p>Write: rohan.k [at] zentech [dot] in</p><p>Sales: sales&#64;zentech.in</p><p>Partner: x@other.com logo@zentech.in.png</p>
<script type="application/ld+json">{{"employee":{{"@type":"Person","name":"Anita Rao","jobTitle":"HR Manager","email":"anita.rao@zentech.in"}}}}</script>
<a href="/our-team">Team</a><a href="/blog">Blog</a><a href="https://other.com/contact">x</a>'''
got = {c["email"]: c for c in pcn.extract_contacts(page, "zentech.in")}
check("parser: finds mailto, Cloudflare-protected, [at]/[dot] and &#64; emails on the company domain only",
      {"priya.sharma@zentech.in", "hr@zentech.in", "rohan.k@zentech.in", "sales@zentech.in", "anita.rao@zentech.in"} == set(got))
check("parser: no partner domain or image file names", not any(e.endswith(".png") or e.endswith("other.com") for e in got))
check("parser: name and title printed next to an email are attached (JSON-LD and page text)",
      got["priya.sharma@zentech.in"]["name"] == "Priya Sharma" and "Talent Acquisition" in got["priya.sharma@zentech.in"]["title"] and got["anita.rao@zentech.in"]["title"] == "HR Manager")
check("parser: one person's name is never given to another address", got["rohan.k@zentech.in"]["name"] == "" and got["hr@zentech.in"]["name"] == "")
check("parser: internal links keep only same-site careers/team/contact pages", pcn.internal_links(page, "https://www.zentech.in/") == ["https://www.zentech.in/our-team"])

os.environ["ACCEPT_HR_MAILBOX"] = "1"
check("HR-mailbox switch ON: hr@/careers@/recruitment@ are valid, info@/support@/sales@ stay generic",
      [lv.validate_email(x) for x in ("hr@a.com", "careers@a.com", "recruitment@a.com", "hr.india@a.com", "info@a.com", "support@a.com", "sales@a.com")] == ["Valid", "Valid", "Valid", "Valid", "Generic", "Generic", "Generic"])
check("HR-mailbox switch ON: email kind and label", lv.email_kind("careers@a.com") == "hr_mailbox" and lv.email_kind("a.b@a.com") == "personal" and lv.email_kind("info@a.com") == "generic" and lv.verification_label("careers@a.com", "Valid", False) == "Unverified (HR mailbox)")
os.environ["ACCEPT_HR_MAILBOX"] = "0"
check("HR-mailbox switch OFF (default): hr@ is generic again", lv.validate_email("hr@a.com") == "Generic" and lv.verification_label("hr@a.com", "Generic", False) == "Unverified (generic email)")

# a site whose team page is not on a standard path: found by following the home page links
site = {
    "https://www.deepco.in": '<title>Deepco</title><a href="/meet-the-people">People</a><a href="/contact">Contact</a>',
    "https://www.deepco.in/meet-the-people": '<h4>Kavya Menon</h4><p>HR Manager</p><a href="mailto:kavya.menon@deepco.in">mail</a>',
    "https://www.deepco.in/contact": "Write to careers@deepco.in or +91 98220 11223",
}
fk = lambda u: site.get(u, "")
pcs = cd2.extract_public_contacts("deepco.in", fk)
check("crawler: follows home-page links to a non-standard team page; named person ranks first", pcs["emails"][0] == "kavya.menon@deepco.in" and pcs["people"][0]["name"] == "Kavya Menon")
lead_d, why = cd2.discover_company({"company": "Deepco", "positions": ["Dev"], "locations": ["Pune"], "job_urls": ["u"]}, fk)
check("crawler: lead gets the person's name, title and a personal email (valid, not generic)", lead_d["HR NAME"] == "Kavya Menon" and lead_d["HR TITLE"] == "HR Manager" and lead_d["EMAIL STATUS"] == "Valid" and lead_d["EMAIL KIND"] == "personal")
os.environ["ACCEPT_HR_MAILBOX"] = "1"
site2 = {"https://www.solo.in": "<title>Solo</title>", "https://www.solo.in/careers": "Mail jobs@solo.in"}
lead_h, _ = cd2.discover_company({"company": "Solo", "positions": [], "locations": [], "job_urls": []}, lambda u: site2.get(u, ""))
check("crawler + switch ON: a published HR mailbox becomes a valid, labelled lead", lead_h["EMAIL STATUS"] == "Valid" and lead_h["EMAIL KIND"] == "hr_mailbox" and "HR mailbox" in lead_h["VERIFICATION"] and lead_h["SCORE"] <= 70)
os.environ["ACCEPT_HR_MAILBOX"] = "0"

import time as _t, threading as _th
many = [{"COMPANY": f"Parallel Co {i}", "JOB TITLE": "Dev", "HR CONTACT": lv.NOT_DISCLOSED} for i in range(12)]
slow_calls = []
def slow_fetch(u):
    _t.sleep(0.05)
    slow_calls.append(_th.current_thread().name)
    host = u.split("/")[2].replace("www.", "")
    if u.count("/") == 2 and "parallel" in host:
        return f"<title>{host}</title>"
    return f"mail hello.person{host.split('.')[0][-2:]}@{host}" if u.endswith("/contact") else ""
t0 = _t.time()
out_p, st_p = cd2.discover(many, 12, slow_fetch, pause=0, workers=6)
check("crawler: companies are crawled in parallel (several threads used)", len(set(slow_calls)) > 1 and st_p["companies_without_contact"] == 12)
out_b, st_b = cd2.discover(many, 12, slow_fetch, pause=0, workers=1, time_budget=0.0001)
check("crawler: time budget stops the run and reports companies not reached", st_b["not_reached"] > 0 and st_b["discovered"] < 12)

# ---- Confidence ----------------------------------------------------------------
check("confidence: personal email + name = high", lv.lead_confidence({"HR EMAIL": "meera.rao@alpha.com", "HR NAME": "Meera Rao"})[0] == "high")
check("confidence: personal email, no name = medium", lv.lead_confidence({"HR EMAIL": "meera.rao@alpha.com", "HR NAME": "Not Disclosed"})[0] == "medium")
check("confidence: matched by company only is capped at medium", lv.lead_confidence({"HR EMAIL": "meera.rao@alpha.com", "HR NAME": "Meera Rao", "HR MATCH": "company"})[0] == "medium")
check("confidence: shared mailbox with a valid mobile = low; nothing = none", lv.lead_confidence({"HR EMAIL": "support@a.com", "HR PHONE": "9876501234"})[0] == "low" and lv.lead_confidence({"HR EMAIL": "Not Disclosed"})[0] == "none")
os.environ["ACCEPT_HR_MAILBOX"] = "1"
check("confidence: HR mailbox = medium only when the switch is on", lv.lead_confidence({"HR EMAIL": "careers@a.com"})[0] == "medium")
os.environ["ACCEPT_HR_MAILBOX"] = "0"
check("confidence: HR mailbox with the switch off is not usable", lv.lead_confidence({"HR EMAIL": "careers@a.com"})[0] == "none")
_r = iu.run_ingest("l.csv", b"Name,Email,Mobile\nAsha Rao,asha.rao@acmetech.in,\nNo Mail,,9876501234\nTemp,temp@mailinator.com,\n")
_c = {x["name"]: x["confidence"] for x in _r["rows"]}
check("ingest rows carry a confidence", _c["Asha Rao"] == "high" and _c["No Mail"] == "low" and _c["Temp"] == "none")

print(f"\nRESULT: {passed}/{total} passed; {total - passed} failed")
sys.exit(0 if passed == total else 1)
