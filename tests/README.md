# Job Scout tests

The tests run the Job Scout workflow's **Daily scan** trigger through n8n's instance-level MCP `test_workflow` tool, with pinned data in place of the outside world:

- **Job Scout config** is pinned to one board (`n8n`), a fake chat ID and the table prefix `jobscout_test_`.
- **Fetch Ashby board** is pinned to `fixtures/ashby-n8n.json`.
- **Send header** and **Send lead message** are pinned to fake Telegram replies, so nothing is sent.

Every other node runs for real, including the Data Table nodes, which write to `jobscout_test_leads`. Each case clears the `jobscout_test_` tables first and again at the end.

The cases check only external behavior: rows in the test table, and the items that reach the two Telegram nodes. One case also checks that the Telegram nodes send what they receive (text, sound, HTML parse mode, no attribution, the Open posting button), because pinned nodes don't evaluate their own parameters.

## Run

```sh
python3 tests/run_tests.py          # all cases
python3 tests/run_tests.py cap      # only cases whose name contains "cap"
VERBOSE=1 python3 tests/run_tests.py  # show tracebacks for failures
```

It exits non-zero if any case fails. A full run takes about 30 seconds, because the workflow waits one second between lead messages.

## What it needs

- Local n8n running at `http://localhost:5678` (see `docker-compose.yml`), with the instance-level MCP server on.
- A workflow named "Job Scout" (import `workflows/job-scout.json` if it's missing). Set `JOB_SCOUT_WORKFLOW_ID` if there's more than one.
- `.env` in the repo root with:
  - `N8N_API_KEY`: a public API key (used to find the workflow and tables and to clear the test table).
  - `N8N_MCP_TOKEN`: an instance-level MCP token (used for `test_workflow`, `get_workflow_execution` and `get_data_table_rows`).
- Python 3.11 or later. Standard library only.

The runner refuses to start if any Telegram or HTTP Request node in the workflow is missing pin data, and it only clears tables whose names start with `jobscout_test_`.

## Fixture

`fixtures/ashby-n8n.json` is six postings from n8n's public Ashby board (`GET https://api.ashbyhq.com/posting-api/job-board/n8n?includeCompensation=true`), recorded 2026-09-30. Descriptions are cut to 160 characters and secondary locations to three. The postings were picked to cover a stated pay range, a Hybrid role, and a title with `&` (to check HTML escaping).
