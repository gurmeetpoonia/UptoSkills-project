#!/usr/bin/env python3
"""Offline deterministic regression tests for the Termux Lead Intelligence app."""
import os, sys, csv, io, sqlite3, tempfile, zipfile
from xml.etree.ElementTree import Element, SubElement, tostring
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app

passed = 0
total = 0
def check(name, condition):
    global passed, total
    total += 1
    if condition:
        passed += 1; print('[PASS]', name)
    else:
        print('[FAIL]', name)

# Use a fresh temporary database so tests never modify the user's real data.
tmp = tempfile.mkdtemp(prefix='leadintel-tests-')
app.DB_PATH = os.path.join(tmp, 'test.db')
app.LOG_PATH = os.path.join(tmp, 'test.log')
app.init_database()
# Avoid external DNS/network dependencies while testing qualification logic.
original_validate = app.EmailValidator.validate
app.EmailValidator.validate = classmethod(lambda cls, value, check_dns=True: (bool(str(value or '').strip()), 'Test validation' if str(value or '').strip() else 'Email missing.', False, False, str(value or '').strip().lower()))
original_research = app.research_company_online
app.research_company_online = lambda *args: {'status':'Research unavailable','industry':'Unverified','tech_stack':[],'has_careers':False,'summary':'No internet research in offline test.','evidence':[],'sources':[],'retrieved_at':'2026-11-03T00:00:00+00:00'}

for header, expected in [('HR Email','email'),('Mobile NO:','phone'),('mobile_no','phone'),('Company LinkedIn','company_linkedin'),('Job Title','job_title')]:
    check('Header mapping '+header, app.map_column_name(header) == expected)
check('Export validation columns are not mistaken for contacts', app.map_column_name('Email_Status') is None and app.map_column_name('Phone_Status') is None and app.map_column_name('Company_Research_Status') is None)

# CSV and XLSX import smoke tests
csv_bytes = b'HR Email,Mobile NO:,Company\na@example.com,9876543210,Example\n'
csv_rows = app.PurePythonFileParser.parse_file(csv_bytes, 'test.csv')
check('CSV import and exact contact headers', len(csv_rows)==1 and csv_rows[0]['HR Email']=='a@example.com' and csv_rows[0]['Mobile NO:']=='9876543210')
# Large CSV must retain every row; preview limiting happens only in the UI.
large_csv = ('HR Email,Mobile NO:,Company\n' + ''.join(f'user{i}@example.com,9876543210,Company {i}\n' for i in range(150))).encode('utf-8')
large_rows = app.PurePythonFileParser.parse_file(large_csv, 'large.csv')
check('CSV parser retains all 150 rows', len(large_rows) == 150)
source_text = open(app.__file__, encoding='utf-8').read()
check('No test dataset/button/API is shipped', 'loadSampleData' not in app.EMBEDDED_HTML_DASHBOARD and 'Load Test Scraped Dataset' not in app.EMBEDDED_HTML_DASHBOARD and 'SAMPLE_EXACT_SCRAPED_ROWS' not in source_text and '/api/load-sample' not in source_text)
check('File selection does not depend on implicit event.target', 'handleFileSelect(event)' not in app.EMBEDDED_HTML_DASHBOARD and 'reader.result' in app.EMBEDDED_HTML_DASHBOARD and 'addEventListener(\'change\'' in app.EMBEDDED_HTML_DASHBOARD)
check('Tab switching does not depend on implicit global event', "event.target.classList.add('active')" not in app.EMBEDDED_HTML_DASHBOARD and 'function switchTab(tabId, triggerEl = null)' in app.EMBEDDED_HTML_DASHBOARD)
check('Score reason preview is visible in qualified-lead table', 'scoreReasonPreview(lead)' in app.EMBEDDED_HTML_DASHBOARD and 'Full score & internet evidence' in app.EMBEDDED_HTML_DASHBOARD)
check('Dashboard restores latest saved run after refresh', "fetch('/api/latest')" in app.EMBEDDED_HTML_DASHBOARD and 'if path == "/api/latest"' in open(app.__file__, encoding='utf-8').read())
source_text = open(app.__file__, encoding='utf-8').read()
check('Preview endpoint sends all records separately from five-row preview', '"records": records,' in source_text and '"preview_records": records[:5]' in source_text)
check('SQLite import does not wait for online research', 'process_leads_dataset(records, filename, min_score=min_score, enable_research=False)' in source_text)
check('Import UI restores button and reports server errors', '.finally(() => {' in app.EMBEDDED_HTML_DASHBOARD and 'if (!r.ok || result.error)' in app.EMBEDDED_HTML_DASHBOARD)

