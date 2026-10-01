#!/usr/bin/env python3
"""Job Scout tests: run the workflow's triggers through n8n's MCP test_workflow tool.

Each case clears the jobscout_test_ tables, runs the "Daily scan" trigger with
pinned data (fixture board response, test config, Jev and Claude replies, fake
Telegram replies), and the "Applied link" and "Referral link" webhook triggers with
a pinned GET request, and then checks only external behavior: rows in the test
tables, the items that reached the Jev, Claude and Telegram nodes, and the page an
action link returns. The pinned config
starts from the defaults in the workflow's "Job Scout config" node, so the cases
test the shipped rules, weights and thresholds.

  python3 tests/run_tests.py            # all cases
  python3 tests/run_tests.py cap        # cases whose name contains "cap"

Stdlib only. Needs the local n8n and N8N_API_KEY + N8N_MCP_TOKEN in .env.
"""
import copy
import hashlib
import hmac
import json
import math
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import n8n_mcp  # noqa: E402

API = os.environ.get("N8N_API_URL", "http://localhost:5678/api/v1")
WORKFLOW_NAME = "Job Scout"
TRIGGER = "Daily scan"
TEST_PREFIX = "jobscout_test_"
LEADS_TABLE = TEST_PREFIX + "leads"
STATE_TABLE = TEST_PREFIX + "state"
REFERRALS_TABLE = TEST_PREFIX + "referrals"
FAKE_CHAT_ID = "000000000"
FIXTURES = ROOT / "tests/fixtures"
FIXTURE = json.loads((FIXTURES / "ashby-n8n.json").read_text())
BOARD = "n8n"
# Synthetic Ashby-shaped postings, one or two per filter rule and edge case.
FILTER_FIXTURE = json.loads((FIXTURES / "ashby-filters.json").read_text())
FILTER_BOARD = "testco"
# Synthetic postings for pay found in the description and the freshness window.
SCORING_FIXTURE = json.loads((FIXTURES / "ashby-scoring.json").read_text())
SCORING_BOARD = "scoreco"
# Greenhouse and Lever: real postings from Instacart's and Spotify's boards, and
# synthetic postings in the same shapes for the location and pay rules.
GH_FIXTURE = json.loads((FIXTURES / "greenhouse-instacart.json").read_text())
GH_BOARD = "instacart"
LV_FIXTURE = json.loads((FIXTURES / "lever-spotify.json").read_text())
LV_BOARD = "spotify"
GHF_FIXTURE = json.loads((FIXTURES / "greenhouse-filters.json").read_text())
GHF_BOARD = "ghco"
LVF_FIXTURE = json.loads((FIXTURES / "lever-filters.json").read_text())
LVF_BOARD = "leverco"
# A real Jev response, recorded 2026-09-30 for n8n's Senior Developer Advocate posting.
JEV_RECORDED = json.loads((FIXTURES / "jev-response.json").read_text())

# Nodes that reach the outside world. test_workflow does not pin anything by
# itself, so every one of these must be pinned or the test would really call it.
EXTERNAL_TYPES = {"n8n-nodes-base.telegram", "n8n-nodes-base.httpRequest", "@n8n/n8n-nodes-langchain.anthropic"}
FETCH_NODE = "Fetch board"
HEADER_NODE = "Send header"
LEAD_NODE = "Send lead message"
JEV_NODE = "Ask Jev"
JEV_RETRY_NODE = "Ask Jev again"
FIT_NODE = "Write fit line"
CRASH_TRIGGER = "Scan crashed"
CRASH_NODE = "Send crash alert"
APPLIED_TRIGGER = "Applied link"
REFERRAL_TRIGGER = "Referral link"
PAGE_NODE = "Build page"
RESPOND_NODE = "Show page"
SIGNED_NODES = ("Build lead messages", "Check Applied link", "Check Referral link")

ENV = n8n_mcp.load_env()


# ---------- n8n access ----------

