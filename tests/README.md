# Job Scout tests

The tests run the Job Scout workflow's **Daily scan** trigger through n8n's instance-level MCP `test_workflow` tool, with pinned data in place of the outside world:

- **Job Scout config** is pinned to the node's own defaults (so the filter rules, weights and thresholds under test are the shipped ones), with the boards the case scans (one Ashby board unless it says otherwise), a fake chat ID and the table prefix `jobscout_test_`. A case can override a field, such as `payFloor`, `weights` or `profileSummary`.
- **Fetch board** is pinned to one full response per board, in the order **Board list** builds them (Ashby, then Greenhouse, then Lever): `fixtures/ashby-n8n.json` (board `n8n`), `fixtures/ashby-filters.json` (`testco`), `fixtures/ashby-scoring.json` (`scoreco`), `fixtures/greenhouse-instacart.json` (`instacart`), `fixtures/lever-spotify.json` (`spotify`), `fixtures/greenhouse-filters.json` (`ghco`) or `fixtures/lever-filters.json` (`leverco`). A board can instead be pinned to a failed fetch (an `error` item, as the node returns with "continue on error"). The runner moves each posting's publish date (Ashby `publishedAt`, Greenhouse `first_published`, Lever `createdAt`) to whole days before now, keeping the gaps between postings, so the freshness window and freshness points don't change as the recorded dates age.
- **Ask Jev** is pinned to one Jev response per lead that should be judged, in the order **Build Jev requests** sends them (by lead key). Each response has the shape of `fixtures/jev-response.json`, a real response recorded 2026-09-30, with the answers for that posting from `JEV` in `run_tests.py`. A case lists the leads it expects Jev to judge, and the runner fails if Jev is asked about any others, so every scan also checks that unchanged leads aren't judged again.
- **Write fit line** (Claude) is pinned to fixed fit lines, in send order.
- **Send header** and **Send lead message** are pinned to fake Telegram replies, so nothing is sent.

Every other node runs for real, including the Data Table nodes, which write to `jobscout_test_leads`. Each case clears the `jobscout_test_` tables first and again at the end.

The cases check only external behavior: rows in the test table, and the items that reach the Jev, Claude and Telegram nodes. Two cases also check that those nodes send what they receive (Telegram: text, sound, HTML parse mode, no attribution, the Open posting button; Jev: the endpoint, Bearer credential, retries and the request body; Claude: the model, credential and a prompt that forbids invented facts), because pinned nodes don't evaluate their own parameters. Another reads the config node's defaults and its sticky note, to check them against the spec.

The expected filter result for every fixture posting is listed by title in `EXPECTED` in `run_tests.py`. Expected fit scores come from `expected_points`, which works out the fit score from the pinned Jev answers, the location basis, the posting's age and the weights, independently of the workflow's code.

## Run

```sh
python3 tests/run_tests.py          # all cases
python3 tests/run_tests.py cap      # only cases whose name contains "cap"
VERBOSE=1 python3 tests/run_tests.py  # show tracebacks for failures
```

It exits non-zero if any case fails. A full run takes about 5 minutes, because the workflow waits one second between lead messages and the MCP server allows 100 calls per window. On HTTP 429 the runner waits until the window resets (`X-RateLimit-Reset`) and retries.

## What it needs