# Minimal valid XLSX using inlineStr cells (the common openpyxl output format).
ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
root=Element('{%s}worksheet'%ns); data=SubElement(root,'{%s}sheetData'%ns)
for r, vals in enumerate([['HR Email','Mobile NO:','Company'],['b@example.com','9876543210','Inline Co']],1):
    row=SubElement(data,'{%s}row'%ns,{'r':str(r)})
    for col, val in zip(['A','B','C'], vals):
        cell=SubElement(row,'{%s}c'%ns,{'r':f'{col}{r}','t':'inlineStr'})
        inline=SubElement(cell,'{%s}is'%ns); t=SubElement(inline,'{%s}t'%ns); t.text=val
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr('xl/worksheets/sheet1.xml',tostring(root,encoding='unicode'))
xlsx_rows=app.PurePythonFileParser.parse_file(buf.getvalue(),'inline.xlsx')
check('XLSX inline-string import', len(xlsx_rows)==1 and xlsx_rows[0].get('HR Email')=='b@example.com')

# Presence-only qualification matrix, including invalid-but-present contact values.
records=[
 {'Company':'Both','Job Title':'Role A','HR Email':'valid@example.com','Mobile NO:':'9876512345'},
 {'Company':'Email only','Job Title':'Role B','HR Email':'valid2@example.com','Mobile NO:':''},
 {'Company':'Phone only','Job Title':'Role C','HR Email':'','Mobile NO:':'9876501234'},
 {'Company':'Neither','Job Title':'Role D','HR Email':'','Mobile NO:':''},
 {'Company':'Invalid present','Job Title':'Role E','HR Email':'bad-email','Mobile NO:':''},
]
res=app.process_leads_dataset(records,'qualification.csv',min_score=0.99,enable_research=False)
check('Presence rule qualifies both/email-only/phone-only/invalid-present',res['qualified_count']==4)
check('Only both-missing record rejected',res['rejected_count']==1 and res['rejected_leads'][0]['company']=='Neither')
check('Score cutoff does not disqualify leads',len(res['qualified_leads'])==4)
check('Every qualified lead has factor-by-factor score explanation', all(bool(x.get('score_explanation')) and len(__import__('json').loads(x['score_explanation'])) >= 7 for x in res['qualified_leads']))
check('Every qualified lead records research evidence fields', all('research_evidence' in x and 'research_sources' in x for x in res['qualified_leads']))
check('Rejected record reason is explicit',res['rejected_leads'][0]['rejection_reason']=='Both email and phone are missing')
conn=sqlite3.connect(app.DB_PATH)
rows=conn.execute('SELECT qualification_status, COUNT(*) FROM leads WHERE run_id=? GROUP BY qualification_status',(res['run_id'],)).fetchall()
conn.close()
check('SQLite stores qualification status separately',dict(rows).get('qualified')==4 and dict(rows).get('rejected')==1)
conn=sqlite3.connect(app.DB_PATH)
lead_cols={r[1] for r in conn.execute('PRAGMA table_info(leads)').fetchall()}
saved=conn.execute('SELECT score_explanation,research_evidence,research_sources FROM leads WHERE run_id=? AND qualification_status="qualified" LIMIT 1',(res['run_id'],)).fetchone()
conn.close()
check('SQLite schema persists explanations and evidence', {'score_explanation','research_evidence','research_sources','research_retrieved_at'}.issubset(lead_cols) and saved and bool(saved[0]))