def api(method, path, query=None):
    url = API + path + ("?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote) if query else "")
    req = urllib.request.Request(url, method=method, headers={
        "X-N8N-API-KEY": ENV["N8N_API_KEY"], "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode()
    return json.loads(body) if body else None


def mcp(tool, args):
    # The MCP server rate-limits calls (HTTP 429, 100 per window); wait until the window
    # resets (X-RateLimit-Reset, epoch seconds), or longer each time, and retry.
    for attempt in range(10):
        try:
            return n8n_mcp.call(tool, args)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 9:
                raise
            reset = e.headers.get("X-RateLimit-Reset", "")
            wait = int(reset) - time.time() if reset.isdigit() else 0
            time.sleep(min(max(wait, 0), 900) + 2 if wait > 0 else 15 * (attempt + 1))


def find_workflow():
    wf_id = os.environ.get("JOB_SCOUT_WORKFLOW_ID")
    if not wf_id:
        found = [w for w in api("GET", "/workflows", {"name": WORKFLOW_NAME})["data"]
                 if w["name"] == WORKFLOW_NAME and not w.get("isArchived")]
        if len(found) != 1:
            sys.exit(f'Expected one workflow named "{WORKFLOW_NAME}", found {len(found)}. '
                     "Set JOB_SCOUT_WORKFLOW_ID to pick one.")
        wf_id = found[0]["id"]
    return api("GET", f"/workflows/{wf_id}")


def find_table(name):
    for t in api("GET", "/data-tables", {"filter": json.dumps({"name": name})})["data"]:
        if t["name"] == name:
            return t
    return None


def reset_test_tables():
    # Clearing the state table also drops the signing secret, so each case's first run
    # makes a new one.
    for name in (LEADS_TABLE, STATE_TABLE, REFERRALS_TABLE):
        table = find_table(name)
        if table is None:
            continue  # the workflow creates it on its first run
        assert table["name"].startswith(TEST_PREFIX), "refusing to clear a non-test table"
        api("DELETE", f"/data-tables/{table['id']}/rows/clear")


def table_rows(name):
    table = find_table(name)
    if table is None:
        return []
    out = mcp("get_data_table_rows", {"dataTableId": table["id"], "projectId": table["projectId"],
                                      "limit": 100})
    assert out["count"] <= 100, "test table has more rows than one page"
    return out["rows"]


def lead_rows():
    return table_rows(LEADS_TABLE)


def rows_by_key():
    return {r["lead_key"]: r for r in lead_rows()}


def set_first_seen(key, when):
    """Backdate a test lead's first sighting, as if an earlier scan had found it."""
    update_lead(key, {"first_seen_at": when.isoformat().replace("+00:00", "Z")})


def update_lead(key, data):
    """Change a test lead's row directly, as the job seeker could on the Data tables page."""
    table = find_table(LEADS_TABLE)
    assert table["name"].startswith(TEST_PREFIX)
    body = {"filter": {"type": "and", "filters": [{"columnName": "lead_key", "condition": "eq", "value": key}]},
            "data": data}
    req = urllib.request.Request(f"{API}/data-tables/{table['id']}/rows/update", method="PATCH",
                                 data=json.dumps(body).encode(), headers={
                                     "X-N8N-API-KEY": ENV["N8N_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


# ---------- fixtures: dates, keys and Jev answers ----------

DAY = timedelta(days=1)


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


ATS_ORDER = ["ashby", "greenhouse", "lever"]  # the order Board list fetches boards in


def jobs_of(fixture, ats):
    """The postings in a board response: Lever's is a bare list."""
    return fixture if ats == "lever" else fixture["jobs"]


def published(job, ats):
    if ats == "lever":
        return datetime.fromtimestamp(job["createdAt"] / 1000, timezone.utc)
    return parse_time(job["publishedAt" if ats == "ashby" else "first_published"])


def set_published(job, ats, when):
    if ats == "lever":
        job["createdAt"] = int(when.timestamp() * 1000)
    else:
        job["publishedAt" if ats == "ashby" else "first_published"] = when.isoformat().replace("+00:00", "Z")


def ages(fixture, ats="ashby"):
    """Each posting's age in whole days once rebased: the newest is 1 day old, and the
    others keep their distance from it, rounded to whole days."""
    jobs = jobs_of(fixture, ats)
    newest = max(published(j, ats) for j in jobs)
    return {j["id"]: round((newest - published(j, ats)) / DAY) + 1 for j in jobs}


def rebase(fixture, now, ats="ashby"):
    """The fixture with its publish dates moved to whole days before now, so the
    freshness window and freshness points don't drift as the recorded dates age."""
    out = copy.deepcopy(fixture)
    age = ages(fixture, ats)
    for j in jobs_of(out, ats):
        set_published(j, ats, now - age[j["id"]] * DAY)
    return out


def keyed(fixture, board, ats="ashby"):
    """Lead key -> posting, with `title` and `jobUrl` under Ashby's names for every ATS."""
    out = {}
    for j in jobs_of(fixture, ats):
        if not j.get("isListed", True):
            continue
        view = dict(j)
        if ats == "greenhouse":
            view["jobUrl"] = j["absolute_url"]
        elif ats == "lever":
            view["title"], view["jobUrl"] = j["text"], j["hostedUrl"]
        out[f"{ats}:{board}:{j['id']}"] = view
    return out


JOBS = [j for j in FIXTURE["jobs"] if j.get("isListed", True)]
KEY = keyed(FIXTURE, BOARD)
FKEY = keyed(FILTER_FIXTURE, FILTER_BOARD)
SKEY = keyed(SCORING_FIXTURE, SCORING_BOARD)
GHKEY = keyed(GH_FIXTURE, GH_BOARD, "greenhouse")
LVKEY = keyed(LV_FIXTURE, LV_BOARD, "lever")
GHFKEY = keyed(GHF_FIXTURE, GHF_BOARD, "greenhouse")
LVFKEY = keyed(LVF_FIXTURE, LVF_BOARD, "lever")
BOARDS = [(KEY, FIXTURE, "ashby"), (FKEY, FILTER_FIXTURE, "ashby"), (SKEY, SCORING_FIXTURE, "ashby"),
          (GHKEY, GH_FIXTURE, "greenhouse"), (LVKEY, LV_FIXTURE, "lever"),
          (GHFKEY, GHF_FIXTURE, "greenhouse"), (LVFKEY, LVF_FIXTURE, "lever")]
ALL_KEYS = {k: j for keys, _, _ in BOARDS for k, j in keys.items()}
AGE = {k: ages(fixture, ats)[j["id"]] for keys, fixture, ats in BOARDS for k, j in keys.items()}
BY_TITLE = {j["title"]: k for k, j in ALL_KEYS.items()}
assert len(BY_TITLE) == len(ALL_KEYS), "fixture titles must be unique"
FBY_TITLE = {j["title"]: k for k, j in FKEY.items()}

# What the default rules should decide for each posting, by title.
EXPECTED = {
    # n8n fixture (real postings)
    "Senior Developer Advocate, US": "passed",  # department is Marketing
    "Field Marketing Lead, US": "passed",
    "Enterprise Sales Development Representative US (Hybrid)": "location",  # hybrid in Boston
    "Forward Deployed Engineer - US East Coast": "passed",
    "Senior Partner Manager SI, West Coast": "passed",  # base tops out at $211,750
    "Senior FP&A Manager - Marketing": "location",  # remote in Europe only
    # synthetic fixture
    "Product Engineer": "location",  # hybrid in London
    "Senior Frontend Engineer": "pay_floor",  # base $140K-$170K; commission is ignored
    "Senior Corporate Paralegal": "excluded_title",
    "HR Business Partner": "excluded_title",  # Dallas hybrid passes location, title fails
    "Developer Experience Engineer": "passed",  # no pay stated
    "Solutions Engineer": "passed",  # no location stated
    "Software Engineer, Frontend": "passed",  # hybrid NYC, "Remote (US)" only as a secondary location
    "Product Engineer, Platform": "location",  # Remote (Canada)
    "Forward Deployed Engineer, Europe": "location",  # "Remote - Europe", no address
    "Senior Product Engineer": "passed",  # hybrid in Plano, TX
    "Forward Deployed Engineer": "location",  # hybrid in Austin
    "Developer Relations Engineer, SDKs & APIs": "passed",
    "Fintech Product Engineer": "passed",
    "Developer Advocate": "passed",  # department is Marketing
    "Product Manager, Developer Platform": "passed",  # base tops out exactly at the floor
    "Solutions Architect": "passed",  # pay only in EUR: unknown
    "Software Engineer Intern": "pay_floor",  # $12.5K a month = $150K a year
    "Partner Engineer": "location",  # Arlington, VA is not Arlington, TX
    "Software Engineer, Finance Platform": "passed",  # "Engineer" overrides "Finance"
    "Finance Manager, Revenue Accounting": "excluded_title",
    "Frontend Engineer": "passed",  # on-site in Dallas
    "Customer Engineer": "location",  # on-site in Austin
    "Technical Support Engineer": "pay_floor",  # $40-$60 an hour = $83.2K-$124.8K a year
    # scoring fixture
    "Developer Advocate, Platform": "passed",  # pay only in the description, below the floor
    "Senior Product Engineer, Growth": "passed",  # pay only in the description
    "Senior Frontend Engineer, Dashboards": "passed",  # posted 41 days ago: no freshness points
    # Greenhouse: Instacart (real)
    "Senior Software Engineer II, AI Labs & Foundations": "passed",  # base $192K-$242.5K across state ranges
    "Senior AI Solutions Sales Executive": "pay_floor",  # base tops out at $154K; the $220K OTE range is ignored
    "Billing Operations Associate": "pay_floor",  # hourly: $28.37-$32.94 x 2,080 hours tops out at $68.5K
    "Senior Product Manager, AI Control Studio": "location",  # Canada copy, though it lists a US remote office
    "iOS Developer": "location",  # hybrid in Israel
    # Lever: Spotify (real)
    "Backend Engineer - Music": "passed",  # remote, New York
    "Senior Software Engineer - Enterprise AI": "passed",  # remote, New York
    "Android Engineer - Experience": "location",  # hybrid in London or Stockholm
    "Lead, Global Markets Strategy": "location",  # hybrid in New York
    "Senior Legal Counsel - Music Publishing": "location",  # on-site in Los Angeles
    # Greenhouse: synthetic
    "Senior Developer Advocate, Data": "passed",  # "Hybrid - Dallas, TX", department Marketing
    "Staff Product Engineer": "location",  # "Austin, TX - Hybrid"
    "Frontend Platform Engineer": "passed",  # "Dallas, TX", no workplace type
    "Developer Experience Lead": "passed",  # no location: unclear
    "Solutions Engineer, Commercial": "location",  # hybrid in New York; a "Remote - United States" office is ignored
    "Senior Integrations Engineer": "pay_floor",  # base $150K-$170K; the OTE range is ignored
    # Lever: synthetic
    "Solutions Engineer, Dallas": "passed",  # "on-site" (the docs' spelling) in Dallas
    "Partner Engineer, Integrations": "passed",  # hybrid in London, "Remote (US)" in allLocations
    "Senior Frontend Engineer, Austin": "location",  # "onsite" in Austin
    "Product Engineer, Payments": "pay_floor",  # $12K-$14K a month = $144K-$168K a year
    "Contract Frontend Engineer": "passed",  # $90-$110 an hour x 2,080 hours = $187.2K-$228.8K a year
    "Partner Solutions Engineer": "passed",  # "unspecified", no location: unclear
    "Developer Advocate, EMEA": "location",  # remote in Stockholm or London
}
# location_basis that Apply hard filters gives each passing posting.
BASIS = {"Solutions Engineer": "unclear", "Senior Product Engineer": "metro", "Frontend Engineer": "metro",
         "Senior Developer Advocate, Data": "metro", "Frontend Platform Engineer": "metro",
         "Developer Experience Lead": "unclear", "Solutions Engineer, Dallas": "metro",
         "Partner Solutions Engineer": "unclear"}
PASSED = [k for k in KEY if EXPECTED[KEY[k]["title"]] == "passed"]
FPASSED = sorted(k for k, j in FKEY.items() if EXPECTED[j["title"]] == "passed")


def passing(keys):
    return sorted(k for k, j in keys.items() if EXPECTED[j["title"]] == "passed")

NONE = "None of these"
# What the pinned Jev answers say about each passing posting, by title:
# (role family, its probability, stack level 0-4, "names a stack" 0-1, seniority, domain level 0-3)
# A family's leftover probability goes to "None of these", and the reverse.
JEV = {
    "Senior Developer Advocate, US": ("DevRel/DevEx", .97, 1.0, .2, "senior", 2.5),
    "Field Marketing Lead, US": (NONE, .92, .4, .1, "lead", 1.0),
    "Forward Deployed Engineer - US East Coast": ("FDE/Solutions", .95, 3.2, .9, "senior", 1.5),
    "Senior Partner Manager SI, West Coast": (NONE, .72, 1.2, .3, "senior", 1.0),
    "Developer Experience Engineer": ("DevRel/DevEx", .91, 3.1, .8, "not_stated", 2.6),
    "Solutions Engineer": ("FDE/Solutions", .95, 2.6, .6, "not_stated", 2.4),
    "Software Engineer, Frontend": ("Product/Frontend Engineering", .93, 3.6, .95, "mid", 2.2),
    "Senior Product Engineer": ("Product/Frontend Engineering", .96, 3.4, .9, "senior", 2.1),
    "Developer Relations Engineer, SDKs & APIs": ("DevRel/DevEx", .97, 2.9, .85, "not_stated", 2.9),
    "Fintech Product Engineer": ("Product/Frontend Engineering", .88, 2.6, .9, "not_stated", 0.9),
    "Developer Advocate": ("DevRel/DevEx", .99, 1.2, .15, "not_stated", 2.4),
    "Product Manager, Developer Platform": ("DevEx/Product PM", .95, 1.6, .3, "not_stated", 3.0),
    "Solutions Architect": ("FDE/Solutions", .91, 2.3, .7, "staff_plus", 2.0),
    "Software Engineer, Finance Platform": ("Product/Frontend Engineering", .81, 2.8, .9, "mid", 1.2),
    "Frontend Engineer": ("Product/Frontend Engineering", .97, 3.8, .95, "not_stated", 1.4),
    "Developer Advocate, Platform": ("DevRel/DevEx", .97, 2.0, .6, "not_stated", 2.6),
    "Senior Product Engineer, Growth": ("Product/Frontend Engineering", .97, 3.7, .95, "senior", 2.2),
    "Senior Frontend Engineer, Dashboards": ("Product/Frontend Engineering", .96, 3.5, .9, "senior", 2.0),
    "Senior Software Engineer II, AI Labs & Foundations": ("Product/Frontend Engineering", .83, 2.6, .9, "senior", 1.2),
    "Billing Operations Associate": (NONE, .97, .2, .1, "intern_junior", .3),
    "Backend Engineer - Music": (NONE, .6, 1.5, .9, "mid", 1.0),
    "Senior Software Engineer - Enterprise AI": ("Product/Frontend Engineering", .7, 2.4, .8, "senior", 1.6),
    "Senior Developer Advocate, Data": ("DevRel/DevEx", .98, 2.2, .5, "senior", 2.4),
    "Frontend Platform Engineer": ("Product/Frontend Engineering", .95, 3.6, .9, "not_stated", 1.8),
    "Developer Experience Lead": ("DevRel/DevEx", .9, 2.0, .3, "lead", 2.5),
    "Solutions Engineer, Dallas": ("FDE/Solutions", .96, 3.0, .7, "not_stated", 2.0),
    "Partner Engineer, Integrations": ("DevRel/DevEx", .88, 2.8, .7, "not_stated", 2.2),
    "Contract Frontend Engineer": ("Product/Frontend Engineering", .94, 3.7, .95, "mid", 1.5),
    "Partner Solutions Engineer": ("FDE/Solutions", .9, 2.5, .5, "not_stated", 1.9),
}
# Jev's pick for the base salary question, for postings whose pay is only in the description.
JEV_PAY = {"Developer Advocate, Platform": "$150,000 - $170,000 USD",
           "Senior Product Engineer, Growth": "$190K–$230K"}
FAIL = "fail"  # in place of a spec: the request failed on both tries (Ask Jev and Ask Jev again)
RECOVER = "recover"  # in place of a spec: the first try failed and the second succeeded
FAILED_RESPONSE = {"error": {"message": "The service is receiving too many requests from you",
                             "description": "Overloaded", "name": "NodeApiError", "httpCode": "529"}}
FIT_FAIL = None  # in place of a fit line: the Claude request failed
FAILED_FIT = {"error": "Overloaded"}
FAMILIES = ["DevEx/Product PM", "FDE/Solutions", "Product/Frontend Engineering", "DevRel/DevEx", NONE]
LEVELS = ["intern_junior", "mid", "senior", "lead", "staff_plus", "manager", "founding", "not_stated"]


def r3(x):
    return round(x + 0.0, 3)


def choice(options, picked, p, other):
    probs = {o: 0.0 for o in options}
    probs[picked] = p
    probs[other] = r3(probs[other] + 1 - p)
    return {"type": "choice", "choice": picked, "confidence": r3(p), "probabilities": probs}


def score(recorded, value):
    lo = math.floor(value)
    probs = {k: 0.0 for k in recorded["legend"]}
    probs[str(lo)] = r3(1 - (value - lo))
    if value > lo:
        probs[str(lo + 1)] = r3(value - lo)
    return {"type": "score", "score": value, "confidence": r3(max(probs.values())),
            "legend": recorded["legend"], "probabilities": probs}


def jev_response(title):
    """A Jev response shaped like the recorded one, with this posting's answers."""
    family, p, stack, names, level, domain = JEV[title]
    rec = JEV_RECORDED["answers"]
    answers = {
        "role_family": choice(FAMILIES, family, p, NONE if family != NONE else FAMILIES[0]),
        "stack_fit": score(rec["stack_fit"], stack),
        "names_stack": {"type": "noul", "noul": names},
        "seniority": choice(LEVELS, level, 1.0, level),
        "domain_fit": score(rec["domain_fit"], domain),
    }
    if title in JEV_PAY:
        answers["base_salary"] = {"type": "choice", "choice": JEV_PAY[title], "confidence": 0.97,
                                  "probabilities": {JEV_PAY[title]: 0.97, "none": 0.03}}
    return {"model": JEV_RECORDED["model"], "answers": answers, "usage": {"input_tokens": 2100, "output_tokens": 200}}


# ---------- the fit score, worked out independently of the workflow ----------

WEIGHTS = {"roleFamily": 25, "stack": 20, "seniority": 15, "location": 15, "domain": 10, "freshness": 10,
           "referral": 5}
TARGET = ["senior", "lead", "founding"]


def half_up(x):
    return math.floor(x + 0.5)


def expected_points(key, weights=WEIGHTS, target=TARGET, referred=()):
    """`referred` is the companies (board names) with a referral."""
    title = ALL_KEYS[key]["title"]
    family, p, stack, names, level, domain = JEV[title]
    sub = {
        "roleFamily": r3(p if family != NONE else 1 - p),
        "stack": r3(names * stack / 4 + (1 - names) * 0.5),
        "seniority": 1 if level in target else 0.5 if level == "not_stated" else 0.2,
        "location": {"us_remote": 1, "metro": 1, "unclear": 0.5}[BASIS.get(title, "us_remote")],
        "domain": r3(domain / 3),
        "freshness": max(0, 1 - (AGE[key] + 1e-4) / 30),  # a scan runs seconds after the rebase
        "referral": 1 if key.split(":")[1] in referred else 0,
    }
    total = sum(weights.values())
    return {d: half_up(100 * weights[d] * sub[d] / total) for d in weights}


def expected_fit(key, **kw):
    return sum(expected_points(key, **kw).values())


def fit_order(keys, min_fit=60, **kw):
    """Keys in a role family and at or above the minimum, highest fit first; ties go to
    the newer posting. Every key is assumed first seen within the freshness window."""
    keep = [k for k in keys if JEV[ALL_KEYS[k]["title"]][0] != NONE and expected_fit(k, **kw) >= min_fit]
    return sorted(keep, key=lambda k: (-expected_fit(k, **kw), AGE[k], k))


# ---------- running the scan ----------

def config_defaults(workflow):
    """The config node's values. List and object fields are JSON inside ={{ }}."""
    node = next(n for n in workflow["nodes"] if n["name"] == "Job Scout config")
    out = {}
    for a in node["parameters"]["assignments"]["assignments"]:
        v = a["value"]
        if isinstance(v, str) and v.startswith("={{") and v.endswith("}}"):
            v = json.loads(v[3:-2])
        out[a["name"]] = v
    return out


FAILED_FETCH = "failed"  # in place of a fixture: the board's fetch failed
FAILED_FETCH_ITEM = {"error": {"message": "404 - {\"ok\":false,\"error\":\"Document not found\"}",
                               "name": "AxiosError", "status": 404}}


def scan_pins(workflow, daily_cap=10, board=BOARD, fixture=FIXTURE, boards=None, judged=(), jev=None,
              fit_lines=None, **config):
    """Pin data for one scan, and the lead keys expected to reach Jev and Ask Jev again."""
    boards = sorted(boards or [("ashby", board, fixture)], key=lambda b: ATS_ORDER.index(b[0]))
    cfg = config_defaults(workflow)
    cfg.update({"ashbyBoards": [b for a, b, _ in boards if a == "ashby"],
                "greenhouseBoards": [b for a, b, _ in boards if a == "greenhouse"],
                "leverBoards": [b for a, b, _ in boards if a == "lever"],
                "telegramChatId": FAKE_CHAT_ID, "dailyCap": daily_cap, "tablePrefix": TEST_PREFIX}, **config)
    now = datetime.now(timezone.utc)
    fetched = [{"json": FAILED_FETCH_ITEM} if f == FAILED_FETCH else
               {"json": {"body": rebase(f, now, a), "headers": {}, "statusCode": 200, "statusMessage": "OK"}}
               for a, _, f in boards]
    judged = sorted(judged)
    jev = jev or {}
    responses, retried, retry_responses = [], [], []
    for k in judged:
        title = ALL_KEYS[k]["title"]
        if jev.get(title) in (FAIL, RECOVER):
            responses.append(FAILED_RESPONSE)
            retried.append(k)
            retry_responses.append(FAILED_RESPONSE if jev[title] == FAIL else jev_response(title))
        else:
            responses.append(jev_response(title))
    lines = fit_lines or [f"Pinned fit line {i + 1}." for i in range(daily_cap)]
    pin = {
        TRIGGER: [{"json": {}}],
        "Job Scout config": [{"json": cfg}],
        FETCH_NODE: fetched,
        JEV_NODE: [{"json": r} for r in responses] or [{"json": {}}],
        JEV_RETRY_NODE: [{"json": r} for r in retry_responses] or [{"json": {}}],
        FIT_NODE: [{"json": FAILED_FIT if t is FIT_FAIL else {"content": [{"type": "text", "text": t}],
                                                             "merged_response": t}} for t in lines]
        or [{"json": {}}],
        HEADER_NODE: [{"json": {"ok": True, "result": {"message_id": 1}}}],
        LEAD_NODE: [{"json": {"ok": True, "result": {"message_id": 2}}}],
        CRASH_NODE: [{"json": {"ok": True, "result": {"message_id": 3}}}],
    }
    unpinned = [n["name"] for n in workflow["nodes"]
                if n["type"] in EXTERNAL_TYPES and n["name"] not in pin and not n.get("disabled")]
    assert not unpinned, f"external nodes without pin data: {unpinned}"
    return pin, judged, retried


def run_pinned(workflow, pin, trigger=TRIGGER):
    """Runs the workflow from a trigger with pin data; returns (status, result, runData)."""
    result = mcp("test_workflow", {"workflowId": workflow["id"], "pinData": pin,
                                   "triggerNodeName": trigger, "timeout": 180})
    execution = mcp("get_workflow_execution", {"workflowId": workflow["id"],
                                               "executionId": result["executionId"],
                                               "includeData": True})
    return result["status"], execution, execution["data"]["resultData"]["runData"]


def run_scan(workflow, **kw):
    """Runs one scan. `boards` is a list of (ats, board, fixture or FAILED_FETCH); by
    default one Ashby board. `judged` is the lead keys expected to reach Jev; their
    pinned answers come from JEV (or `jev`, by title, where FAIL means the request
    failed on both tries and RECOVER that it failed once and then succeeded), in the
    order Build Jev requests sends them. `fit_lines` are Claude's pinned replies, in
    send order (FIT_FAIL for a failed request)."""
    pin, judged, retried = scan_pins(workflow, **kw)
    status, execution, run_data = run_pinned(workflow, pin)
    assert status == "success", f"scan failed: {execution['data']['resultData'].get('error')}"
    asked = sorted(i["lead_key"] for i in items_reaching(run_data, JEV_NODE))
    assert asked == judged, (f"Jev was asked about {[ALL_KEYS[k]['title'] for k in asked]}, "
                             f"expected {[ALL_KEYS[k]['title'] for k in judged]}")
    again = [i["lead_key"] for i in items_reaching(run_data, JEV_RETRY_NODE)]
    assert again == retried, f"Ask Jev again got {titles(again)}, expected {titles(retried)}"
    return run_data


def items_reaching(run_data, node_name):
    """Items that went into a node, across all its runs, read from its sources' outputs."""
    items = []
    for run in run_data.get(node_name, []):
        for src in run.get("source") or []:
            if not src:
                continue
            prev = run_data[src["previousNode"]][src.get("previousNodeRun", 0)]
            outputs = prev["data"]["main"]
            items += [i["json"] for i in outputs[src.get("previousNodeOutput", 0)] or []]
    return items


def sent(run_data):
    return items_reaching(run_data, HEADER_NODE), items_reaching(run_data, LEAD_NODE)


def jev_requests(run_data):
    return {i["lead_key"]: i["jev_body"] for i in items_reaching(run_data, JEV_NODE)}


# ---------- shared checks ----------

def same_instant(a, b):
    return parse_time(a) == parse_time(b)


# ---------- signed action links ----------

def signing_secret():
    rows = table_rows(STATE_TABLE)
    secrets = [r["value"] for r in rows if r["key"] == "signing_secret"]
    assert len(secrets) == 1, f"expected one signing secret, found {len(secrets)}"
    return secrets[0]


def sign(action, key, secret=None):
    """The signature Job Scout should put on a link: HMAC-SHA256 of "<action>:<lead key>"
    with the stored secret, hex, first 32 characters."""
    secret = secret or signing_secret()
    return hmac.new(secret.encode(), f"{action}:{key}".encode(), hashlib.sha256).hexdigest()[:32]


def public_base():
    """The instance's public webhook base, as n8n derives it (never printed)."""
    base = ENV.get("N8N_WEBHOOK_URL") or ENV.get("WEBHOOK_URL") or "http://localhost:5678/"
    return base if base.endswith("/") else base + "/"


def link_query(url):
    """The query of an action link, after checking (without printing it) that it points at
    the production webhook on the public base."""
    parts = urllib.parse.urlsplit(url)
    assert url.startswith(public_base() + "webhook/job-scout/"), "action link isn't on the public webhook base"
    query = urllib.parse.parse_qs(parts.query)
    return parts.path.rsplit("/", 1)[1], {k: v[0] for k, v in query.items()}


def run_action(wf, trigger, query, **config):
    """Opens an action link: runs its webhook trigger with a pinned GET request. Returns the
    page (status, heading, lines, html) and the run data."""
    pin, _, _ = scan_pins(wf, **config)
    del pin[TRIGGER]
    pin[trigger] = [{"json": {"headers": {"user-agent": "Mozilla/5.0 (iPhone)"}, "params": {}, "query": query,
                              "body": {}}}]
    status, execution, run_data = run_pinned(wf, pin, trigger=trigger)
    assert status == "success", f"{trigger} failed: {execution['data']['resultData'].get('error')}"
    assert TRIGGER not in run_data, "the daily scan ran from an action link"
    pages = items_reaching(run_data, RESPOND_NODE)
    assert len(pages) == 1, f"expected one page, got {len(pages)}"
    page = dict(pages[0], lines=items_reaching(run_data, PAGE_NODE)[0].get("lines", []))
    return page, run_data


def tap(wf, action, key, sig=None, **config):
    """Taps a lead's Applied or Referral button, signed as Job Scout signs it unless `sig`
    is given."""
    trigger = APPLIED_TRIGGER if action == "applied" else REFERRAL_TRIGGER
    query = {"lead": key, "sig": sign(action, key) if sig is None else sig}
    return run_action(wf, trigger, {k: v for k, v in query.items() if v is not False}, **config)


def check_page(page, status, heading):
    assert (page["http_status"], page["heading"]) == (status, heading), (page["http_status"], page["heading"])
    assert f"<h1>{heading}</h1>" in page["html"]


def ran(run_data, node):
    return bool(run_data.get(node))


def check_lead_messages(leads, rows_by_key):
    secret = signing_secret() if leads else None
    for msg in leads:
        key = msg["lead_key"]
        assert msg["silent"] is True, f"lead message not silent: {key}"
        assert msg["button_text"] == "Open posting", msg
        assert msg["button_url"] == ALL_KEYS[key]["jobUrl"], msg
        assert msg["button_url"] == rows_by_key[key]["posting_url"]
        # Applied and Referral: signed links on the public base, without the secret.
        for action in ("applied", "referral"):
            path, query = link_query(msg[f"{action}_url"])
            assert path == action and query == {"lead": key, "sig": sign(action, key, secret)}, \
                f"{action} link for {key} has the wrong path, lead or signature"
        assert secret not in json.dumps(msg), "the signing secret is in a lead message"


def check_header(header, n, unscored=0):
    # The unscored note appears only when Jev couldn't score a lead.
    assert len(header) == 1, f"expected one header, got {len(header)}"
    word = "lead" if n == 1 else "leads"
    want = f"Job Scout: {n} new {word} today"
    if unscored:
        want += f" · {unscored} couldn't be scored (retrying next scan)"
    assert header[0]["text"] == want, header[0]
    assert header[0]["silent"] is False, "header must make a sound"


def check_empty_day(header, leads, scanned, filtered, unscored=0):
    # Nothing to send: one silent message with the day's counts, and no lead messages.
    assert leads == [], f"an empty day sent {len(leads)} lead message(s)"
    assert len(header) == 1, f"expected one empty-day message, got {len(header)}"
    note = f"{unscored} couldn't be scored" + (" (retrying next scan)" if unscored else "")
    want = (f"Job Scout: no new leads today\n{scanned} posting{'' if scanned == 1 else 's'} scanned · "
            f"{filtered} filtered out · {note}")
    assert header[0]["text"] == want, header[0]["text"]
    assert header[0]["silent"] is True, "the empty-day message should be silent"


def titles(keys):
    return [ALL_KEYS[k]["title"] for k in keys]


def check_sent_order(leads, expected):
    got = [m["lead_key"] for m in leads]
    assert got == expected, f"sent {titles(got)}, expected {titles(expected)}"


# ---------- cases: the scan and the daily ping ----------

def case_one_lead_per_posting(wf):
    reset_test_tables()
    now = datetime.now(timezone.utc)
    run_scan(wf, judged=PASSED)
    rebased = {j["id"]: j for j in rebase(FIXTURE, now)["jobs"]}
    rows = lead_rows()
    keys = [r["lead_key"] for r in rows]
    assert len(rows) == len(JOBS), f"{len(rows)} rows for {len(JOBS)} postings"
    assert sorted(keys) == sorted(KEY), "lead keys don't match the postings"
    for r in rows:
        job = KEY[r["lead_key"]]
        assert (r["ats"], r["board"], r["job_id"]) == ("ashby", BOARD, job["id"])
        assert r["company"] == BOARD and r["title"] == job["title"]
        assert r["location_text"] == job["location"]
        assert r["workplace_type"] == job["workplaceType"]
        assert r["secondary_locations"] == "; ".join(l["location"] for l in job["secondaryLocations"])
        assert r["pay_text"] == (job["compensation"]["compensationTierSummary"] or "")
        assert r["posting_url"] == job["jobUrl"] and r["apply_url"] == job["applyUrl"]
        assert abs((parse_time(r["published_at"]) - parse_time(rebased[job["id"]]["publishedAt"])).total_seconds()) < 1
        assert r["status"] == "new" and r["first_seen_at"], r
        assert r["filter_result"] == EXPECTED[job["title"]], (job["title"], r["filter_result"])
        # Only leads that passed the filters are scored.
        want = "scored" if r["filter_result"] == "passed" else None
        assert r["scoring_state"] == want, (job["title"], r["scoring_state"])


def case_daily_ping_shape(wf):
    reset_test_tables()
    run_data = run_scan(wf, judged=PASSED)
    header, leads = sent(run_data)
    rows = rows_by_key()
    expected = fit_order(PASSED)
    assert len(expected) == 2, "fixture should leave two leads at or above the minimum"
    check_header(header, len(expected))
    check_sent_order(leads, expected)
    check_lead_messages(leads, rows)
    assert all(rows[k]["sent_at"] for k in expected), "sent leads have no sent_at"


def case_rescan_creates_no_duplicates_and_sends_no_leads(wf):
    # The second scan also asks Jev nothing: the two unsent leads below the minimum
    # are still candidates, but their scoring input hasn't changed.
    reset_test_tables()
    run_scan(wf, judged=PASSED)
    before = rows_by_key()
    run_data = run_scan(wf, judged=())
    after_rows = lead_rows()
    after = {r["lead_key"]: r for r in after_rows}
    assert len(after_rows) == len(before) == len(JOBS), "second scan changed the row count"
    for key, row in after.items():
        assert row["id"] == before[key]["id"], f"{key} got a new row"
        assert row["first_seen_at"] == before[key]["first_seen_at"], f"{key} first_seen_at changed"
        assert row["sent_at"] == before[key]["sent_at"], f"{key} sent_at changed"
        assert row["scored_at"] == before[key]["scored_at"], f"{key} was judged again"
    header, leads = sent(run_data)
    check_empty_day(header, leads, scanned=len(KEY), filtered=len(KEY) - len(PASSED))


def case_cap_and_carry_over_by_fit(wf):
    # Leads that miss the cap are sent on later scans, highest fit first, never twice,
    # and Claude writes fit lines only for the leads sent that day.
    cap = 4
    order = fit_order(FPASSED)
    assert len(order) == len(FPASSED) > 2 * cap, "fixture must exceed two caps"
    reset_test_tables()
    done = []
    for scan, judged in enumerate([FPASSED, (), ()]):
        run_data = run_scan(wf, daily_cap=cap, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=judged)
        header, leads = sent(run_data)
        want = order[len(done):len(done) + cap]
        check_header(header, len(want))
        check_sent_order(leads, want)
        claude = [i["lead_key"] for i in items_reaching(run_data, FIT_NODE)]
        assert claude == want, f"scan {scan + 1}: Claude wrote for {titles(claude)}"
        assert not set(done) & set(want), "a lead was sent twice"
        done += want
    rows = rows_by_key()
    assert sorted(k for k, r in rows.items() if r["sent_at"]) == sorted(FPASSED)
    header, leads = sent(run_scan(wf, daily_cap=cap, board=FILTER_BOARD, fixture=FILTER_FIXTURE))
    check_empty_day(header, leads, scanned=len(FKEY), filtered=len(FKEY) - len(FPASSED))


def case_telegram_nodes_send_what_they_receive(wf):
    # Pinned nodes don't evaluate their parameters, so check once that both send
    # nodes pass the incoming item through: text, sound, HTML, no attribution, button.
    nodes = {n["name"]: n for n in wf["nodes"]}
    for name in (HEADER_NODE, LEAD_NODE):
        p = nodes[name]["parameters"]
        extra = p.get("additionalFields", {})
        assert p["text"] == "={{ $json.text }}", name
        assert extra.get("parse_mode") == "HTML", f"{name}: parse mode not HTML"
        assert extra.get("appendAttribution") is False, f"{name}: attribution not off"
        assert extra.get("disable_notification") == "={{ $json.silent }}", name
    # Row 1: Open posting. Row 2: Applied and Referral, as URL buttons to the signed links.
    rows = [r["row"]["buttons"] for r in nodes[LEAD_NODE]["parameters"]["inlineKeyboard"]["rows"]]
    got = [[(b["text"], b["additionalFields"]["url"]) for b in row] for row in rows]
    assert got == [[("={{ $json.button_text }}", "={{ $json.button_url }}")],
                   [("Applied", "={{ $json.applied_url }}"), ("Referral", "={{ $json.referral_url }}")]], got


def case_jev_and_claude_nodes_call_what_they_receive(wf):
    # The same check for the pinned Jev and Claude nodes: Jev gets the request body
    # built for each lead, with the TypeSafe Bearer credential, retries and a failed
    # request passed on instead of stopping the scan. Claude gets the posting and the
    # profile summary, under a prompt that forbids invented facts.
    nodes = {n["name"]: n for n in wf["nodes"]}
    jev = nodes[JEV_NODE]
    p = jev["parameters"]
    assert (p["method"], p["url"]) == ("POST", "https://api.typesafe.ai/v1/systemone")
    assert (p["authentication"], p["genericAuthType"]) == ("genericCredentialType", "httpBearerAuth")
    assert "httpBearerAuth" in jev.get("credentials", {}), "Ask Jev has no Bearer credential"
    assert p["jsonBody"] == "={{ JSON.stringify($json.jev_body) }}"
    assert jev.get("onError") == "continueRegularOutput"
    # Ask Jev tries each request once (n8n retries a node only when its first item
    # fails, and then re-sends every item); the failed ones go to Ask Jev again, which
    # sends the same request and retries.
    again = nodes[JEV_RETRY_NODE]
    assert again["parameters"] == p, "Ask Jev again must send the same request as Ask Jev"
    assert again.get("credentials") == jev.get("credentials")
    assert again.get("retryOnFail") is True and again.get("maxTries", 3) >= 2
    assert again.get("onError") == "continueRegularOutput"
    claude = nodes[FIT_NODE]
    p = claude["parameters"]
    assert (p["resource"], p["operation"]) == ("text", "message")
    assert p["modelId"]["value"] == "claude-sonnet-5-5", p["modelId"]
    assert "anthropicApi" in claude.get("credentials", {}), "Write fit line has no Anthropic credential"
    prompt = p["messages"]["values"][0]["content"]
    for field in ("profileSummary", "$json.title", "$json.company", "$json.description"):
        assert field in prompt, f"fit line prompt lacks {field}"
    system = p["options"]["system"]
    assert "only facts written in the posting or in the job seeker's profile summary" in system
    assert "Do not invent" in system
    assert claude.get("onError") == "continueRegularOutput"


# ---------- cases: scoring and selection ----------

def case_fit_score_from_sub_scores_and_weights(wf):
    reset_test_tables()
    run_scan(wf, judged=PASSED, minFitScore=101)  # score only; send nothing
    rows = rows_by_key()
    for k in PASSED:
        r, title = rows[k], KEY[k]["title"]
        pts = expected_points(k)
        assert r["fit_score"] == sum(pts.values()), (title, r["fit_score"], pts)
        family = JEV[title][0]
        assert r["role_family"] == family and r["seniority_level"] == JEV[title][4], title
        assert r["scoring_state"] == "scored" and r["jev_model"] == "jev-1.13.0", title
        assert r["sub_location"] == 1 and r["sub_referral"] == 0, title
        assert 0 < r["sub_freshness"] <= 1, title
        assert json.loads(r["jev_answers"])["role_family"]["choice"] == family
        assert not r["sent_at"], f"{title} sent although minFitScore is 101"


def case_weight_change_reranks_without_jev(wf):
    new_weights = {**WEIGHTS, "stack": 0, "freshness": 0, "domain": 40}
    before, after = fit_order(FPASSED)[0], fit_order(FPASSED, weights=new_weights)[0]
    assert before != after, "fixture: the new weights must change the top lead"
    reset_test_tables()
    run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED, minFitScore=101)
    scored = rows_by_key()
    header, leads = sent(run_scan(wf, daily_cap=1, board=FILTER_BOARD, fixture=FILTER_FIXTURE,
                                  judged=(), weights=new_weights))
    check_sent_order(leads, [after])
    rows = rows_by_key()
    for k in FPASSED:
        assert rows[k]["scored_at"] == scored[k]["scored_at"], "a weight change re-asked Jev"
        assert rows[k]["fit_score"] == expected_fit(k, weights=new_weights), FKEY[k]["title"]


def case_below_minimum_never_sent(wf):
    reset_test_tables()
    keep, low = fit_order(PASSED, min_fit=80), BY_TITLE["Forward Deployed Engineer - US East Coast"]
    assert 60 <= expected_fit(low) < 80 <= expected_fit(keep[0]) and len(keep) == 1
    for judged in (PASSED, ()):
        header, leads = sent(run_scan(wf, judged=judged, minFitScore=80))
        assert low not in {m["lead_key"] for m in leads}, "a lead below the minimum was sent"
    rows = rows_by_key()
    assert rows[keep[0]]["sent_at"] and not rows[low]["sent_at"]
    assert rows[low]["selection_reason"] == "below_min_fit", rows[low]["selection_reason"]


def case_no_role_family_never_sent(wf):
    # With no role family points, the two "None of these" leads clear the minimum on
    # their other sub-scores, but a lead outside the role families is never sent.
    reset_test_tables()
    weights = {**WEIGHTS, "roleFamily": 0}
    none = [k for k in PASSED if JEV[KEY[k]["title"]][0] == NONE]
    assert len(none) == 2 and all(expected_fit(k, weights=weights) >= 60 for k in none)
    header, leads = sent(run_scan(wf, judged=PASSED, weights=weights))
    check_sent_order(leads, fit_order(PASSED, weights=weights))
    rows = rows_by_key()
    for k in none:
        r = rows[k]
        assert r["fit_score"] >= 60 and not r["sent_at"], KEY[k]["title"]
        assert r["role_family"] == NONE and r["selection_reason"] == "no_role_family", r["selection_reason"]


def case_freshness_window_counts_from_first_seen(wf):
    # A posting published 41 days ago is new to Job Scout today, so it is judged and
    # sent, with no freshness points. A lead first seen 31 days ago is not judged or
    # sent again, even though it would be the top lead.
    reset_test_tables()
    old = BY_TITLE["Senior Frontend Engineer, Dashboards"]
    top = BY_TITLE["Senior Product Engineer, Growth"]
    assert AGE[old] > 30 and expected_points(old)["freshness"] == 0
    run_scan(wf, board=SCORING_BOARD, fixture=SCORING_FIXTURE, judged=list(SKEY), minFitScore=101)
    rows = rows_by_key()
    assert rows[old]["sub_freshness"] == 0 and rows[old]["selection_reason"] == "below_min_fit"
    set_first_seen(top, datetime.now(timezone.utc) - 31 * DAY)
    header, leads = sent(run_scan(wf, board=SCORING_BOARD, fixture=SCORING_FIXTURE, judged=()))
    check_sent_order(leads, [old])
    rows = rows_by_key()
    assert rows[top]["selection_reason"] == "window_passed" and not rows[top]["sent_at"], rows[top]
    assert rows[old]["fit_score"] == expected_fit(old) and rows[old]["sent_at"]


def case_changed_profile_summary_rejudges_unsent_leads(wf):
    reset_test_tables()
    run_scan(wf, judged=PASSED)
    sent_keys = fit_order(PASSED)
    unsent = [k for k in PASSED if k not in sent_keys]
    before = rows_by_key()
    run_data = run_scan(wf, judged=unsent, profileSummary="A different profile summary for the test.")
    for body in jev_requests(run_data).values():
        assert body["state"]["profile"]["summary"] == "A different profile summary for the test."
    rows = rows_by_key()
    for k in unsent:
        assert rows[k]["scoring_fingerprint"] != before[k]["scoring_fingerprint"], KEY[k]["title"]
    for k in sent_keys:
        assert rows[k]["scored_at"] == before[k]["scored_at"], "a sent lead was judged again"


def case_developer_advocate_under_marketing_gets_devrel(wf):
    # The department never reaches Jev; the role family question says to ignore it,
    # and nothing in code lowers a Marketing lead's score.
    rows, (_, leads), requests = filter_scan(wf)
    k = FBY_TITLE["Developer Advocate"]
    assert FKEY[k]["department"] == "Marketing"
    body = requests[k]
    posting = body["state"]["posting"]
    assert set(posting) == {"title", "company", "location", "pay", "description"}, posting.keys()
    assert "Marketing" not in json.dumps(body["state"]), "the department reached Jev"
    question = body["questions"]["role_family"]
    assert question["type"] == "choice"
    assert "Ignore which department" in question["instructions"]["how_to_judge"]
    assert set(question["criteria"]) == {f["name"] for f in config_defaults(wf)["roleFamilies"]} | {NONE}
    assert body["model"] == "jev-1.13.0"
    r = rows[k]
    assert r["role_family"] == "DevRel/DevEx" and r["sub_role_family"] == 0.99, r
    assert r["fit_score"] == expected_fit(k) and k in {m["lead_key"] for m in leads}


def case_jev_failure_leaves_lead_unscored(wf):
    # Jev fails for three leads. Each failed request gets a second try in the same scan:
    # one succeeds and that lead is scored and sent; two fail again and are saved
    # unscored, held back, and counted in the header. The next scan judges only those
    # two again, and then they are sent.
    reset_test_tables()
    failed = [FBY_TITLE["Senior Product Engineer"], FBY_TITLE["Developer Advocate"]]  # top leads when scored
    recovered = FBY_TITLE["Frontend Engineer"]
    jev = {FKEY[k]["title"]: FAIL for k in failed}
    jev[FKEY[recovered]["title"]] = RECOVER
    run_data = run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED, daily_cap=50, jev=jev)
    header, leads = sent(run_data)
    rows = rows_by_key()
    for k in failed:
        r = rows[k]
        assert r["scoring_state"] == "unscored" and r["fit_score"] is None and not r["sent_at"], r
        assert r["selection_reason"] == "unscored", r["selection_reason"]
    assert rows[recovered]["scoring_state"] == "scored" and rows[recovered]["fit_score"] == expected_fit(recovered)
    want = fit_order(set(FPASSED) - set(failed))
    assert recovered in want
    check_sent_order(leads, want)
    check_header(header, len(want), unscored=2)
    # The next scan judges the two again (and nothing else), and then they are sent.
    header, leads = sent(run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=failed))
    check_sent_order(leads, fit_order(failed))
    check_header(header, 2)
    rows = rows_by_key()
    assert all(rows[k]["scoring_state"] == "scored" and rows[k]["sent_at"] for k in failed)


def case_claude_failure_still_sends_lead(wf):
    # Claude fails for the first lead: it is still sent, with no fit line, and the
    # other leads keep theirs.
    reset_test_tables()
    order = fit_order(PASSED)
    run_data = run_scan(wf, judged=PASSED, fit_lines=[FIT_FAIL, "Pinned fit line 2."])
    header, leads = sent(run_data)
    check_header(header, len(order))
    check_sent_order(leads, order)
    assert "<i>" not in leads[0]["text"] and leads[0]["fit_line"] is None, leads[0]["text"]
    assert "<i>Pinned fit line 2.</i>" in leads[1]["text"], leads[1]["text"]
    rows = rows_by_key()
    assert all(rows[k]["sent_at"] for k in order), "a lead without a fit line wasn't sent"
    assert not rows[order[0]]["fit_line"] and rows[order[1]]["fit_line"] == "Pinned fit line 2."


def case_empty_day_message_counts(wf):
    # Nothing to send: one silent message with how many postings were scanned, how many
    # were filtered out and how many couldn't be scored.
    # 1. Every posting fails a hard rule, so no lead is even a candidate.
    reset_test_tables()
    only_filtered = without(FILTER_FIXTURE, FPASSED)
    n = len(FKEY) - len(FPASSED)
    header, leads = sent(run_scan(wf, board=FILTER_BOARD, fixture=only_filtered))
    check_empty_day(header, leads, scanned=n, filtered=n)
    # 2. Leads are scored but none reaches the minimum. A salary Jev found in the
    #    description below the floor counts as filtered.
    reset_test_tables()
    header, leads = sent(run_scan(wf, board=SCORING_BOARD, fixture=SCORING_FIXTURE, judged=list(SKEY),
                                  minFitScore=101))
    check_empty_day(header, leads, scanned=len(SKEY), filtered=1)
    # 3. Jev fails for one lead and none of the others reaches the minimum.
    reset_test_tables()
    run_data = run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED, minFitScore=101,
                        jev={"Senior Product Engineer": FAIL})
    header, leads = sent(run_data)
    check_empty_day(header, leads, scanned=len(FKEY), filtered=len(FKEY) - len(FPASSED), unscored=1)
    assert items_reaching(run_data, FIT_NODE) == [], "Claude ran on an empty day"


def case_every_board_failing_crashes_the_scan(wf):
    # With no board fetched there is nothing to report as an empty day, so the scan
    # fails at Normalize postings (which sends the crash alert in a published run).
    reset_test_tables()
    pin, _, _ = scan_pins(wf, boards=[("ashby", FILTER_BOARD, FAILED_FETCH), ("lever", LVF_BOARD, FAILED_FETCH)])
    status, execution, run_data = run_pinned(wf, pin)
    assert status != "success", "the scan should fail when no board could be fetched"
    result = execution["data"]["resultData"]
    assert result["lastNodeExecuted"] == "Normalize postings", result["lastNodeExecuted"]
    error = result["error"]
    assert error["message"].startswith("No board could be fetched: ashby:testco (404"), error["message"]
    assert "lever:leverco" in error["message"]
    assert HEADER_NODE not in run_data and lead_rows() == []


# The data n8n's Error Trigger gets when a published run fails, in the shape recorded from
# a real failed scan on 2026-10-01 (n8n 2.41.3): a Code node error carries no `node`, and
# lastNodeExecuted is the step that failed. The host is made up.
CRASH_DATA = {
    "execution": {
        "id": "470", "url": "https://n8n.example.com/workflow/abc/executions/470",
        "error": {"message": "Request failed <html> & more [line 3]", "name": "WrappedExecutionError",
                  "level": "info", "lineNumber": 3, "description": None, "tags": {}, "shouldReport": False,
                  "stack": "WrappedExecutionError: Request failed"},
        "lastNodeExecuted": "Board list", "mode": "trigger",
        "executionContext": {"version": 1, "source": "trigger",
                             "triggerNode": {"name": "Daily scan", "type": "n8n-nodes-base.scheduleTrigger"}},
    },
    "workflow": {"id": "abc", "name": "Job Scout"},
}


def case_crash_alert_names_the_failed_step(wf):
    # Runs the crash alert path from its Error Trigger with pinned error data (a real
    # published failure is checked by hand; see tests/README.md).
    nodes = {n["name"]: n for n in wf["nodes"]}
    assert nodes[CRASH_TRIGGER]["type"] == "n8n-nodes-base.errorTrigger"
    assert not wf.get("settings", {}).get("errorWorkflow"), "another error workflow would replace this path"
    p = nodes[CRASH_NODE]["parameters"]
    assert p["chatId"] == ("={{ $('Job Scout config').params.assignments.assignments"
                           ".find((a) => a.name === 'telegramChatId').value }}"), p["chatId"]
    assert p["text"] == "={{ $json.text }}"
    extra = p["additionalFields"]
    assert extra.get("parse_mode") == "HTML" and extra.get("appendAttribution") is False
    assert "telegramApi" in nodes[CRASH_NODE].get("credentials", {}), "Send crash alert has no credential"
    pin = {CRASH_TRIGGER: [{"json": CRASH_DATA}], CRASH_NODE: [{"json": {"ok": True, "result": {"message_id": 3}}}]}
    status, execution, run_data = run_pinned(wf, pin, trigger=CRASH_TRIGGER)
    assert status == "success", execution["data"]["resultData"].get("error")
    (alert,) = items_reaching(run_data, CRASH_NODE)
    assert alert["text"] == ("Job Scout scan failed at Board list: Request failed &lt;html&gt; &amp; more [line 3]"
                             "\nExecution: https://n8n.example.com/workflow/abc/executions/470"), alert["text"]
    assert alert["silent"] is False
    # An error that names its node (as node errors can) wins over lastNodeExecuted.
    data = copy.deepcopy(CRASH_DATA)
    data["execution"]["error"]["node"] = {"name": "Fetch board", "type": "n8n-nodes-base.httpRequest"}
    pin[CRASH_TRIGGER] = [{"json": data}]
    _, _, run_data = run_pinned(wf, pin, trigger=CRASH_TRIGGER)
    (alert,) = items_reaching(run_data, CRASH_NODE)
    assert alert["text"].startswith("Job Scout scan failed at Fetch board: "), alert["text"]


def case_message_shows_fit_breakdown_and_fit_line(wf):
    reset_test_tables()
    order = fit_order(PASSED)
    lines = [f"Fits because {KEY[k]['title']} matches the profile & stack." for k in order]
    run_data = run_scan(wf, judged=PASSED, fit_lines=lines)
    _, leads = sent(run_data)
    check_sent_order(leads, order)
    rows = rows_by_key()
    for msg, line in zip(leads, lines):
        p = expected_points(msg["lead_key"])
        breakdown = (f"Fit {sum(p.values())} · role {p['roleFamily']} · stack {p['stack']} · "
                     f"seniority {p['seniority']} · location {p['location']} · domain {p['domain']} · "
                     f"fresh {p['freshness']}")
        assert breakdown in msg["text"], msg["text"]
        assert "<i>" + line.replace("&", "&amp;") + "</i>" in msg["text"], "fit line missing or not escaped"
        assert rows[msg["lead_key"]]["fit_line"] == line, "fit line not saved"
    claude = items_reaching(run_data, FIT_NODE)
    assert [i["lead_key"] for i in claude] == order, "Claude wrote for leads that weren't sent"
    assert all(i["description"] for i in claude), "Claude didn't get the posting description"


def case_pay_found_in_description(wf):
    # No structured pay: a regex finds dollar amounts, Jev picks the base salary, and
    # code compares it with the floor.
    reset_test_tables()
    below = BY_TITLE["Developer Advocate, Platform"]  # $150,000 - $170,000
    above = BY_TITLE["Senior Product Engineer, Growth"]  # $190K–$230K
    run_data = run_scan(wf, board=SCORING_BOARD, fixture=SCORING_FIXTURE, judged=list(SKEY))
    requests = jev_requests(run_data)
    options = requests[below]["questions"]["base_salary"]["criteria"]
    assert list(options) == ["$20k-$100k", "$150,000 - $170,000 USD", "none"], list(options)
    assert len(requests[below]["state"]["posting"]["pay_mentions"]) == 2
    rows = rows_by_key()
    assert rows[below]["filter_result"] == "pay_floor", rows[below]["filter_result"]
    assert rows[below]["selection_reason"] == "pay_floor" and not rows[below]["sent_at"]
    assert (rows[below]["pay_extracted_min"], rows[below]["pay_extracted_max"]) == (150000, 170000)
    assert (rows[above]["pay_extracted_min"], rows[above]["pay_extracted_max"]) == (190000, 230000)
    _, leads = sent(run_data)
    order = fit_order([above, BY_TITLE["Senior Frontend Engineer, Dashboards"]])
    check_sent_order(leads, order)
    text = leads[order.index(above)]["text"]
    assert "Pay: $190K–$230K (from the description)" in text, text
    assert [i["lead_key"] for i in items_reaching(run_data, FIT_NODE)] == order


# ---------- hard filters ----------

_filter_scan = {}


def filter_scan(wf):
    """One scan of the synthetic fixture, shared by the cases that only read it."""
    if not _filter_scan:
        reset_test_tables()
        run_data = run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED)
        _filter_scan["rows"] = rows_by_key()
        _filter_scan["sent"] = sent(run_data)
        _filter_scan["requests"] = jev_requests(run_data)
    return _filter_scan["rows"], _filter_scan["sent"], _filter_scan["requests"]


def case_filters_store_the_failed_rule(wf):
    rows, _, _ = filter_scan(wf)
    assert sorted(rows) == sorted(FKEY), "filtered postings must still be saved as leads"
    wrong = {FKEY[k]["title"]: r["filter_result"] for k, r in rows.items()
             if r["filter_result"] != EXPECTED[FKEY[k]["title"]]}
    assert not wrong, f"wrong filter_result: {wrong}"
    basis = lambda t: rows[FBY_TITLE[t]]["location_basis"]
    assert basis("Software Engineer, Frontend") == "us_remote"
    assert basis("Senior Product Engineer") == "metro"
    assert basis("Frontend Engineer") == "metro"
    assert basis("Solutions Engineer") == "unclear"
    pay = lambda t: (rows[FBY_TITLE[t]]["pay_min"], rows[FBY_TITLE[t]]["pay_max"])
    assert pay("Software Engineer, Frontend") == (143200, 284000)
    assert pay("Senior Frontend Engineer") == (140000, 170000), "commission counted as base pay"
    assert pay("Software Engineer Intern") == (150000, 150000), "monthly pay not made yearly"
    assert pay("Technical Support Engineer") == (83200, 124800), "hourly pay not counted at 2,080 hours"
    assert rows[FBY_TITLE["Technical Support Engineer"]]["pay_text"] == "$40 – $60 per hour, ≈ $83.2K – $124.8K a year"
    assert pay("Solutions Architect") == (None, None), "EUR pay must stay unknown"
    assert pay("Developer Experience Engineer") == (None, None)


def case_filtered_leads_never_reach_telegram(wf):
    rows, (header, leads), requests = filter_scan(wf)
    assert sorted(requests) == FPASSED, "Jev was asked about a filtered lead"
    sent_keys = [m["lead_key"] for m in leads]
    assert sorted(sent_keys) == FPASSED, f"sent {sorted(titles(sent_keys))}"
    check_header(header, len(FPASSED))
    for k, r in rows.items():
        if r["filter_result"] != "passed":
            assert not r["sent_at"] and not r["scoring_state"], f"filtered lead scored or sent: {FKEY[k]['title']}"


def case_messages_show_pay_and_location(wf):
    _, (_, leads), _ = filter_scan(wf)
    text = {FKEY[m["lead_key"]]["title"]: m["text"] for m in leads}
    assert "Pay: Pay not listed" in text["Developer Experience Engineer"]
    assert "Location: Location unclear" in text["Solutions Engineer"]
    ramp_style = text["Software Engineer, Frontend"]
    assert "Pay: $143.2K – $284K • Offers Equity" in ramp_style, ramp_style
    assert "Location: New York, NY (HQ) · Hybrid · Remote (US) option" in ramp_style, ramp_style
    assert "Location: Plano, TX · Hybrid" in text["Senior Product Engineer"]
    assert "Pay: €91.4K – €171.7K" in text["Solutions Architect"], "non-USD pay text not shown"
    assert "SDKs &amp; APIs" in text["Developer Relations Engineer, SDKs & APIs"], "HTML not escaped"


def case_rule_changes_apply_to_saved_leads(wf):
    # A lead filtered under one config passes after the rule changes, and is judged
    # and sent then.
    reset_test_tables()
    pm = FBY_TITLE["Product Manager, Developer Platform"]  # base $150K-$180K
    others = [k for k in FPASSED if k != pm]
    header, leads = sent(run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE,
                                  judged=others, payFloor=200000))
    rows = rows_by_key()
    assert rows[pm]["filter_result"] == "pay_floor" and not rows[pm]["sent_at"]
    assert pm not in {m["lead_key"] for m in leads}

    header, leads = sent(run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=[pm]))
    rows = rows_by_key()
    assert rows[pm]["filter_result"] == "passed", rows[pm]["filter_result"]
    assert [m["lead_key"] for m in leads] == [pm], "only the newly passing lead should be sent"
    assert rows[pm]["sent_at"]


