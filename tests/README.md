# Job Scout tests

The tests run the Job Scout workflow's **Daily scan** trigger through n8n's instance-level MCP `test_workflow` tool, with pinned data in place of the outside world:

- **Job Scout config** is pinned to the node's own defaults (so the filter rules under test are the shipped ones), with one board, a fake chat ID and the table prefix `jobscout_test_`. A case can override a field, such as `payFloor`.
- **Fetch Ashby board** is pinned to `fixtures/ashby-n8n.json` (board `n8n`) or `fixtures/ashby-filters.json` (board `testco`).
- **Send header** and **Send lead message** are pinned to fake Telegram replies, so nothing is sent.

Every other node runs for real, including the Data Table nodes, which write to `jobscout_test_leads`. Each case clears the `jobscout_test_` tables first and again at the end.

The cases check only external behavior: rows in the test table, and the items that reach the two Telegram nodes. One case also checks that the Telegram nodes send what they receive (text, sound, HTML parse mode, no attribution, the Open posting button), because pinned nodes don't evaluate their own parameters. Another reads the config node's defaults and its sticky note, to check them against the spec.

The expected filter result for every fixture posting is listed by title in `EXPECTED` in `run_tests.py`.

## Run

```sh
python3 tests/run_tests.py          # all cases
python3 tests/run_tests.py cap      # only cases whose name contains "cap"
VERBOSE=1 python3 tests/run_tests.py  # show tracebacks for failures
```

It exits non-zero if any case fails. A full run takes about 40 seconds, because the workflow waits one second between lead messages. The MCP server rate-limits bursts of calls; the runner waits and retries on HTTP 429.

## What it needs

- Local n8n running at `http://localhost:5678` (see `docker-compose.yml`), with the instance-level MCP server on.
- A workflow named "Job Scout" (import `workflows/job-scout.json` if it's missing). Set `JOB_SCOUT_WORKFLOW_ID` if there's more than one.
- `.env` in the repo root with:
  - `N8N_API_KEY`: a public API key (used to find the workflow and tables and to clear the test table).
  - `N8N_MCP_TOKEN`: an instance-level MCP token (used for `test_workflow`, `get_workflow_execution` and `get_data_table_rows`).
- Python 3.11 or later. Standard library only.

The runner refuses to start if any Telegram or HTTP Request node in the workflow is missing pin data, and it only clears tables whose names start with `jobscout_test_`.

## Fixtures

`fixtures/ashby-n8n.json` is six postings from n8n's public Ashby board (`GET https://api.ashbyhq.com/posting-api/job-board/n8n?includeCompensation=true`), recorded 2026-09-30. Descriptions are cut to 160 characters and secondary locations to three. The postings were picked to cover a stated pay range, a Hybrid role, and a title with `&`. Under the hard filters, four of them pass; the `&` title and the Hybrid role fail on location, so HTML escaping is now checked with a synthetic posting.

`fixtures/ashby-filters.json` is 18 synthetic postings in the same shape, with made-up IDs and `testco` URLs, for the hard-filter cases. Their shapes follow live responses from the `n8n`, `posthog` and `ramp` boards on 2026-09-30: `workplaceType`, `location`, `secondaryLocations` and `address.postalAddress`, and `compensation` with `summaryComponents` and `compensationTiers`. They cover:

- each rule failing: hybrid in London, a USD base range below the floor (with a commission range above it, which must be ignored), and excluded titles (`Senior Corporate Paralegal`, and `HR Business Partner` in Dallas)
- unknowns passing: no pay ("Pay not listed"), no location at all ("Location unclear"), and pay only in EUR
- location edge cases: hybrid in New York with "Remote (US)" only as a secondary location (passes), `Remote (Canada)` and `Remote - Europe` with no address (fail), hybrid in Plano, TX (passes), hybrid in Austin (fails), and hybrid in Arlington, VA (fails; Arlington, TX would pass)
- titles that must not be excluded: `Developer Relations Engineer, SDKs & APIs`, `Fintech Product Engineer`, and `Developer Advocate` in the Marketing department
- pay edge cases: a range that tops out exactly at the floor (passes), and monthly pay ($12.5K a month counts as $150K a year)