# Duplicate should be distinct from rejected; matching contact email.
dups=[{'Company':'DupCo','Job Title':'Analyst','HR Email':'same@example.com','Mobile NO:':''},
      {'Company':'Other','Job Title':'Analyst II','HR Email':'same@example.com','Mobile NO:':''}]
r2=app.process_leads_dataset(dups,'duplicates.csv',enable_research=False)
check('Duplicate classification is separate from score/rejection',r2['duplicates_count']==1 and r2['qualified_count']==1)

# Public search result parser: ensure title, snippet and source URL are captured.
sample_search_html = '<a class="result__a" href="https://example.com/about">Example Company About</a><a class="result__snippet">Official company overview</a>'
parsed_hits = app._extract_search_results(sample_search_html)
check('Web research parser captures title and source URL', len(parsed_hits)==1 and parsed_hits[0]['url']=='https://example.com/about' and 'Example Company' in parsed_hits[0]['title'])

# Score explanation must explicitly say when there is no research support.
score_input={'company':'No Evidence Co','job_title':'Analyst','email':'a@b.com','email_valid':1,'email_status':'test','phone':'','phone_valid':0,'company_status':'Research unavailable','research_evidence':[]}
sc, bd, tier, why = app.score_lead(score_input)
check('No public research evidence receives zero evidence points', bd['public_web_evidence']==0 and 'no fetched source page' in why['public_web_evidence'])
# A search snippet or a reachable website alone must not inflate research points.
snippet_only={'company':'No Evidence Co','email':'a@b.com','email_valid':1,'company_status':'Website reachable (HTTP 200)','research_evidence':[{'kind':'search_result','title':'No Evidence Co official','url':'https://example.com','snippet':'No Evidence Co profile','verified_for_company':False,'evidence_level':'search_snippet_only'}]}
_, snippet_bd, _, _ = app.score_lead(snippet_only)
check('Search snippets and HTTP 200 alone award no research points', snippet_bd['public_web_evidence']==0 and snippet_bd['company_profile_evidence']==0 and snippet_bd['company_web_presence']==0.0)



# Research evidence must be carried through the pipeline into score and stored result.
app.research_company_online = lambda *args: {
    'status':'Public web search results found','industry':'Unverified','tech_stack':[],
    'has_careers':False,'summary':'Search found the Example Company official profile.',
    'evidence':[{'kind':'verified_company_profile','title':'Example Company official website','url':'https://example.org/about',
                 'snippet':'Example Company builds products.','retrieved_at':'2026-11-03T00:00:00+00:00','verified_for_company':True,'evidence_level':'fetched_page_company_match'},
                {'kind':'verified_job_relevance','title':'Example Company Analyst roles','url':'https://jobs.example.org/analyst','snippet':'Analyst role at Example Company.','retrieved_at':'2026-11-03T00:00:00+00:00','verified_for_company':True,'evidence_level':'fetched_page_company_match'}],
    'sources':['https://example.org/about'],'retrieved_at':'2026-11-03T00:00:00+00:00'
}
r_research=app.process_leads_dataset([{'Company':'Example Company','Job Title':'Analyst','HR Email':'lead@example.org','Company Domain':'example.org'}],
                                    'research-evidence.csv',enable_research=True)