def case_config_defaults_match_spec(wf):
    cfg = config_defaults(wf)
    assert cfg["ashbyBoards"] == ["n8n", "posthog", "ramp"], cfg["ashbyBoards"]
    assert cfg["greenhouseBoards"] == ["instacart"], cfg["greenhouseBoards"]
    assert cfg["leverBoards"] == ["palantir", "spotify"], cfg["leverBoards"]
    assert cfg["payFloor"] == 180000
    excluded = [t.lower() for t in cfg["excludedTitles"]]
    assert excluded == ["accountant", "finance", "legal", "counsel", "paralegal", "hr", "people ops",
                        "people operations", "office manager", "facilities", "executive assistant"], excluded
    assert "marketing" not in excluded, "DevRel roles often sit in Marketing"
    assert [t.lower() for t in cfg["excludedTitleOverrides"]] == [
        "engineer", "engineering", "developer", "software", "swe", "architect", "programmer",
        "advocate", "devrel", "product manager", "pm", "platform"]
    rules = cfg["locationRules"]
    assert rules["usRemote"] is True
    (dfw,) = rules["metros"]
    for city in ["Dallas", "Fort Worth", "DFW", "Frisco", "Plano", "Irving", "Arlington", "Richardson",
                 "Addison", "McKinney", "Allen", "Carrollton", "Grapevine", "Southlake", "Denton",
                 "Garland", "Lewisville", "Coppell"]:
        assert city in dfw["cities"], city
    assert "Austin" not in dfw["cities"]
    assert dfw["workplaceTypes"] == ["Remote", "Hybrid", "OnSite"]
    assert [f["name"] for f in cfg["roleFamilies"]] == [
        "DevEx/Product PM", "FDE/Solutions", "Product/Frontend Engineering", "DevRel/DevEx"]
    assert all(f["titleKeywords"] and f["description"] for f in cfg["roleFamilies"])
    fde = next(f["description"] for f in cfg["roleFamilies"] if f["name"] == "FDE/Solutions")
    assert "technical or solutions consultants" in fde and "Not accounting" in fde, fde
    # Rahat, 2026-10-01 (#11): account management and customer success aren't FDE/Solutions.
    assert "Not account management or customer success management" in fde and "technical account managers" in fde, fde
    # Rahat, 2026-10-01: customer success engineers stay in; partner, alliances and SI roles are out.
    assert "customer success engineers" in fde and "systems-integrator" in fde, fde
    # Scoring (spec #1, issue #9).
    assert cfg["weights"] == WEIGHTS, cfg["weights"]
    assert cfg["minFitScore"] == 60 and cfg["freshnessWindowDays"] == 30 and cfg["dailyCap"] == 10
    assert cfg["targetSeniority"] == TARGET
    assert cfg["jevModel"] == "jev-1.13.0"
    assert cfg["profileSummary"].strip(), "profile summary is empty"
    note = next(n["parameters"]["content"] for n in wf["nodes"]
                if n["type"] == "n8n-nodes-base.stickyNote"
                and n["parameters"]["content"].startswith("## Job Scout config"))
    for field in cfg:
        assert f"**{field}**" in note, f"config sticky note doesn't explain {field}"

