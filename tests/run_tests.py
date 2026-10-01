#!/usr/bin/env python3
"""Job Scout tests: run the scan trigger through n8n's MCP test_workflow tool.

Each case clears the jobscout_test_ tables, runs the "Daily scan" trigger with
pinned data (fixture board response, test config, Jev and Claude replies, fake
Telegram replies), and then checks only external behavior: rows in the test tables
and the items that reached the Jev, Claude and Telegram nodes. The pinned config
starts from the defaults in the workflow's "Job Scout config" node, so the cases
test the shipped rules, weights and thresholds.

  python3 tests/run_tests.py            # all cases
  python3 tests/run_tests.py cap        # cases whose name contains "cap"

Stdlib only. Needs the local n8n and N8N_API_KEY + N8N_MCP_TOKEN in .env.
"""
import copy
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import n8n_mcp  # noqa: E402

API = os.environ.get("N8N_API_URL", "http://localhost:5678/api/v1")
WORKFLOW_NAME = "Job Scout"
TRIGGER = "Daily scan"
TEST_PREFIX = "jobscout_test_"
LEADS_TABLE = TEST_PREFIX + "leads"
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
# A real Jev response, recorded 2026-09-30 for n8n's Senior Developer Advocate posting.
JEV_RECORDED = json.loads((FIXTURES / "jev-response.json").read_text())

# Nodes that reach the outside world. test_workflow does not pin anything by
# itself, so every one of these must be pinned or the test would really call it.
EXTERNAL_TYPES = {"n8n-nodes-base.telegram", "n8n-nodes-base.httpRequest", "@n8n/n8n-nodes-langchain.anthropic"}
HEADER_NODE = "Send header"
LEAD_NODE = "Send lead message"
JEV_NODE = "Ask Jev"
FIT_NODE = "Write fit line"

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
    # The MCP server rate-limits bursts of calls (HTTP 429); wait and retry.
    for attempt in range(6):
        try:
            return n8n_mcp.call(tool, args)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(10 * (attempt + 1))


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
    table = find_table(LEADS_TABLE)
    if table is None:
        return  # the workflow creates it on its first run
    assert table["name"].startswith(TEST_PREFIX), "refusing to clear a non-test table"
    api("DELETE", f"/data-tables/{table['id']}/rows/clear")


def lead_rows():
    table = find_table(LEADS_TABLE)
    if table is None:
        return []
    out = mcp("get_data_table_rows", {"dataTableId": table["id"], "projectId": table["projectId"],
                                      "limit": 100})
    assert out["count"] <= 100, "test table has more rows than one page"
    return out["rows"]


def rows_by_key():
    return {r["lead_key"]: r for r in lead_rows()}