research_lead=r_research['qualified_leads'][0]
research_breakdown=__import__('json').loads(research_lead['score_breakdown'])
research_explanation=__import__('json').loads(research_lead['score_explanation'])
research_items=__import__('json').loads(research_lead['research_evidence'])
check('Research findings are passed into the scoring pipeline', research_breakdown['public_web_evidence'] > 0 and research_breakdown['company_profile_evidence'] > 0 and research_breakdown['job_relevance_evidence'] > 0 and len(research_items)==2)
check('Score explanation cites the internet evidence contribution', 'fetched page' in research_explanation['public_web_evidence'].lower() and 'example.org/about' in research_explanation['company_profile_evidence'])
check('Website HTTP status alone adds zero score', research_breakdown['company_web_presence']==0.0)
check('Research source URL and retrieval timestamp are saved', 'https://example.org/about' in research_lead['research_sources'] and bool(research_lead['research_retrieved_at']))
check('Unverified snippets cannot score even when company name appears', app.score_lead({'company':'Example Company','research_evidence':[{'kind':'search_result','title':'Example Company','url':'https://example.org','verified_for_company':False}]})[1]['company_profile_evidence']==0)
check('Verified evidence points are capped and separately explained', research_breakdown['company_profile_evidence']==0.10 and research_breakdown['job_relevance_evidence']==0.10 and 'company-matched fetched source' in research_explanation['job_relevance_evidence'])
check('Existing leads can be refreshed through a dashboard action', 'function rerunDeepResearch()' in app.EMBEDDED_HTML_DASHBOARD and 'if path == "/api/research-latest"' in open(app.__file__,encoding='utf-8').read())
check('Research runs in a background worker', 'threading.Thread(target=_research_latest_worker' in open(app.__file__,encoding='utf-8').read() and 'if path == "/api/research-status"' in open(app.__file__,encoding='utf-8').read())
check('Dashboard polls research progress and displays errors', "fetch('/api/research-status')" in app.EMBEDDED_HTML_DASHBOARD and 'state.completed' in app.EMBEDDED_HTML_DASHBOARD and 'state.errors' in app.EMBEDDED_HTML_DASHBOARD)
check('Research progress commits each lead separately', "RESEARCH_JOB['completed'] += 1" in open(app.__file__,encoding='utf-8').read())

# Phone format and normalization basic checks
pv=app.PhoneValidator.validate('98765 12345')
check('Indian phone without country code accepted',pv[0] and '+91' in pv[2])

# XLSX export round-trip through the built-in XLSX parser.
xbytes=app.build_xlsx_bytes(['Company','Mobile_NO'], [('Excel Co','+91 98765 43210')])
xrows=app.PurePythonFileParser.parse_file(xbytes,'roundtrip.xlsx')
check('XLSX export creates a readable workbook', len(xrows)==1 and xrows[0]['Company']=='Excel Co' and xrows[0]['Mobile_NO']=='+91 98765 43210')


# ---------------------------------------------------------------------------
# v1.5.0: usable-contact rule, Ready / Needs review / Rejected, duplicates, DNS label
# ---------------------------------------------------------------------------
def mk(**kw):
    base = dict(email='', phone='', company='Acme', hr_name='Jane', job_title='Dev', email_valid=0, email_status='', is_role_based=0,
                is_disposable=0, phone_valid=0, phone_status='')
    base.update(kw); return base
GOOD_MX = 'Valid format and MX found.'
check('Nothing supplied is Rejected', app.classify_lead(mk())[0] == 'Rejected')
check('Invalid email and invalid phone are Rejected (not Qualified)',
      app.classify_lead(mk(email='not-an-email', email_status='Invalid email format.', phone='12345', phone_status='Invalid length (5 digits; expected 7-15)'))[0] == 'Rejected')
check('Rejection reason names the problem',
      'Invalid email format' in app.classify_lead(mk(email='x', email_status='Invalid email format.', phone='1', phone_status='Invalid length'))[1])