# ---------- Greenhouse and Lever ----------

# Per posting, what Normalize postings makes of the fields that differ by ATS:
# (workplace_type, secondary_locations, pay_text, pay_min, pay_max)
NORMALIZED = {
    "Senior Software Engineer II, AI Labs & Foundations": ("Remote", "", "$192K – $242.5K (by location)", 192000, 242500),
    "Senior AI Solutions Sales Executive": ("Remote", "", "$122K – $154K (by location)", 122000, 154000),
    "Billing Operations Associate": ("Remote", "", "$28.37 – $32.94 an hour, ≈ $59K – $68.5K a year (by location)",
                                     59010, 68515),
    "Senior Product Manager, AI Control Studio": ("Remote", "", "194K – 204.5K CAD", None, None),
    "iOS Developer": ("Hybrid", "", "", None, None),
    "Backend Engineer - Music": ("Remote", "Boston, MA; Miami, FL", "", None, None),
    "Senior Software Engineer - Enterprise AI": ("Remote", "", "", None, None),
    "Android Engineer - Experience": ("Hybrid", "Stockholm", "", None, None),
    "Lead, Global Markets Strategy": ("Hybrid", "", "", None, None),
    "Senior Legal Counsel - Music Publishing": ("OnSite", "", "", None, None),
    "Senior Developer Advocate, Data": ("Hybrid", "", "$190K – $220K; 240K – 260K CAD", 190000, 220000),
    "Staff Product Engineer": ("Hybrid", "", "$200K – $240K", 200000, 240000),
    "Frontend Platform Engineer": ("", "", "", None, None),
    "Developer Experience Lead": ("", "", "", None, None),
    "Solutions Engineer, Commercial": ("Hybrid", "", "$150K – $170K", 150000, 170000),
    "Senior Integrations Engineer": ("Remote", "", "$150K – $170K", 150000, 170000),
    "Solutions Engineer, Dallas": ("OnSite", "", "$185K – $230K a year", 185000, 230000),
    "Partner Engineer, Integrations": ("Hybrid", "Remote (US)", "", None, None),
    "Senior Frontend Engineer, Austin": ("OnSite", "", "$190K – $220K a year", 190000, 220000),
    "Product Engineer, Payments": ("Remote", "", "$12K – $14K a month", 144000, 168000),
    "Contract Frontend Engineer": ("Remote", "", "$90.00 – $110.00 an hour, ≈ $187.2K – $228.8K a year", 187200, 228800),
    "Partner Solutions Engineer": ("", "", "", None, None),
    "Developer Advocate, EMEA": ("Remote", "London", "90K – 110K EUR a year", None, None),
}


