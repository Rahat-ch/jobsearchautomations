#!/usr/bin/env python3
"""Job Scout tests: run the scan trigger through n8n's MCP test_workflow tool.

Each case clears the jobscout_test_ tables, runs the "Daily scan" trigger with
pinned data (fixture board response, test config, fake Telegram replies), and then
checks only external behavior: rows in the test tables and the items that reached
the Telegram send nodes.

  python3 tests/run_tests.py            # all cases
  python3 tests/run_tests.py cap        # cases whose name contains "cap"

Stdlib only. Needs the local n8n and N8N_API_KEY + N8N_MCP_TOKEN in .env.
"""
import json
import os
import sys
import traceback
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
    return n8n_mcp.call(tool, args)


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

def run_scan(workflow, daily_cap=10):
    pin = {
        TRIGGER: [{"json": {}}],
        "Job Scout config": [{"json": {
            "ashbyBoards": [BOARD], "telegramChatId": FAKE_CHAT_ID,
            "dailyCap": daily_cap, "tablePrefix": TEST_PREFIX}}],
        "Fetch Ashby board": [{"json": FIXTURE}],
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


# ---------- expectations from the fixture ----------

JOBS = [j for j in FIXTURE["jobs"] if j.get("isListed", True)]
KEY = {f"ashby:{BOARD}:{j['id']}": j for j in JOBS}
NEWEST_FIRST = sorted(KEY, key=lambda k: KEY[k]["publishedAt"], reverse=True)


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


def case_daily_ping_shape(wf):
    reset_test_tables()
    run_data = run_scan(wf, daily_cap=10)
    header, leads = sent(run_data)
    rows = {r["lead_key"]: r for r in lead_rows()}
    check_header(header, len(JOBS))
    assert [m["lead_key"] for m in leads] == NEWEST_FIRST, "leads not newest first"
    check_lead_messages(leads, rows)
    fpa = [m for m in leads if "FP&A" in KEY[m["lead_key"]]["title"]]
    assert fpa and "FP&amp;A" in fpa[0]["text"], "HTML special characters not escaped"
    assert all(r["sent_at"] for r in rows.values()), "sent leads have no sent_at"


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
    cap = 4
    assert len(JOBS) > cap, "fixture must exceed the cap"
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
    assert all(r["sent_at"] for r in lead_rows())

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


CASES = [
    case_telegram_nodes_send_what_they_receive,
    case_one_lead_per_posting,
    case_daily_ping_shape,
    case_rescan_creates_no_duplicates_and_sends_nothing,
    case_cap_and_carry_over,
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