check('Disposable email alone is Rejected', app.classify_lead(mk(email='a@mailinator.com', email_valid=1, is_disposable=1, email_status=GOOD_MX))[0] == 'Rejected')
check('Verified email is Ready', app.classify_lead(mk(email='a@acme.com', email_valid=1, email_status=GOOD_MX))[0] == 'Ready')
check('Valid mobile phone alone is Ready', app.classify_lead(mk(phone='9876512345', phone_valid=1, phone_status='Valid Indian Mobile Format (Line activity unconfirmed)'))[0] == 'Ready')
check('Valid phone rescues an invalid email', app.classify_lead(mk(email='bad', email_status='Invalid email format.', phone='9876512345', phone_valid=1, phone_status='Valid Indian Mobile Format'))[0] == 'Ready')
check('Role-based email only is Needs review', app.classify_lead(mk(email='info@acme.com', email_valid=1, is_role_based=1, email_status=GOOD_MX))[0] == 'Needs review')
check('Unverified (DNS unavailable) email only is Needs review', app.classify_lead(mk(email='a@acme.com', email_valid=1, email_status='DNS verification unavailable.'))[0] == 'Needs review')
check('Landline only is Needs review', app.classify_lead(mk(phone='04067522016', phone_valid=1, phone_status='Valid Indian Landline (Hyderabad)'))[0] == 'Needs review')
check('Missing company makes a good contact Needs review', app.classify_lead(mk(company='', email='a@acme.com', email_valid=1, email_status=GOOD_MX))[0] == 'Needs review')
check('Phone duplicate key ignores formatting',
      app.phone_dedupe_key('98765 43210') == app.phone_dedupe_key('+91 9876543210') == app.phone_dedupe_key('09876543210'))

def run(rows):
    return app.process_leads_dataset(rows, 'v150.csv', min_score=0.0, enable_research=False)
r = run([{'Company':'Alpha','Job Title':'Dev','HR Email':'a@alpha.com','Mobile NO:':'98765 12345'},
         {'Company':'Beta','Job Title':'QA','HR Email':'b@beta.com','Mobile NO:':'+91 9876512345'}])
check('Same phone in another format is a duplicate', r['duplicates_count'] == 1 and 'phone' in r['duplicates'][0]['duplicate_reason'].lower())
r = run([{'Company':'Acme','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':'jane@acme.com'},
         {'Company':'Acme','Job Title':'Python Developer','HR Name':'Raj Kumar','HR Email':'raj@acme.com'}])
check('Different HR people at the same company/job are both kept', r['duplicates_count'] == 0 and r['qualified_count'] == 2)
r = run([{'Company':'Acme','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':'jane@acme.com'},
         {'Company':'Acme Corp','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':''  ,'Mobile NO:':''}])
check('A contact-less repeat is Rejected, not hidden as a duplicate', r['duplicates_count'] == 0 and r['rejected_count'] == 1)
r = run([{'Company':'Acme','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':'jane@acme.com'},
         {'Company':'Acme','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':'','Mobile NO:':'9876512345'}])
check('Same posting and same HR person (no conflicting contact) is merged as a duplicate', r['duplicates_count'] == 1)
r = run([{'Company':'Acme','Job Title':'Python Developer','HR Name':'Jane Roe','HR Email':'jane@acme.com'},
         {'Company':'Acme','Job Title':'Data Engineer','HR Name':'Jane Roe','HR Email':'','Mobile NO:':'9876512345'}])
check('Same HR person at the same company is one lead even for another job', r['duplicates_count'] == 1 and 'same hr person' in r['duplicates'][0]['duplicate_reason'].lower())
r = run([{'Company':'Alpha','Job Title':'Dev','HR Email':'a@alpha.com','Mobile NO:':'98765 12345'}])
check('Result carries Ready / Needs review counts', 'ready_count' in r and 'review_count' in r and r['ready_count'] + r['review_count'] == r['qualified_count'])
check('Lead class and reason are saved to the database',
      sqlite3.connect(app.DB_PATH).execute("SELECT lead_class, class_reason FROM leads ORDER BY id DESC LIMIT 1").fetchone()[0] in ('Ready', 'Needs review'))
check('Export exposes Lead_Class and Class_Reason and a Ready filter', any(h == 'Lead_Class' for h, _ in app.EXPORT_COLUMNS) and any(h == 'Class_Reason' for h, _ in app.EXPORT_COLUMNS) and '"ready", "review"' in source_text)