def expected_row(key, now):
    """The saved lead for a Greenhouse or Lever posting, worked out from the fixture."""
    ats, board, job_id = key.split(":", 2)
    j = ALL_KEYS[key]
    workplace, secondary, pay_text, pay_min, pay_max = NORMALIZED[j["title"]]
    if ats == "greenhouse":
        company, location, apply_url = j["company_name"], j["location"]["name"], j["absolute_url"]
    else:
        company, location, apply_url = board, j["categories"]["location"], j["applyUrl"]
    return {"lead_key": key, "ats": ats, "board": board, "job_id": job_id, "company": company,
            "title": j["title"], "location_text": location, "workplace_type": workplace,
            "secondary_locations": secondary, "pay_text": pay_text, "pay_min": pay_min, "pay_max": pay_max,
            "posting_url": j["jobUrl"], "apply_url": apply_url, "status": "new", "closed_at": None,
            "filter_result": EXPECTED[j["title"]], "published_at": now - AGE[key] * DAY}


def check_rows(rows, keys, now):
    for k in keys:
        r, want = rows[k], expected_row(k, now)
        when = want.pop("published_at")
        got = {f: r[f] for f in want}
        assert got == want, f"{want['title']}: {[(f, got[f], want[f]) for f in want if got[f] != want[f]]}"
        assert abs((parse_time(r["published_at"]) - when).total_seconds()) < 5, (want["title"], r["published_at"])
        assert r["first_seen_at"] and r["last_seen_at"], want["title"]


