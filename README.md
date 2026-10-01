# Job Scout

Job Scout is an n8n workflow that finds job openings every morning, scores each one against your profile, and sends the best matches to Telegram, where you triage them with one tap. It never applies for jobs, contacts anyone, or searches for people.

It is a rebuild of the daily search in my own job-scout agent.

## What a run does

```
Daily scan (8:00)
  → fetch company job boards: Ashby, Greenhouse, Lever
  → normalize every posting into a lead (one lead per posting, deduped across runs)
  → hard filters: location, pay floor, excluded titles
  → Jev scores each candidate lead: role family, stack, seniority, domain
  → code adds location, freshness and referral, applies your weights → fit score out of 100
  → pick the best new leads above the minimum, up to the daily cap
  → Claude writes one line on why each one fits
  → Telegram: a header plus one message per lead
```

Each lead message shows the role, company, pay, location, fit score with its breakdown and the fit line, with five buttons:

| Button | What it does |
|---|---|
| Open posting | Opens the job page |
| Search LinkedIn | Opens LinkedIn's own people search for that company and role. No automation |
| Applied | Marks the lead applied, so it never comes back |
| Referral | Flags the company; all its current and future leads get referral points |
| Pass | Opens a short form: pick one of ten reasons, add an optional note |

The buttons are signed links (HMAC over the action and lead), so an edited or guessed link changes nothing.

Everything is tracked in n8n Data Tables (`leads`, `passes`, `referrals`, `state`). On a day with nothing new you get one "no new leads" message with the day's counts. If a scan crashes, an alert tells you which step failed. Agents such as Claude Code can read the pipeline through n8n's instance-level MCP server.

## Design choices

Each of these has a short decision record in [`docs/adr/`](docs/adr/):

- **Never contact or apply** ([0001](docs/adr/0001-never-contact-or-apply.md)). Job Scout only suggests; you act.
- **No LinkedIn automation and no people search** ([0002](docs/adr/0002-no-linkedin-automation.md)). LinkedIn's terms ban bots, and an AI people search was tried and dropped for cost. Each lead gets a plain Search LinkedIn link instead.
- **Hybrid scoring** ([0003](docs/adr/0003-hybrid-scoring.md)). [TypeSafe's Jev](https://docs.typesafe.ai) makes the typed judgments (about $0.0002 per lead), code does the math so the score is explainable, and Claude only writes text for the leads that are sent.
- **X through the HTTP Request node** ([0004](docs/adr/0004-x-via-http-request.md)), for when the X source lands.
- **One workflow, several triggers** ([0005](docs/adr/0005-one-workflow-many-triggers.md)). An n8n template is a single workflow, so the scan, the button webhooks, the Pass form and the crash alert all live in one.

## Running cost

With six boards and a daily cap of 10, a day costs a few cents: Jev scores the candidate leads for about $0.01, and Claude writes up to 10 fit lines for about $0.05. n8n Community Edition is free.

## Run it yourself

You need:

- n8n self-hosted (built and tested on 2.41.3; see `docker-compose.yml`)
- A Telegram bot from [@BotFather](https://t.me/BotFather), and your chat ID
- An Anthropic API key, for the fit lines
- A TypeSafe API key, for Jev scoring
- A public HTTPS URL for n8n if you want the phone buttons to work (I use a named Cloudflare tunnel; see `docker-compose.yml`)

Then:

1. Import [`workflows/job-scout.json`](workflows/job-scout.json) into n8n.
2. Create three credentials and attach them: Telegram API, Anthropic, and Bearer Auth for TypeSafe.
3. Edit the **Job Scout config** node. Every field has a sticky note:
   - `telegramChatId`, `profileSummary` (a few lines about you; no resume needed)
   - boards: `ashbyBoards`, `greenhouseBoards`, `leverBoards`
   - `roleFamilies`, `targetSeniority`, `excludedTitles`, `locationRules`, `payFloor`
   - `weights`, `minFitScore`, `dailyCap`, `freshnessWindowDays`
4. Set the run time on the **Daily scan** trigger.
5. Publish the workflow. The first run creates its Data Tables and the link-signing secret.

The defaults are my own search: senior DevRel, forward-deployed and product engineering roles, remote in the US or in Dallas–Fort Worth. Change them in the config node.

## Tests

`python3 tests/run_tests.py` runs the workflow through n8n's MCP `test_workflow` tool against recorded board responses, with Telegram, Jev and Claude replaced by fixtures and separate `jobscout_test_` tables. It checks only outside behavior: the rows written and the messages that would be sent. See [`tests/README.md`](tests/README.md).

## How it was built

The research, decisions and tickets are all in this repo and its issues:

- [`docs/research/`](docs/research/): primary-source research (n8n, the job-board APIs, Telegram, MCP, Jev, X, Coolify)
- [`docs/status.md`](docs/status.md): the decision log
- [`CONTEXT.md`](CONTEXT.md): the glossary
- [Issue #1](https://github.com/Rahat-ch/jobsearchautomations/issues/1): the spec. The other issues are the tickets it was built from.

## Not done yet

- An X source for hiring posts that link to job boards (spike in [`docs/research/job-scout-x-spike.md`](docs/research/job-scout-x-spike.md))
- A status trigger so agents can mark leads over MCP
- Packaging as an n8n gallery template