# DNS: a failed lookup while DNS itself is down must say "unavailable", never "no MX records".
import socket as _socket
real_socket, real_gethost = _socket.socket, _socket.gethostbyname
class _NoUDP:
    def __init__(self, *a, **k): raise OSError('network down')
def _no_dns(name): raise _socket.gaierror(-2, 'Name or service not known')
_socket.socket, _socket.gethostbyname = _NoUDP, _no_dns
try:
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._resolver_probe = None
    offline = app.EmailValidator.check_mx_records('hsbc.com')
    def _only_example(name):
        if name == 'example.com': return '93.184.216.34'
        raise _socket.gaierror(-2, 'Name or service not known')
    _socket.gethostbyname = _only_example
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._resolver_probe = None
    online_missing = app.EmailValidator.check_mx_records('no-such-domain-xyz.invalid')
finally:
    _socket.socket, _socket.gethostbyname = real_socket, real_gethost
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._resolver_probe = None
# A resolver that answers NXDOMAIN to everything (sinkholed/filtered network) must not condemn real domains.
_orig_udp = app.EmailValidator._udp_mx_query
app.EmailValidator._udp_mx_query = classmethod(lambda cls, domain: ('nxdomain', 0))
_socket.gethostbyname = _no_dns
try:
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._dns_probe = None; app.EmailValidator._resolver_probe = None
    sink = app.EmailValidator.check_mx_records('hsbc.com')
finally:
    app.EmailValidator._udp_mx_query = _orig_udp
    _socket.gethostbyname = real_gethost
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._dns_probe = None; app.EmailValidator._resolver_probe = None
check('A resolver that says NXDOMAIN for everything is treated as unavailable', sink[0] is None and 'unavailable' in sink[1].lower())
# And a healthy resolver still condemns a genuinely missing domain.
app.EmailValidator._udp_mx_query = classmethod(lambda cls, domain: ('mx', 2) if domain == 'gmail.com' else ('nxdomain', 0))
try:
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._dns_probe = None
    healthy_missing = app.EmailValidator.check_mx_records('no-such-domain-xyz.invalid')
    healthy_ok = app.EmailValidator.check_mx_records('gmail.com')
finally:
    app.EmailValidator._udp_mx_query = _orig_udp
    app.EmailValidator._mx_cache.clear(); app.EmailValidator._dns_probe = None
check('With a healthy resolver a missing domain is rejected and a real one has MX', healthy_missing[0] is False and healthy_ok[0] is True)
check('DNS down is reported as unavailable, not "no MX records"', offline[0] is None and 'unavailable' in offline[1].lower())
check('A missing domain is still "no MX records" when DNS works', online_missing[0] is False and 'no MX' in online_missing[1])
check('An unavailable DNS result is not cached', 'hsbc.com' not in app.EmailValidator._mx_cache)

# v1.5.1: with the optional "phonenumbers" library installed (as on some Termux setups) a landline must be labelled "Landline".
try:
    import phonenumbers  # noqa: F401
    _have_pn = True
except ImportError:
    _have_pn = False
if _have_pn:
    _ll = app.PhoneValidator.validate('+91 40 6752 2016')
    _mob = app.PhoneValidator.validate('+91 98401 49369')
    check('phonenumbers path: a landline is labelled Landline', _ll[0] and 'landline' in _ll[1].lower())
    check('phonenumbers path: a mobile is labelled Mobile', _mob[0] and 'Mobile' in _mob[1] and 'landline' not in _mob[1].lower())
    check('phonenumbers path: landline-only lead is Needs review',
          app.classify_lead(mk(phone='+91 40 6752 2016', phone_valid=1, phone_status=_ll[1]))[0] == 'Needs review')
else:
    print('[SKIP] phonenumbers not installed; landline label tests skipped')