def set_first_seen(key, when):
    """Backdate a test lead's first sighting, as if an earlier scan had found it."""
    table = find_table(LEADS_TABLE)
    assert table["name"].startswith(TEST_PREFIX)
    body = {"filter": {"type": "and", "filters": [{"columnName": "lead_key", "condition": "eq", "value": key}]},
            "data": {"first_seen_at": when.isoformat().replace("+00:00", "Z")}}
    req = urllib.request.Request(f"{API}/data-tables/{table['id']}/rows/update", method="PATCH",
                                 data=json.dumps(body).encode(), headers={
                                     "X-N8N-API-KEY": ENV["N8N_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


# ---------- fixtures: dates, keys and Jev answers ----------

DAY = timedelta(days=1)


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def ages(fixture):
    """Each posting's age in whole days once rebased: the newest is 1 day old, and the
    others keep their distance from it, rounded to whole days."""
    newest = max(parse_time(j["publishedAt"]) for j in fixture["jobs"])
    return {j["id"]: round((newest - parse_time(j["publishedAt"])) / DAY) + 1 for j in fixture["jobs"]}


def rebase(fixture, now):
    """The fixture with publishedAt moved to whole days before now, so the freshness
    window and freshness points don't drift as the recorded dates age."""
    out = copy.deepcopy(fixture)
    age = ages(fixture)
    for j in out["jobs"]:
        j["publishedAt"] = (now - age[j["id"]] * DAY).isoformat().replace("+00:00", "Z")
    return out


def keyed(fixture, board):
    return {f"ashby:{board}:{j['id']}": j for j in fixture["jobs"] if j.get("isListed", True)}


JOBS = [j for j in FIXTURE["jobs"] if j.get("isListed", True)]
KEY = keyed(FIXTURE, BOARD)
FKEY = keyed(FILTER_FIXTURE, FILTER_BOARD)
SKEY = keyed(SCORING_FIXTURE, SCORING_BOARD)
ALL_KEYS = {**KEY, **FKEY, **SKEY}
AGE = {**{k: ages(FIXTURE)[j["id"]] for k, j in KEY.items()},
       **{k: ages(FILTER_FIXTURE)[j["id"]] for k, j in FKEY.items()},
       **{k: ages(SCORING_FIXTURE)[j["id"]] for k, j in SKEY.items()}}
BY_TITLE = {j["title"]: k for k, j in ALL_KEYS.items()}  # titles are unique across fixtures
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
    # scoring fixture
    "Developer Advocate, Platform": "passed",  # pay only in the description, below the floor
    "Senior Product Engineer, Growth": "passed",  # pay only in the description
    "Senior Frontend Engineer, Dashboards": "passed",  # posted 41 days ago: no freshness points
}
# location_basis that Apply hard filters gives each passing posting.
BASIS = {"Solutions Engineer": "unclear", "Senior Product Engineer": "metro", "Frontend Engineer": "metro"}
PASSED = [k for k in KEY if EXPECTED[KEY[k]["title"]] == "passed"]
FPASSED = sorted(k for k, j in FKEY.items() if EXPECTED[j["title"]] == "passed")

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
}
# Jev's pick for the base salary question, for postings whose pay is only in the description.
JEV_PAY = {"Developer Advocate, Platform": "$150,000 - $170,000 USD",
           "Senior Product Engineer, Growth": "$190K–$230K"}
FAIL = "fail"  # in place of a spec: the request failed after its retries
FAILED_RESPONSE = {"error": {"message": "The service is receiving too many requests from you",
                             "description": "Overloaded", "name": "NodeApiError", "httpCode": "529"}}
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


def expected_points(key, weights=WEIGHTS, target=TARGET):
    title = ALL_KEYS[key]["title"]
    family, p, stack, names, level, domain = JEV[title]
    sub = {
        "roleFamily": r3(p if family != NONE else 1 - p),
        "stack": r3(names * stack / 4 + (1 - names) * 0.5),
        "seniority": 1 if level in target else 0.5 if level == "not_stated" else 0.2,
        "location": {"us_remote": 1, "metro": 1, "unclear": 0.5}[BASIS.get(title, "us_remote")],
        "domain": r3(domain / 3),
        "freshness": max(0, 1 - (AGE[key] + 1e-4) / 30),  # a scan runs seconds after the rebase
        "referral": 0,
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


def run_scan(workflow, daily_cap=10, board=BOARD, fixture=FIXTURE, judged=(), jev=None, fit_lines=None, **config):
    """Runs one scan. `judged` is the lead keys expected to reach Jev; their pinned
    answers come from JEV (or `jev`, by title, where FAIL means a failed request), in
    the order Build Jev requests sends them. `fit_lines` are Claude's pinned replies,
    in send order."""
    cfg = config_defaults(workflow)
    cfg.update({"ashbyBoards": [board], "telegramChatId": FAKE_CHAT_ID,
                "dailyCap": daily_cap, "tablePrefix": TEST_PREFIX}, **config)
    judged = sorted(judged)
    jev = jev or {}
    responses = []
    for k in judged:
        title = ALL_KEYS[k]["title"]
        responses.append(FAILED_RESPONSE if jev.get(title) == FAIL else jev_response(title))
    lines = fit_lines or [f"Pinned fit line {i + 1}." for i in range(daily_cap)]
    pin = {
        TRIGGER: [{"json": {}}],
        "Job Scout config": [{"json": cfg}],
        "Fetch Ashby board": [{"json": rebase(fixture, datetime.now(timezone.utc))}],
        JEV_NODE: [{"json": r} for r in responses] or [{"json": {}}],
        FIT_NODE: [{"json": {"content": [{"type": "text", "text": t}], "merged_response": t}} for t in lines]
        or [{"json": {}}],
        HEADER_NODE: [{"json": {"ok": True, "result": {"message_id": 1}}}],
        LEAD_NODE: [{"json": {"ok": True, "result": {"message_id": 2}}}],
    }
    unpinned = [n["name"] for n in workflow["nodes"]
                if n["type"] in EXTERNAL_TYPES and n["name"] not in pin and not n.get("disabled")]
    assert not unpinned, f"external nodes without pin data: {unpinned}"

    result = mcp("test_workflow", {"workflowId": workflow["id"], "pinData": pin,
                                   "triggerNodeName": TRIGGER, "timeout": 180})
    assert result["status"] == "success", f"scan failed: {result}"
    execution = mcp("get_workflow_execution", {"workflowId": workflow["id"],
                                               "executionId": result["executionId"],
                                               "includeData": True})
    run_data = execution["data"]["resultData"]["runData"]
    asked = sorted(i["lead_key"] for i in items_reaching(run_data, JEV_NODE))
    assert asked == judged, (f"Jev was asked about {[ALL_KEYS[k]['title'] for k in asked]}, "
                             f"expected {[ALL_KEYS[k]['title'] for k in judged]}")
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


def check_lead_messages(leads, rows_by_key):
    for msg in leads:
        assert msg["silent"] is True, f"lead message not silent: {msg['lead_key']}"
        assert msg["button_text"] == "Open posting", msg
        assert msg["button_url"] == ALL_KEYS[msg["lead_key"]]["jobUrl"], msg
        assert msg["button_url"] == rows_by_key[msg["lead_key"]]["posting_url"]


def check_header(header, n):
    assert len(header) == 1, f"expected one header, got {len(header)}"
    word = "lead" if n == 1 else "leads"
    assert header[0]["text"] == f"Job Scout: {n} new {word} today", header[0]
    assert header[0]["silent"] is False, "header must make a sound"


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


def case_rescan_creates_no_duplicates_and_sends_nothing(wf):
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
    assert header == [] and leads == [], f"second scan sent {len(header)} header(s), {len(leads)} lead(s)"


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
    assert header == [] and leads == [], "fourth scan sent messages"


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
    button = nodes[LEAD_NODE]["parameters"]["inlineKeyboard"]["rows"][0]["row"]["buttons"][0]
    assert button["text"] == "={{ $json.button_text }}"
    assert button["additionalFields"]["url"] == "={{ $json.button_url }}"


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
    assert jev.get("retryOnFail") is True and jev.get("onError") == "continueRegularOutput"
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
    reset_test_tables()
    failed = FBY_TITLE["Senior Product Engineer"]  # the top lead when scored
    header, leads = sent(run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=FPASSED,
                                  daily_cap=50, jev={"Senior Product Engineer": FAIL}))
    row = rows_by_key()[failed]
    assert row["scoring_state"] == "unscored" and row["fit_score"] is None and not row["sent_at"], row
    sent_keys = [m["lead_key"] for m in leads]
    assert failed not in sent_keys and sorted(sent_keys) == sorted(set(FPASSED) - {failed})
    # The next scan judges it again, and then it is sent.
    header, leads = sent(run_scan(wf, board=FILTER_BOARD, fixture=FILTER_FIXTURE, judged=[failed]))
    check_sent_order(leads, [failed])
    assert rows_by_key()[failed]["scoring_state"] == "scored"


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


CASES = [
    case_telegram_nodes_send_what_they_receive,
    case_jev_and_claude_nodes_call_what_they_receive,
    case_config_defaults_match_spec,
    case_one_lead_per_posting,
    case_daily_ping_shape,
    case_rescan_creates_no_duplicates_and_sends_nothing,
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
    case_message_shows_fit_breakdown_and_fit_line,
    case_pay_found_in_description,
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