- Local n8n running at `http://localhost:5678` (see `docker-compose.yml`), with the instance-level MCP server on.
- A workflow named "Job Scout" (import `workflows/job-scout.json` if it's missing). Set `JOB_SCOUT_WORKFLOW_ID` if there's more than one.
- `.env` in the repo root with:
  - `N8N_API_KEY`: a public API key (used to find the workflow and tables and to clear the test table).
  - `N8N_MCP_TOKEN`: an instance-level MCP token (used for `test_workflow`, `get_workflow_execution` and `get_data_table_rows`).
- Python 3.11 or later. Standard library only.

The runner refuses to start if any Telegram, HTTP Request or Anthropic node in the workflow is missing pin data, so no test calls Jev, Claude, a job board or Telegram. It only clears tables whose names start with `jobscout_test_`.

## Fixtures

`fixtures/ashby-n8n.json` is six postings from n8n's public Ashby board (`GET https://api.ashbyhq.com/posting-api/job-board/n8n?includeCompensation=true`), recorded 2026-09-30. Descriptions are cut to 160 characters and secondary locations to three. The postings were picked to cover a stated pay range, a Hybrid role, and a title with `&`. Under the hard filters, four of them pass; the `&` title and the Hybrid role fail on location, so HTML escaping is now checked with a synthetic posting.

`fixtures/ashby-filters.json` is 22 synthetic postings in the same shape, with made-up IDs and `testco` URLs, for the hard-filter cases. Their shapes follow live responses from the `n8n`, `posthog` and `ramp` boards on 2026-09-30: `workplaceType`, `location`, `secondaryLocations` and `address.postalAddress`, and `compensation` with `summaryComponents` and `compensationTiers`. They cover:

- each rule failing: hybrid in London, a USD base range below the floor (with a commission range above it, which must be ignored), and excluded titles (`Senior Corporate Paralegal`, `Finance Manager, Revenue Accounting`, and `HR Business Partner` in Dallas)
- unknowns passing: no pay ("Pay not listed"), no location at all ("Location unclear"), and pay only in EUR
- location edge cases: hybrid in New York with "Remote (US)" only as a secondary location (passes), `Remote (Canada)` and `Remote - Europe` with no address (fail), hybrid in Plano, TX and on-site in Dallas (pass), hybrid and on-site in Austin (fail), and hybrid in Arlington, VA (fails; Arlington, TX would pass)
- titles that must not be excluded: `Developer Relations Engineer, SDKs & APIs`, `Fintech Product Engineer`, `Software Engineer, Finance Platform` (an `excludedTitleOverrides` word wins), and `Developer Advocate` in the Marketing department
- pay edge cases: a range that tops out exactly at the floor (passes), and monthly pay ($12.5K a month counts as $150K a year)

`fixtures/ashby-scoring.json` is three synthetic postings (board `scoreco`) for scoring: a Developer Advocate in Marketing whose pay appears only in the description, below the floor (`$150,000 - $170,000 USD`, next to the distractors `$200M` and `$20k-$100k+ ARR`); a Senior Product Engineer whose pay appears only in the description, above the floor (`$190K–$230K`); and a posting published 41 days before the newest, which gets no freshness points but is still sent, because the freshness window counts from when Job Scout first sees a lead. One case backdates a lead's `first_seen_at` in the test table to check that a lead first seen more than 30 days ago is no longer sent.

`fixtures/greenhouse-instacart.json` is five postings from Instacart's public Greenhouse board (`GET https://boards-api.greenhouse.io/v1/boards/instacart/jobs?content=true&pay_transparency=true`), recorded 2026-10-01, with `content` cut to its first four paragraphs and long pay blurbs shortened. They cover US remote with one pay range per group of states (passes), an on-target-earnings range above the floor next to base ranges below it (fails on pay; OTE is ignored), hourly ranges (pay unknown, passes), the Canada copy of a role that lists "Remote - United States" as an office (fails on location; offices are ignored), and hybrid in Israel with no pay.

`fixtures/lever-spotify.json` is five postings from Spotify's public Lever board (`GET https://api.lever.co/v0/postings/spotify?mode=json`), recorded 2026-10-01, with text fields shortened and two lists kept. Live `workplaceType` values are `remote`, `hybrid` and `onsite`. They cover remote in New York with other US cities in `allLocations` (passes), remote in New York (passes), hybrid in London or Stockholm, hybrid in New York, and on-site in Los Angeles (all fail on location). The live boards had no `salaryRange` (Zoox's board, checked the same day, uses `{currency, interval: "per-year-salary" | "per-hour-wage", min, max}`).

`fixtures/greenhouse-filters.json` (board `ghco`) and `fixtures/lever-filters.json` (board `leverco`) are synthetic postings in those shapes, for the location and pay rules on both ATSes: hybrid in Dallas (`Hybrid - Dallas, TX`, department Marketing), `Dallas, TX` with no workplace type, Lever `on-site` (the docs' spelling) in Dallas, hybrid or `onsite` in Austin, hybrid in London with "Remote (US)" in `allLocations`, no location at all, Greenhouse OTE ranges, Lever monthly pay ($12K-$14K a month fails the floor), hourly pay, and EUR pay.

The Closed cases drop postings from a fixture between scans: a sent lead, an unsent New lead and a filtered lead are closed quietly while the next leads in fit order are sent; a board pinned as a failed fetch closes none of its leads while a missing posting on the other board is closed; and a posting listed again has `closed_at` cleared and is sent.

`fixtures/jev-response.json` is one real Jev (`jev-1.13.0`) response for n8n's Senior Developer Advocate posting, recorded through the workflow on 2026-09-30. The pinned responses reuse its shape and score legends.

The pinned Jev answers in `JEV` are made up to cover the cases: two n8n postings are in no role family (Field Marketing Lead, Senior Partner Manager), as are Instacart's Billing Operations Associate and Spotify's Backend Engineer - Music, every passing `testco` posting clears it, and the fit scores are spread out so the sending order is checked. They test Job Scout's handling of Jev's answers, not Jev's judgment.