# ---------------- v1.6.0: expiry removal + selection modes ----------------
from datetime import datetime as _dt, timedelta as _td
_today = _dt.now()
_past = (_today - _td(days=3)).strftime('%d/%m/%Y')
_future = (_today + _td(days=30)).strftime('%d/%m/%Y')
check('parse_expiry day-first', app.parse_expiry('05/11/2026')[0] == _dt(2026, 11, 5))
check('parse_expiry month-first fallback', app.parse_expiry('11/25/2026')[0] == _dt(2026, 11, 25))
check('parse_expiry ISO + text month', app.parse_expiry('2026-12-01')[0] == _dt(2026, 12, 1) and app.parse_expiry('1st Dec 2026')[0] == _dt(2026, 12, 1))
check('parse_expiry garbage is None', app.parse_expiry('soon') is None and app.parse_expiry('') is None)
check('past date expired, future not', app.lead_is_expired(*app.parse_expiry(_past)) and not app.lead_is_expired(*app.parse_expiry(_future)))
_tdy = _today.strftime('%d/%m/%Y')
check('today is not yet expired (date only)', not app.lead_is_expired(*app.parse_expiry(_tdy)))
_rows = [
 {'HR Email': 'both@acme.com', 'Mobile NO:': '9876501234', 'Company': 'A', 'Expiry Date': _future},
 {'HR Email': 'mail@beta.com', 'Mobile NO:': '', 'Company': 'B', 'Expiry Date': _future},
 {'HR Email': '', 'Mobile NO:': '9123456780', 'Company': 'C', 'Expiry Date': _future},
 {'HR Email': 'old@gamma.com', 'Mobile NO:': '9812345670', 'Company': 'D', 'Expiry Date': _past},
 {'HR Email': 'dummy@delta.com', 'Mobile NO:': '9876543210', 'Company': 'E', 'Expiry Date': _future},
 {'HR Email': 'x@getnada.com', 'Mobile NO:': '', 'Company': 'F', 'Expiry Date': _future},
]
_res = app.process_leads_dataset(_rows, 'v160.csv', 0.0, False)
_all = app.fetch_latest_leads()
_by = {x['company']: x for x in _all}
check('expired lead removed from qualified', _by['D']['qualification_status'] != 'qualified' and _by['D']['lead_class'] == 'Expired')
check('expired count reported', _res.get('expired_count') == 1)
check('dummy phone 9876543210 not a valid mobile', not app.selection_flags(_by['E'])[1])
check('getnada disposable email rejected (real validator)', original_validate('x@getnada.com', False)[3] is True)
_live = [x for x in _all if x['qualification_status'] == 'qualified' and not x['is_duplicate']]
_pick = lambda m: sorted(x['company'] for x in _live if app.selection_result(x, m)[0])
check('mode any = email OR mobile', _pick('any') == ['A', 'B', 'C', 'E', 'F'])
check('mode email = valid email', _pick('email') == ['A', 'B', 'E', 'F'])
check('mode mobile = valid mobile', _pick('mobile') == ['A', 'C'])
check('mode both = email and mobile', _pick('both') == ['A'])
check('selection counts match', app.selection_counts(_live) == {'any': 5, 'email': 4, 'mobile': 2, 'both': 1})
check('every selected lead has a reason', all(app.selection_result(x, 'any')[1].startswith('Selected') for x in _live if app.selection_result(x, 'any')[0]))
check('expired lead never selected in any mode', all(not app.selection_result(_by['D'], m)[0] for m in app.SELECT_MODES) and 'expired' in app.selection_result(_by['D'], 'any')[1].lower())
check('every selected lead is scored', all(float(x['qualification_score'] or 0) > 0 for x in _live if app.selection_result(x, 'any')[0]))
_h, _r, _s = app.build_export(_all, 'selected', 'email')
check('export selected/email has reason + expiry columns and 4 rows', 'Selection_Reason' in _h and 'Expiry_Date' in _h and len(_r) == 4 and _s == 'selected_email')
_h2, _r2, _ = app.build_export(_all, 'expired')
check('export expired has 1 row', len(_r2) == 1)