def case_greenhouse_and_lever_postings_become_leads(wf):
    # Real postings from all three ATSes in one scan: every one becomes a lead with
    # the same fields, keyed ats:board:job_id, and only those that pass are judged.
    reset_test_tables()
    now = datetime.now(timezone.utc)
    judged = PASSED + passing(GHKEY) + passing(LVKEY)
    run_data = run_scan(wf, boards=[("lever", LV_BOARD, LV_FIXTURE), ("greenhouse", GH_BOARD, GH_FIXTURE),
                                    ("ashby", BOARD, FIXTURE)], judged=judged, minFitScore=101)
    rows = rows_by_key()
    assert sorted(rows) == sorted([*KEY, *GHKEY, *LVKEY]), "every posting should be one lead"
    ashby_fields = {f for f, v in rows[PASSED[0]].items() if v not in (None, "")}
    for k in [*GHKEY, *LVKEY]:
        missing = {f for f in ashby_fields if rows[k][f] in (None, "")} - {
            "secondary_locations", "pay_text", "pay_min", "pay_max", "workplace_type", "location_basis",
            "role_family", "seniority_level", "scoring_state", "scored_at", "scoring_fingerprint", "jev_model",
            "jev_answers", "sub_role_family", "sub_stack", "sub_domain", "sub_seniority", "sub_location",
            "sub_freshness", "sub_referral", "fit_score", "selection_reason"}
        assert not missing, f"{ALL_KEYS[k]['title']} lacks {missing}"
    check_rows(rows, [*GHKEY, *LVKEY], now)
    assert rows[BY_TITLE["Backend Engineer - Music"]]["location_basis"] == "us_remote"
    # Greenhouse content is HTML-escaped HTML: Jev gets plain text.
    body = jev_requests(run_data)[BY_TITLE["Senior Software Engineer II, AI Labs & Foundations"]]
    text = body["state"]["posting"]["description"]
    assert "Instacart" in text and "<" not in text and "&lt;" not in text and "&amp;" not in text, text[:200]
    assert body["state"]["posting"]["company"] == "Instacart"
    lever = jev_requests(run_data)[BY_TITLE["Senior Software Engineer - Enterprise AI"]]["state"]["posting"]
    assert lever["location"] == "New York, NY · Remote", lever["location"]


