#!/usr/bin/env python3
"""Job Scout tests: run the scan trigger through n8n's MCP test_workflow tool.

Each case clears the jobscout_test_ tables, runs the "Daily scan" trigger with
pinned data (fixture board response, test config, fake Telegram replies), and then
checks only external behavior: rows in the test tables and the items that reached
the Telegram send nodes. The pinned config starts from the defaults in the workflow's
"Job Scout config" node, so the filter cases test the shipped rules.

  python3 tests/run_tests.py            # all cases
  python3 tests/run_tests.py cap        # cases whose name contains "cap"

Stdlib only. Needs the local n8n and N8N_API_KEY + N8N_MCP_TOKEN in .env.
"""
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
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
FIXTURE = json.loads((ROOT / "tests/fixtures/ashby-n8n.json").read_text())
BOARD = "n8n"
# Synthetic Ashby-shaped postings, one or two per filter rule and edge case.
FILTER_FIXTURE = json.loads((ROOT / "tests/fixtures/ashby-filters.json").read_text())
FILTER_BOARD = "testco"

# Nodes that reach the outside world. test_workflow does not pin anything by
# itself, so every one of these must be pinned or the test would really call it.
EXTERNAL_TYPES = {"n8n-nodes-base.telegram", "n8n-nodes-base.httpRequest"}
HEADER_NODE = "Send header"
LEAD_NODE = "Send lead message"

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


def run_scan(workflow, daily_cap=10, board=BOARD, fixture=FIXTURE, **config):
    cfg = config_defaults(workflow)
    cfg.update({"ashbyBoards": [board], "telegramChatId": FAKE_CHAT_ID,
                "dailyCap": daily_cap, "tablePrefix": TEST_PREFIX}, **config)
    pin = {
        TRIGGER: [{"json": {}}],
        "Job Scout config": [{"json": cfg}],
        "Fetch Ashby board": [{"json": fixture}],
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
    return execution["data"]["resultData"]["runData"]


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


# ---------- expectations from the fixtures ----------

JOBS = [j for j in FIXTURE["jobs"] if j.get("isListed", True)]
KEY = {f"ashby:{BOARD}:{j['id']}": j for j in JOBS}

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
}
PASSED = [k for k in KEY if EXPECTED[KEY[k]["title"]] == "passed"]
NEWEST_FIRST = sorted(PASSED, key=lambda k: KEY[k]["publishedAt"], reverse=True)

FJOBS = FILTER_FIXTURE["jobs"]
FKEY = {f"ashby:{FILTER_BOARD}:{j['id']}": j for j in FJOBS}
FBY_TITLE = {j["title"]: f"ashby:{FILTER_BOARD}:{j['id']}" for j in FJOBS}
FPASSED = {k for k, j in FKEY.items() if EXPECTED[j["title"]] == "passed"}


def same_instant(a, b):
    from datetime import datetime
    return datetime.fromisoformat(a.replace("Z", "+00:00")) == datetime.fromisoformat(b.replace("Z", "+00:00"))


def check_lead_messages(leads, rows_by_key):
    for msg in leads:
        assert msg["silent"] is True, f"lead message not silent: {msg['lead_key']}"
        assert msg["button_text"] == "Open posting", msg
        assert msg["button_url"] == KEY[msg["lead_key"]]["jobUrl"], msg
        assert msg["button_url"] == rows_by_key[msg["lead_key"]]["posting_url"]


def check_header(header, n):
    assert len(header) == 1, f"expected one header, got {len(header)}"
    word = "lead" if n == 1 else "leads"
    assert header[0]["text"] == f"Job Scout: {n} new {word} today", header[0]
    assert header[0]["silent"] is False, "header must make a sound"


# ---------- cases ----------

def case_one_lead_per_posting(wf):
    reset_test_tables()
    run_scan(wf)
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
        assert same_instant(r["published_at"], job["publishedAt"])
        assert r["status"] == "new" and r["first_seen_at"], r
        assert r["filter_result"] == EXPECTED[job["title"]], (job["title"], r["filter_result"])


def case_daily_ping_shape(wf):
    reset_test_tables()
    run_data = run_scan(wf, daily_cap=10)
    header, leads = sent(run_data)
    rows = {r["lead_key"]: r for r in lead_rows()}
    check_header(header, len(PASSED))
    assert [m["lead_key"] for m in leads] == NEWEST_FIRST, "leads not newest first"
    check_lead_messages(leads, rows)
    assert all(rows[k]["sent_at"] for k in PASSED), "sent leads have no sent_at"