# ---------------- v1.7.0: evaluate_leads + /api/ingest (used by the scraper) ----------------
import json as _json, threading as _th, urllib.request as _rq, urllib.error as _er
_recs = [
 {'HR Email': 'a@acme.com', 'Mobile NO:': '9876501234', 'Company': 'Acme', 'Job Title': 'Dev', 'Expiry Date': _future},
 {'HR Email': '', 'Mobile NO:': '', 'Company': 'Nobody', 'Job Title': 'Dev'},
 {'HR Email': 'old@gamma.com', 'Mobile NO:': '', 'Company': 'Gamma', 'Job Title': 'QA', 'Expiry Date': _past},
 {'HR Email': 'a@acme.com', 'Mobile NO:': '', 'Company': 'Acme again', 'Job Title': 'Other'},
 {'HR Email': '', 'Mobile NO:': '9123456780', 'Company': 'Phone Co', 'Job Title': 'Ops'},
]
_before = app.fetch_latest_leads()
_ev = app.evaluate_leads(_recs, 'any', persist=False)
_after = app.fetch_latest_leads()
check('evaluate_leads(persist=False) leaves the dashboard database untouched', len(_before) == len(_after))
check('evaluate_leads returns one verdict per record, in input order', [v['index'] for v in _ev['results']] == [0, 1, 2, 3, 4] and _ev['total'] == 5)
_sel = [v['selected'] for v in _ev['results']]
check('verdicts: valid contact selected; no contact, expired and duplicate are not', _sel == [True, False, False, False, True])
check('verdicts carry reason, score and class', all(v['selection_reason'] for v in _ev['results']) and _ev['results'][0]['score'] > 0 and _ev['results'][2]['lead_class'] == 'Expired' and _ev['results'][3]['lead_class'] == 'Duplicate')
check('evaluate_leads mode=mobile selects only the valid mobiles', [v['selected'] for v in app.evaluate_leads(_recs, 'mobile', persist=False)['results']] == [True, False, False, False, True])
check('evaluate_leads handles empty / bad input', app.evaluate_leads([], 'any')['selected_count'] == 0 and app.evaluate_leads(['x', None], 'bogus', persist=False)['mode'] == 'any')
check('DB path is restored after evaluate_leads', os.path.basename(app.DB_PATH) == 'test.db')
_srv = app.ThreadedHTTPServer(('127.0.0.1', 0), app.LeadIntelligenceHTTPHandler)
_port = _srv.server_address[1]
_th.Thread(target=_srv.serve_forever, daemon=True).start()
def _post(body, headers=None):
    req = _rq.Request(f'http://127.0.0.1:{_port}/api/ingest', data=body if isinstance(body, bytes) else _json.dumps(body).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with _rq.urlopen(req) as r:
            return r.status, _json.loads(r.read())
    except _er.HTTPError as e:
        return e.code, _json.loads(e.read())
_st, _body = _post({'leads': _recs, 'mode': 'any', 'persist': False})
check('POST /api/ingest returns verdicts as JSON', _st == 200 and _body['selected_count'] == 2 and len(_body['results']) == 5)
check('POST /api/ingest rejects a bad body', _post(b'not json')[0] == 400 and _post({'leads': 'x'})[0] == 400)
os.environ['LEADSCORE_API_KEY'] = 'secret'
check('POST /api/ingest enforces LEADSCORE_API_KEY when set', _post({'leads': _recs})[0] == 401 and _post({'leads': _recs, 'persist': False}, {'X-Api-Key': 'secret'})[0] == 200)
del os.environ['LEADSCORE_API_KEY']
_srv.shutdown()

app.EmailValidator.validate = original_validate
app.research_company_online = original_research
print(f'\nRESULT: {passed}/{total} passed; {total-passed} failed')
sys.exit(0 if passed==total else 1)