def case_greenhouse_and_lever_location_and_pay_rules(wf):
    # Synthetic postings: Lever's live "onsite" and the docs' "on-site" are both
    # on-site; Greenhouse's workplace type comes from the location name; DFW hybrid or
    # on-site passes, Austin fails, a "Remote (US)" secondary location counts, no
    # location is "Location unclear"; Greenhouse OTE ranges and Lever monthly pay are
    # handled like Ashby's, hourly pay counts at 2,080 hours a year (an hourly range
    # above the floor passes), and non-USD pay is unknown.
    reset_test_tables()
    now = datetime.now(timezone.utc)
    keys = [*GHFKEY, *LVFKEY]
    want_sent = passing(GHFKEY) + passing(LVFKEY)
    run_data = run_scan(wf, daily_cap=50, boards=[("greenhouse", GHF_BOARD, GHF_FIXTURE), ("lever", LVF_BOARD, LVF_FIXTURE)],
                        judged=want_sent)
    rows = rows_by_key()
    assert sorted(rows) == sorted(keys)
    check_rows(rows, keys, now)
    for title, basis in BASIS.items():
        if BY_TITLE[title] in rows:
            assert rows[BY_TITLE[title]]["location_basis"] == basis, (title, rows[BY_TITLE[title]]["location_basis"])
    assert rows[BY_TITLE["Partner Engineer, Integrations"]]["location_basis"] == "us_remote"
    header, leads = sent(run_data)
    check_sent_order(leads, fit_order(want_sent))
    text = {ALL_KEYS[m["lead_key"]]["title"]: m["text"] for m in leads}
    assert "Pay: $90.00 – $110.00 an hour, ≈ $187.2K – $228.8K a year" in text["Contract Frontend Engineer"], \
        text["Contract Frontend Engineer"]
    assert "Location: Location unclear" in text["Partner Solutions Engineer"]
    assert "Location: London · Hybrid · Remote (US) option" in text["Partner Engineer, Integrations"]
    # The Greenhouse department (Marketing) never reaches Jev.
    body = jev_requests(run_data)[BY_TITLE["Senior Developer Advocate, Data"]]
    assert "Marketing" not in json.dumps(body["state"]), "the department reached Jev"


# ---------- Closed postings ----------

def without(fixture, keys, ats="ashby"):
    """The board response minus the postings with these lead keys."""
    ids = {k.split(":", 2)[2] for k in keys}
    out = copy.deepcopy(fixture)
    kept = [j for j in jobs_of(out, ats) if str(j["id"]) not in ids]
    if ats == "lever":
        return kept
    out["jobs"] = kept
    return out


def case_missing_posting_is_closed_quietly(wf):
    # A posting gone from a board fetched successfully closes its lead, whatever the
    # status: a sent lead, an unsent New lead and a filtered one. Nothing is sent about
    # it and a closed New lead is never sent; the next leads in fit order go instead.
    reset_test_tables()
    order = fit_order(FPASSED)
    run_data = run_scan(wf, daily_cap=2, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED)
    check_sent_order(sent(run_data)[1], order[:2])
    gone_sent, gone_new, gone_filtered = order[0], order[2], FBY_TITLE["Product Engineer"]
    gone = [gone_sent, gone_new, gone_filtered]
    before = time.time()
    header, leads = sent(run_scan(wf, daily_cap=2, board=FILTER_BOARD, fixture=without(FILTER_FIXTURE, gone)))
    check_header(header, 2)
    check_sent_order(leads, order[3:5])
    rows = rows_by_key()
    for k in gone:
        assert rows[k]["closed_at"], f"{FKEY[k]['title']} not closed"
        assert parse_time(rows[k]["closed_at"]).timestamp() >= before - 5
    assert all(not r["closed_at"] for k, r in rows.items() if k not in gone), "an open posting was closed"
    assert rows[gone_new]["status"] == "new" and not rows[gone_new]["sent_at"]
    assert rows[gone_new]["selection_reason"] == "closed", rows[gone_new]["selection_reason"]
    assert rows[gone_sent]["sent_at"], "closing must not clear sent_at"


def case_failed_fetch_closes_nothing(wf):
    # One board's fetch fails: its leads stay open (and aren't judged), while a missing
    # posting on the board that was fetched is closed.
    reset_test_tables()
    lv_passed = passing(LVFKEY)
    run_scan(wf, boards=[("ashby", FILTER_BOARD, FILTER_FIXTURE), ("lever", LVF_BOARD, LVF_FIXTURE)],
             judged=FPASSED + lv_passed, minFitScore=101)
    gone = BY_TITLE["Solutions Engineer, Dallas"]
    run_data = run_scan(wf, boards=[("ashby", FILTER_BOARD, FAILED_FETCH),
                                    ("lever", LVF_BOARD, without(LVF_FIXTURE, [gone], "lever"))],
                        minFitScore=101)
    rows = rows_by_key()
    assert sorted(rows) == sorted([*FKEY, *LVFKEY]), "a failed fetch must not remove leads"
    assert not [FKEY[k]["title"] for k in FKEY if rows[k]["closed_at"]], "the failed board's leads were closed"
    assert rows[gone]["closed_at"], "the missing posting on the fetched board wasn't closed"
    assert [k for k in LVFKEY if rows[k]["closed_at"]] == [gone]
    # The failed board adds nothing to the counts.
    header, leads = sent(run_data)
    check_empty_day(header, leads, scanned=len(LVFKEY) - 1,
                    filtered=sum(EXPECTED[j["title"]] != "passed" for k, j in LVFKEY.items() if k != gone))


def case_reappearing_posting_clears_closed_at(wf):
    reset_test_tables()
    top = fit_order(list(SKEY))[0]
    run_scan(wf, board=SCORING_BOARD, fixture=SCORING_FIXTURE, judged=list(SKEY), minFitScore=101)
    run_scan(wf, board=SCORING_BOARD, fixture=without(SCORING_FIXTURE, [top]), minFitScore=101)
    assert rows_by_key()[top]["closed_at"], "the missing posting wasn't closed"
    header, leads = sent(run_scan(wf, daily_cap=1, board=SCORING_BOARD, fixture=SCORING_FIXTURE))
    row = rows_by_key()[top]
    assert row["closed_at"] is None, row["closed_at"]
    check_sent_order(leads, [top])
    assert row["sent_at"]

# ---------- action links: Applied and Referral ----------