def case_rescan_creates_no_duplicates_and_sends_nothing(wf):
    reset_test_tables()
    run_scan(wf)
    before = {r["lead_key"]: r for r in lead_rows()}
    run_data = run_scan(wf)
    after_rows = lead_rows()
    after = {r["lead_key"]: r for r in after_rows}
    assert len(after_rows) == len(before) == len(JOBS), "second scan changed the row count"
    for key, row in after.items():
        assert row["id"] == before[key]["id"], f"{key} got a new row"
        assert row["first_seen_at"] == before[key]["first_seen_at"], f"{key} first_seen_at changed"
        assert row["sent_at"] == before[key]["sent_at"], f"{key} sent_at changed"
    header, leads = sent(run_data)
    assert header == [] and leads == [], f"second scan sent {len(header)} header(s), {len(leads)} lead(s)"


def case_cap_and_carry_over(wf):
    cap = 3
    assert len(PASSED) > cap, "fixture must exceed the cap"
    reset_test_tables()

    header, leads = sent(run_scan(wf, daily_cap=cap))
    rows = {r["lead_key"]: r for r in lead_rows()}
    check_header(header, cap)
    assert [m["lead_key"] for m in leads] == NEWEST_FIRST[:cap], "first ping isn't the newest leads"
    check_lead_messages(leads, rows)
    assert sorted(k for k, r in rows.items() if r["sent_at"]) == sorted(NEWEST_FIRST[:cap])
    first_ping = {m["lead_key"] for m in leads}

    header, leads = sent(run_scan(wf, daily_cap=cap))
    rest = NEWEST_FIRST[cap:]
    check_header(header, len(rest))
    assert [m["lead_key"] for m in leads] == rest, "leads over the cap weren't sent next"
    assert not first_ping & {m["lead_key"] for m in leads}, "a lead was sent twice"
    assert sorted(r["lead_key"] for r in lead_rows() if r["sent_at"]) == sorted(PASSED)

    header, leads = sent(run_scan(wf, daily_cap=cap))
    assert header == [] and leads == [], "third scan sent messages"


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


# ---------- hard filters ----------

_filter_scan = {}


def filter_scan(wf):
    """One scan of the synthetic fixture, shared by the filter cases that only read it."""
    if not _filter_scan:
        reset_test_tables()
        run_data = run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE)
        _filter_scan["rows"] = {r["lead_key"]: r for r in lead_rows()}
        _filter_scan["sent"] = sent(run_data)
    return _filter_scan["rows"], _filter_scan["sent"]


def case_filters_store_the_failed_rule(wf):
    rows, _ = filter_scan(wf)
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
    rows, (header, leads) = filter_scan(wf)
    sent_keys = [m["lead_key"] for m in leads]
    assert sorted(sent_keys) == sorted(FPASSED), (
        f"sent {sorted(FKEY[k]['title'] for k in sent_keys)}")
    check_header(header, len(FPASSED))
    for k, r in rows.items():
        if r["filter_result"] != "passed":
            assert not r["sent_at"], f"filtered lead has sent_at: {FKEY[k]['title']}"


def case_messages_show_pay_and_location(wf):
    _, (_, leads) = filter_scan(wf)
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
    # A lead filtered under one config passes after the rule changes, and is sent then.
    reset_test_tables()
    pm = FBY_TITLE["Product Manager, Developer Platform"]  # base $150K-$180K
    header, leads = sent(run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE,
                                  payFloor=200000))
    rows = {r["lead_key"]: r for r in lead_rows()}
    assert rows[pm]["filter_result"] == "pay_floor" and not rows[pm]["sent_at"]
    assert pm not in {m["lead_key"] for m in leads}

    header, leads = sent(run_scan(wf, daily_cap=50, board=FILTER_BOARD, fixture=FILTER_FIXTURE))
    rows = {r["lead_key"]: r for r in lead_rows()}
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
    assert all(f["titleKeywords"] for f in cfg["roleFamilies"])
    note = next(n["parameters"]["content"] for n in wf["nodes"]
                if n["type"] == "n8n-nodes-base.stickyNote"
                and n["parameters"]["content"].startswith("## Job Scout config"))
    for field in cfg:
        assert f"**{field}**" in note, f"config sticky note doesn't explain {field}"


CASES = [
    case_telegram_nodes_send_what_they_receive,
    case_one_lead_per_posting,
    case_daily_ping_shape,
    case_rescan_creates_no_duplicates_and_sends_nothing,
    case_cap_and_carry_over,
    case_config_defaults_match_spec,
    case_filters_store_the_failed_rule,
    case_filtered_leads_never_reach_telegram,
    case_messages_show_pay_and_location,
    case_rule_changes_apply_to_saved_leads,
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