def case_action_links_are_signed_get_webhooks(wf):
    # Pinned triggers don't check their own parameters, so check them here: both action
    # webhooks are GET on fixed paths (a ":param" path would get a UUID prefix), answer
    # through Show page and ignore bots. The page is HTML with the status the action
    # chose. Every Code node that signs uses the same code, and the config holds no secret.
    nodes = {n["name"]: n for n in wf["nodes"]}
    for name, path in ((APPLIED_TRIGGER, "job-scout/applied"), (REFERRAL_TRIGGER, "job-scout/referral")):
        p = nodes[name]["parameters"]
        assert (p.get("httpMethod"), p["path"], p["responseMode"]) == ("GET", path, "responseNode"), name
        assert p["options"].get("ignoreBots") is True, f"{name}: Ignore Bots is off"
        assert p.get("authentication", "none") == "none", f"{name}: the signature is the auth"
    show = nodes[RESPOND_NODE]["parameters"]
    assert show["respondWith"] == "text" and show["responseBody"] == "={{ $json.html }}"
    assert show["options"]["responseCode"] == "={{ $json.http_status }}"
    headers = {h["name"].lower(): h["value"] for h in show["options"]["responseHeaders"]["entries"]}
    assert headers["content-type"].startswith("text/html"), headers
    blocks = set()
    for name in SIGNED_NODES:
        code = nodes[name]["parameters"]["jsCode"]
        blocks.add(code[code.index("// ---- Signed action links"):code.index("// ---- end of signed action links")])
    assert len(blocks) == 1, "the Code nodes sign links differently"
    assert not [k for k in config_defaults(wf) if "secret" in k.lower() or "sign" in k.lower()], "secret in config"


def case_applied_from_new_sets_status_and_date(wf):
    # The first run makes the signing secret and later runs reuse it. Tapping Applied in a
    # lead message marks that New lead Applied with the date; a second tap changes nothing.
    reset_test_tables()
    run_data = run_scan(wf, judged=PASSED)
    assert ran(run_data, "Generate signing secret"), "the first run didn't make a signing secret"
    secret = signing_secret()
    assert len(secret) == 64 and all(c in "0123456789abcdef" for c in secret), "secret isn't 32 bytes of hex"
    leads = sent(run_data)[1]
    check_lead_messages(leads, rows_by_key())
    key = leads[0]["lead_key"]
    _, query = link_query(leads[0]["applied_url"])
    before = time.time()
    page, run_data = run_action(wf, APPLIED_TRIGGER, query)
    assert not ran(run_data, "Generate signing secret") and signing_secret() == secret, "the secret changed"
    check_page(page, 200, "Marked applied")
    assert page["lines"][0] == f"<b>{html_escape(ALL_KEYS[key]['title'], quote=False)}</b> at {BOARD}", page["lines"]
    rows = rows_by_key()
    assert rows[key]["status"] == "applied", rows[key]["status"]
    assert parse_time(rows[key]["applied_at"]).timestamp() >= before - 5, rows[key]["applied_at"]
    assert all(r["status"] == "new" and not r["applied_at"] for k, r in rows.items() if k != key)
    page, run_data = run_action(wf, APPLIED_TRIGGER, query)
    check_page(page, 200, "Already marked applied")
    assert not ran(run_data, "Mark applied"), "a second tap wrote to the table"
    assert rows_by_key()[key] == rows[key]


def case_applied_from_picked_but_not_passed(wf):
    reset_test_tables()
    run_scan(wf, judged=PASSED, minFitScore=101)
    picked, passed = PASSED[0], PASSED[1]
    update_lead(picked, {"status": "picked"})
    page, _ = tap(wf, "applied", picked)
    check_page(page, 200, "Marked applied")
    row = rows_by_key()[picked]
    assert row["status"] == "applied" and row["applied_at"], row["status"]
    update_lead(passed, {"status": "passed"})
    page, run_data = tap(wf, "applied", passed)
    check_page(page, 409, "Not changed")
    assert not ran(run_data, "Mark applied")
    row = rows_by_key()[passed]
    assert row["status"] == "passed" and not row["applied_at"], row["status"]


def case_tampered_link_changes_nothing(wf):
    # A link whose signature doesn't match its action and lead gets the invalid page (403)
    # and changes no row.
    reset_test_tables()
    run_scan(wf, judged=PASSED, minFitScore=101)
    key, other = PASSED[0], PASSED[1]
    good = sign("applied", key)
    attempts = [
        ("applied", good[:-1] + ("0" if good[-1] != "0" else "1")),  # one character changed
        ("applied", sign("referral", key)),  # the Referral signature
        ("applied", sign("applied", other)),  # another lead's signature
        ("applied", False),  # no signature
        ("applied", good[:16]),  # cut short
        ("referral", sign("applied", key)),
        ("referral", sign("referral", other)),
    ]
    before = sorted(lead_rows(), key=lambda r: r["id"])
    for action, sig in attempts:
        page, run_data = tap(wf, action, key, sig=sig)
        check_page(page, 403, "Invalid link")
        assert not ran(run_data, "Mark applied") and not ran(run_data, "Save referral"), (action, "acted")
    assert sorted(lead_rows(), key=lambda r: r["id"]) == before, "a tampered link changed a lead"
    assert table_rows(REFERRALS_TABLE) == [], "a tampered link saved a referral"
    page, _ = tap(wf, "applied", f"ashby:{BOARD}:no-such-posting")
    check_page(page, 404, "Lead not found")


def case_applied_lead_is_never_sent(wf):
    reset_test_tables()
    order = fit_order(FPASSED)
    run_data = run_scan(wf, daily_cap=2, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED)
    check_sent_order(sent(run_data)[1], order[:2])
    tap(wf, "applied", order[2])  # New and not sent yet: it would have been next
    header, leads = sent(run_scan(wf, daily_cap=2, board=FILTER_BOARD, fixture=FILTER_FIXTURE))
    check_header(header, 2)
    check_sent_order(leads, order[3:5])
    row = rows_by_key()[order[2]]
    assert row["status"] == "applied" and not row["sent_at"], row["status"]


def case_referral_raises_company_fit_and_flags_messages(wf):
    # Referral on one testco lead: testco joins referrals, its unsent leads get the
    # referral points at once (no Jev calls), and n8n's leads don't. A posting testco lists
    # later gets them on its first scan, and testco messages say "Referral available".
    # With a minimum of 66, two testco leads (64 and 65) reach it only with the referral.
    reset_test_tables()
    floor = 66
    late = FBY_TITLE["Frontend Engineer"]
    boards = lambda testco: [("ashby", FILTER_BOARD, testco), ("ashby", BOARD, FIXTURE)]  # noqa: E731
    first = [k for k in FPASSED if k != late] + PASSED
    run_data = run_scan(wf, boards=boards(without(FILTER_FIXTURE, [late])), judged=first, daily_cap=1,
                        minFitScore=floor)
    sent_first = [m["lead_key"] for m in sent(run_data)[1]]
    check_sent_order(sent(run_data)[1], fit_order(first, min_fit=floor)[:1])
    before = rows_by_key()
    unsent = [k for k, r in before.items() if k.split(":")[1] == FILTER_BOARD and not r["sent_at"]]
    tapped = next(k for k in FPASSED if k in unsent)
    start = time.time()
    page, _ = tap(wf, "referral", tapped, minFitScore=floor)
    check_page(page, 200, "Referral saved")
    assert f"{len(unsent)} unsent leads were rescored." in page["lines"], page["lines"]
    assert any("(+5)" in line for line in page["lines"]), page["lines"]
    refs = table_rows(REFERRALS_TABLE)
    assert [(r["company_key"], r["company"], r["lead_key"]) for r in refs] == [(FILTER_BOARD, FILTER_BOARD, tapped)]
    assert parse_time(refs[0]["set_at"]).timestamp() >= start - 5
    after = rows_by_key()
    raised = 0
    for k, r in after.items():
        b, title = before[k], ALL_KEYS[k]["title"]
        if k not in unsent:
            assert (r["sub_referral"], r["fit_score"]) == (b["sub_referral"], b["fit_score"]), title
            continue
        assert r["sub_referral"] == 1, title
        if b["fit_score"] is None:
            continue
        assert r["fit_score"] == b["fit_score"] + 5, (title, b["fit_score"], r["fit_score"])
        if b["selection_reason"] in ("below_min_fit", "eligible"):
            assert r["selection_reason"] == ("eligible" if r["fit_score"] >= floor else "below_min_fit"), title
            raised += b["selection_reason"] == "below_min_fit" and r["selection_reason"] == "eligible"
    assert raised == 2, f"{raised} leads crossed the minimum, expected 2"
    # A second tap, from another testco lead, changes nothing.
    page, _ = tap(wf, "referral", next(k for k in unsent if k != tapped), minFitScore=floor)
    check_page(page, 200, "Referral already saved")
    assert table_rows(REFERRALS_TABLE) == refs
    assert rows_by_key() == after, "a second tap changed leads"
    # The next scan: the new testco posting gets the points too.
    run_data = run_scan(wf, boards=boards(FILTER_FIXTURE), judged=[late], daily_cap=30, minFitScore=floor)
    rows = rows_by_key()
    assert rows[late]["sub_referral"] == 1, "a new lead from the company has no referral"
    assert rows[late]["fit_score"] == expected_fit(late, referred={FILTER_BOARD}), rows[late]["fit_score"]
    leads = sent(run_data)[1]
    remaining = [k for k in FPASSED + PASSED if k not in sent_first]
    check_sent_order(leads, fit_order(remaining, min_fit=floor, referred={FILTER_BOARD}))
    check_lead_messages(leads, rows)
    for m in leads:
        lines, has = m["text"].split("\n"), m["lead_key"].split(":")[1] == FILTER_BOARD
        assert (lines[2] == "Referral available") == has, (ALL_KEYS[m["lead_key"]]["title"], lines[:3])
        assert ("· referral 5" in m["text"]) == has, m["text"]


CASES = [
    case_telegram_nodes_send_what_they_receive,
    case_jev_and_claude_nodes_call_what_they_receive,
    case_config_defaults_match_spec,
    case_one_lead_per_posting,
    case_daily_ping_shape,
    case_rescan_creates_no_duplicates_and_sends_no_leads,
    case_cap_and_carry_over_by_fit,
    case_filters_store_the_failed_rule,
    case_filtered_leads_never_reach_telegram,
    case_messages_show_pay_and_location,
    case_developer_advocate_under_marketing_gets_devrel,
    case_rule_changes_apply_to_saved_leads,
    case_fit_score_from_sub_scores_and_weights,
    case_weight_change_reranks_without_jev,
    case_below_minimum_never_sent,
    case_no_role_family_never_sent,
    case_freshness_window_counts_from_first_seen,
    case_changed_profile_summary_rejudges_unsent_leads,
    case_jev_failure_leaves_lead_unscored,
    case_claude_failure_still_sends_lead,
    case_empty_day_message_counts,
    case_every_board_failing_crashes_the_scan,
    case_crash_alert_names_the_failed_step,
    case_message_shows_fit_breakdown_and_fit_line,
    case_pay_found_in_description,
    case_greenhouse_and_lever_postings_become_leads,
    case_greenhouse_and_lever_location_and_pay_rules,
    case_missing_posting_is_closed_quietly,
    case_failed_fetch_closes_nothing,
    case_reappearing_posting_clears_closed_at,
    case_action_links_are_signed_get_webhooks,
    case_applied_from_new_sets_status_and_date,
    case_applied_from_picked_but_not_passed,
    case_tampered_link_changes_nothing,
    case_applied_lead_is_never_sent,
    case_referral_raises_company_fit_and_flags_messages,
]


def main():
    wanted = sys.argv[1:]
    workflow = find_workflow()
    failed = 0
    for case in CASES:
        name = case.__name__[len("case_"):]
        if wanted and not any(w in name for w in wanted):
            continue
        try:
            case(workflow)
            print(f"PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {e}")
            if os.environ.get("VERBOSE"):
                traceback.print_exc()
    reset_test_tables()
    print(f"\n{'FAILED' if failed else 'OK'}: {failed} failing")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
