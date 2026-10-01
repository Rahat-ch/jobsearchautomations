# Job Scout: status

Last updated: 2026-09-30. Phase: **spec published** as [issue #1](https://github.com/Rahat-ch/jobsearchautomations/issues/1). Tickets come next, from `/to-tickets`.

## What Job Scout is

It rebuilds the backend of Hermes (Rahat's job-scout agent) on n8n:
- scan job boards on a schedule
- filter to real US-remote roles
- score each role against Rahat's resume with Claude
- dedupe across runs
- let Rahat triage
- learn from passes

The Hermes board design may become the UI later. The proof of concept has no frontend (see Scope).

## Scope (decided 2026-09-29/30)

- **Proof of concept first, demo as soon as possible.** Keep it simple.
- **No frontend.** Telegram is the whole interface. The Hermes board is deferred.
- **Job Scout replaces only Mina's daily search**, across Ashby, Greenhouse, Lever and X. Resume review and outreach stay in Rahat's Claude sessions.
- **No Hermes integration.** Job Scout borrows Hermes' design (pass codes, weights, X query buckets, scoring in code), and "Hermes" in the spec's wording becomes "Job Scout".
- **The parallel run is separate.** Rahat will run Job Scout next to Mina for a couple of days and compare by hand, but that testing isn't part of Job Scout, the demo or the template.
- **Demo shape:** one forkable n8n template.
  1. A daily search runs on inputs anyone can change after importing it.
  2. Results go to Telegram.
  3. When Rahat picks a lead, Job Scout returns the apply link with key facts, and suggests people to contact with a reason for each.
- **Job Scout never sends DMs or messages to anyone.** It only suggests. Rahat reaches out by hand.

## Decisions made

| Area | Decision | Notes |
|---|---|---|
| Engine | n8n, self-hosted | Community Edition is free. Running costs: Jev (about $0.0002 per lead, estimated), Claude for top and picked leads, Claude web search ($10 per 1,000 searches), and X reads ($0.005 per post, capped in config). |
| Hosting | Local Docker n8n on Rahat's Mac Mini, which runs 24/7 (decided 2026-09-29) | Used for the demo and the Hermes parallel run. Coolify is deferred; its research stays in `job-scout-coolify.md`. Phone buttons reach local n8n through a named Cloudflare tunnel on a subdomain of Rahat's Cloudflare-managed domain (decided 2026-09-30). The web-form Pass design stays. |
| UI | None for the proof of concept; Telegram only | The Hermes board (columns New, Applied, Interviewing, Offer, Passed, the pass-reason modal and the "Feedback to Hermes" panel) is deferred. Research is kept in `job-scout-board-serving.md`. |
| Notifications | Telegram | Daily ping with per-lead buttons. See Decisions for the spec. |
| Sources | Ashby, Greenhouse, Lever, X | Scanned daily. X uses Mina's five query buckets. |
| Starting companies | n8n, PostHog, Ramp (Ashby); Instacart (Greenhouse); Palantir, Spotify (Lever) | Checked 2026-09-29: board names resolve and return jobs. |
| Comp floor | $180K base | |
| Scoring and writing | Jev scores, code weights, Claude writes | Hybrid (decided 2026-09-30). Claude uses the Anthropic node, including Web Search for people. |
| Storage | n8n Data Tables | `leads`, `passes`, `contacts`. Config lives in the config node. No full resume text in n8n; scoring uses a short profile summary. |
| Extra | Instance-level MCP | Basic, read plus one status workflow. Claude Code on camera. |

## Research docs

| Doc | Covers |
|---|---|
| [`research/job-scout-build.md`](research/job-scout-build.md) | n8n version and editions, AI nodes, human-in-the-loop, Data Tables, scheduling, templates, ATS APIs, demo video |
| [`research/job-scout-coolify.md`](research/job-scout-coolify.md) | n8n on Coolify: templates, volume, backups, HTTPS, SQLite vs Postgres, durable scheduler, 3.0 upgrade |
| [`research/job-scout-board-serving.md`](research/job-scout-board-serving.md) | Serving the board from n8n webhooks vs a static site: HTML sandbox, auth, CORS, execution history |
| [`research/job-scout-telegram.md`](research/job-scout-telegram.md) | Bot setup, chat ID, message limits, digest shape, Send-and-Wait on Telegram, Mini Apps |
| [`research/job-scout-outreach.md`](research/job-scout-outreach.md) | Finding people to contact: LinkedIn's terms and API, Claude web search in n8n, GitHub and posting text, search APIs, browser-automation nodes |
| [`research/job-scout-x.md`](research/job-scout-x.md) | X API: pay-per-use pricing, recent search for hiring posts, routing ATS links, people lookup, storage terms, n8n's X node |
| [`research/job-scout-jev.md`](research/job-scout-jev.md) | TypeSafe Jev for scoring: API, which primitive fits each sub-score, draft questions, cost, calling it from n8n |
| [`research/job-scout-mcp.md`](research/job-scout-mcp.md) | Instance-level MCP: tools, auth, scopes, reading Data Tables, connecting Claude Code and Claude Desktop |

## Key findings

**From the first pass** (`job-scout-build.md`)
- **n8n 3.0 ships in October 2026.** It removes AI Agent v1, so build on current node versions.
- **Ashby's `isRemote` can't be trusted.** It was true on 140 of 155 Ramp jobs. Use `workplaceType` plus `secondaryLocations`. Hybrid roles with "Remote (US)" only in the secondary locations need extra checking.
- **Greenhouse had no structured pay data** in the Vercel sample, so pay must be parsed from the description. Lever's live `workplaceType` values (`onsite`) differ from its docs (`on-site`).
- **Template gallery:** new creators get one template in review at a time, sticky notes are mandatory, and personal identifiers must be removed.
- **n8n's own Senior Developer Advocate, US posting is on Ashby** (board `n8n`). That makes a natural first result in the demo.

**Coolify** (`job-scout-coolify.md`)
- **Start from Coolify's plain `n8n` template (SQLite plus a task-runner sidecar) and edit it before the first deploy.** At Coolify v4.3.23 it pins n8n 2.10.2, sets the deprecated `WEBHOOK_URL` and `N8N_RUNNERS_ENABLED`, and defaults to UTC. Coolify never merges template updates into an existing service.
- **Keep the task-runner sidecar**, and pin `n8nio/n8n` and `n8nio/runners` to the same tag (2.41.3). This corrects the build doc, which said a single container was enough.
- **SQLite is enough.** n8n Cloud Starter and Pro run on it. Data Tables live in the same database. `export:entities` / `import:entities` is the official path to Postgres later.
- **Everything lives in one volume** (`/home/node/.n8n`: database, encryption key, Data Tables). Back it up with Coolify's scheduled volume backup (v4.3.0+) and keep the encryption key in a password manager.
- **Turn on the durable scheduler.** It works with SQLite on a single instance. Coolify doesn't auto-update service images, so missed runs come only from deploys, reboots or crashes.
- **Stay on 2.41.x through the demo recording.** 3.0 cuts the Code node timeout from 300 s to 60 s, and its database migration can't be rolled back.

**Board serving** (`job-scout-board-serving.md`)
- **n8n sandboxes every HTML page a webhook returns** (`Content-Security-Policy: sandbox`, without `allow-same-origin`). On such a page `localStorage` and cookies fail, and Basic Auth isn't sent on `fetch`. Scripts, forms and cross-origin calls still work.
- **An auth pattern that fits the sandbox:** the page webhook uses Basic Auth and embeds a short-lived JWT in the HTML. The API webhooks use JWT Auth.
- **Other webhook gotchas:**
  - Paths like `leads/:id` get a UUID prefix, so pass the ID in the body.
  - Test URLs stop after one call, so build the board against published URLs.
  - "Allowed Origins" fails open on some paths.
  - Every page load is an execution. Turn off saving successful runs for the board workflows.
- **Don't call n8n's public API from the browser.** It sends no CORS headers, and a Community Edition API key can't be scoped.
- **Fallback:** a static site on its own Coolify subdomain, not a subpath of the n8n host.

**Telegram** (`job-scout-telegram.md`)
- **Telegram Send-and-Wait has native one-tap approval** ("Approve Within Chat"): callback buttons, resolved inside Telegram. Free Text and Custom Form still open a browser page.
- **The daily ping needs no Telegram Trigger.** Add a Trigger only for phone commands like `/scan`. Telegram allows one webhook per bot, so use a separate test bot.
- **Chat ID:** tap Start in the bot, then call `getUpdates` once, before any webhook exists. Store the ID in the config Data Table.
- **Limits:** 4096 characters per message, `callback_data` up to 64 bytes, and about 1 message per second per chat.
- **Where the n8n docs and source disagree:** the node's parse mode actually defaults to legacy Markdown, not HTML, and it sends the old `disable_web_page_preview` field.
- **Unverified:** whether URL buttons open in Telegram's in-app browser or the phone's browser. Test on the phone.

**Instance-level MCP** (`job-scout-mcp.md`)
- **Endpoint:** `https://<host>/mcp-server/http`, over stateless Streamable HTTP. It's off by default, with no license gate on Community Edition.
- **Auth:** OAuth with chosen scopes, or a non-expiring API-key token that unlocks every tool.
- **Agents can read Data Tables directly** with `get_data_table_rows` (filters, sort, up to 100 rows per call). No MCP tool updates or deletes rows, so "mark applied" needs a Webhook-triggered workflow marked "Available in MCP".
- **`execute_workflow` can start only Webhook, Form, Chat, Schedule and Manual triggers**, not sub-workflow triggers. It returns an execution ID, and the agent reads the result with a second call.
- **MCP runs skip the Webhook node's own auth.** The workflow must validate its inputs itself.
- **Scope risk:** `dataTable:read` reaches every table, and `get_workflow_details` returns every node parameter. Keep resume text out of anything an MCP token can reach.

**Outreach** (`job-scout-outreach.md`)
- **LinkedIn's User Agreement 8.2 bans scraping tools, including browser plugins and add-ons, and bots.** A browser agent on Rahat's logged-in account puts that account at risk of restriction.
- **LinkedIn's self-serve API gives only sign-in and posting.** People search needs partner approval. n8n's LinkedIn node only creates posts.
- **n8n's Anthropic node ("Message a Model") has a built-in Web Search option at 2.41.3.** Claude can return people with name, title, public profile link, a reason, and cited sources. Search costs $10 per 1,000 searches plus tokens.
- **Other free signals:** posting text often names the role the hire reports to. GitHub `public_members` works for devtools companies.

**X** (`job-scout-x.md`)
- **Self-serve X API is pay-per-use** (since 2026-02-06): $0.005 per post read and $0.010 per user read. The same item read twice in one UTC day is charged once. Legacy Basic and Pro plan terms are no longer in the docs.
- **Recent search (last 7 days) is enough for a daily run.** `url:` matches the full link behind t.co links, so it finds posts that link to Ashby, Greenhouse or Lever. Those links can go straight to the existing ATS fetchers. `since_id` makes each run incremental.
- **Use the HTTP Request node with a Bearer token, not n8n's X node.** At 2.41.3 the node's search drops author and paging data, and its only credential is a user login that always requests `dm.write`. A Bearer token can't send DMs, which enforces the no-DM rule.
- **People on X:** the best signal is the author of the hiring post. `GET /2/users/search` costs about $1 per call at its default of 100 results, so always set `max_results`.
- **Terms:** no tracking or profiling of users, deleted posts removed within 24 hours, no model training. Store IDs and links, not post text.

**Jev** (`job-scout-jev.md`)
- **Jev fits the planned scoring design.** TypeSafe's composite-scoring page uses resume screening as its example: several Score questions in one request, with weights applied in code.
- **API:** `POST https://api.typesafe.ai/v1/systemone` with a Bearer key. All questions in a request run in parallel. Current model `jev-1.13.0`.
- **Cost and speed:** $0.042 per million input tokens, output free. About $0.0002 per lead (estimate). Most calls take about 100 ms. 1,200 requests per minute.
- **Suggested split:**
  - Choice for role family and messy location text.
  - Score for stack, seniority and domain.
  - Noul for "is this X post a real job".
  - Pay and freshness stay in code.
- **Jev doesn't write text.** "Why it fits" and "who to contact and why" still need Claude, or code builds the fit line from the sub-scores.
- **n8n:** no official TypeSafe node. Use the HTTP Request node with a Bearer credential. A forker would need three keys: Telegram, Anthropic and TypeSafe.

## Decisions for the spec

**Hosting**
- **Local Docker n8n on Rahat's Mac Mini**, which runs 24/7. Coolify is deferred (`job-scout-coolify.md` still applies later).
- **A named Cloudflare tunnel** on the `jobscout` subdomain of Rahat's Cloudflare-managed domain, so phone buttons and forms reach n8n.
  - Set `N8N_WEBHOOK_URL` to it and `N8N_PROXY_HOPS=1`, and turn on the durable scheduler.
  - The n8n owner login protects the editor, with no Cloudflare Access for now.
- **MCP from Claude Code uses `localhost:5678`**, not the tunnel.

**Config node** (one "Job Scout config" node with a sticky note per field)
1. Target role title keywords and exclusions. Default: per-family keywords from Mina's X buckets.
2. Location rules. Default: remote US, or remote, hybrid or on-site anywhere in the Dallas–Fort Worth area (suburbs and Fort Worth included). Austin hybrid or on-site roles fail; remote US roles based in Austin pass (on-site and Austin decided 2026-09-30). Include every listing that offers US remote, including Ramp-style listings where "Remote (US)" appears only as a secondary location.
3. Pay floor. Default: $180K base.
4. Companies, by board. Ashby: n8n, PostHog, Ramp. Greenhouse: Instacart. Lever: Palantir, Spotify.
5. X search: on/off (off by default in the template), query buckets, and a monthly spending cap with presets of $5, $10 and $25.
6. Profile summary. Drafted from Rahat's general resume at build time and edited by Rahat. The template ships a placeholder.
7. Minimum fit score and daily cap. Default cap: top 10.
8. Daily run time. Default: 8:00 am Central.
9. Score weights. Default: Hermes' role family 25, stack 20, ownership/seniority 15, location 15, domain 10, freshness 10, referral 5. All four role families score equally.

**X default queries** (Mina's five buckets, last 7 days, each ending in `-is:retweet lang:en`; the largest is about 370 of 512 characters)
1. **DevEx/Product PM, remote US:** Product Manager, Technical PM, Senior PM, Product Lead, Group PM, Platform PM. Combined with DevEx, developer platform, devtools, APIs, SDKs, integrations, developer productivity, or AI developer product. Plus hiring, opening or apply, and remote, remote US or US remote.
2. **DevEx/Product PM, DFW:** the same titles and keywords. Plus Dallas, DFW, Frisco, Plano, Irving, Arlington, Richardson, Addison, McKinney, or Texas.
3. **FDE / Solutions:** "forward deployed engineer", "AI solutions engineer", "solutions architect", "solutions engineer", "field engineer", or "customer engineer". Plus hiring, opening or apply, and Remote-US or Texas/DFW terms.
4. **Product / frontend engineering:** Senior Frontend Engineer, Frontend Engineer, Product Engineer, Senior Product Engineer, Software Engineer, Founding Engineer. Combined with React, Next.js, TypeScript, React Native, frontend, or AI. Plus Remote-US or Texas/DFW.
5. **DevRel / DevEx:** Developer Relations, DevRel, Developer Advocate, Developer Experience, DevEx, or Partner Engineer. Plus Remote-US or Texas/DFW.
- These are also the four target role families: DevEx/Product PM, FDE/Solutions, Product/Frontend Engineering, and DevRel/DevEx.
- "Texas" in the queries is broader than the location rule. The code location filter runs after search.
- Use the HTTP Request node with a Bearer token, not n8n's X node. Rahat's X key is pay-per-use.

**Scoring** (hybrid)
- **Code:** the location, pay-floor and freshness checks, then applies the weights and computes the total.
- **Jev:** scores role family, stack, seniority and domain, checks messy location text, and decides "is this X post a real job".
- **Claude:** writes only for the leads that make the daily cap, and when Rahat taps "Find people".
- **Seniority:** Senior, Lead and Founding Engineer are the focus. Junior, mid-level, Staff+ and manager titles score low.
- **Referral:** 0 by default. A Telegram button on a lead marks "I have a referral" and adds the referral points.
- **Keys:** the template needs three, for Telegram, Anthropic and TypeSafe.

**Telegram**
- **Bot:** display name "Job Scout", username `jobscout_n8n_bot`. The username can't be changed later.
- **Messages:** one header message ("Job Scout: N new leads today", with sound), then one silent message per lead. Each lead shows role, company, pay, location, fit score with its breakdown, a one-line reason it fits, and "Referral available" when set.
- **Buttons on each lead:** Open posting, Find people, Search LinkedIn, Referral, Applied, Pass.
- **Lead states:** New, then Picked, Applied, or Passed.
  - **Find people** marks the lead Picked. It runs at most 3 web searches per tap, and a second tap re-sends the saved list. The reply has the apply link, key facts, up to 4 people (likely hiring manager, a team member, a recruiter, anyone Rahat already knows) with a reason and links (LinkedIn, plus GitHub and X when found), and an **Applied** button.
  - **Applied** records that Rahat submitted the application. It works from New or Picked. The lead stops appearing.
  - **Pass** means "not for me". It opens a short form with the lead prefilled, a required reason code and an optional note. The link is signed. The lead stops appearing.
  - **Referral** flags the lead's company, so every current and future lead from it gets the referral points.
  - **No undo button.** Fix a mis-tap on the Data tables page, or ask Claude over MCP.
- **Pass-reason codes:** the 10 codes in the Hermes spec's section 1 table. Drop the seed data's `role_too_backend` and `location_mismatch`.
- **Not in the proof of concept:** phone commands, a Telegram Trigger, the "learn from passes" step (after the parallel run), and the "sent automatically with n8n" line (turned off).

**People search**
- Claude web search, through the Anthropic node's Web Search option, returns people with public profile links and cited sources.
- A "Search LinkedIn" button opens LinkedIn's own people search, prefilled.
- No LinkedIn automation, and nothing logs into Rahat's LinkedIn account.

**Tracking**
- **n8n Data Tables**, stored in local n8n's SQLite database:
  - `leads`: status and a date for each status change, plus referral.
  - `passes`
  - `contacts`
- **Rahat views them** on n8n's Data tables page (with Download CSV), or through Claude over MCP.
- **The private job-search log stays separate**, with no sync.

**MCP**
- Basic instance-level MCP over OAuth with `workflow:read`, `workflow:execute`, `execution:read` and `dataTable:read`. No `workflow:write`.
- Agents read the tables directly, and change status only through one "set lead status" workflow (Passed requires a reason code).
- Claude Code on camera.

**Demo and template**
- Real postings in the video, with personal details and applied-to companies hidden.
- One n8n template.

**Lead lifecycle** (decided in grilling, 2026-09-30; terms in `CONTEXT.md`)
- **Identity:** a lead is keyed by board + ATS job ID. A hiring post that links to a posting merges into that lead, with X added as a source. A hiring post with no posting link becomes an X-only lead, keyed by the post, if Jev judges it a real opening.
- **Filters first:** postings that fail location, pay floor or title exclusions are stored as Filtered with the reason, and never sent. No stated pay passes the pay floor and shows as "Pay not listed".
- **Excluded titles** (decided 2026-09-30): the default list is non-engineering operations titles only (accountant, finance, legal, counsel, paralegal, HR, people ops, office manager, facilities, executive assistant), matched on whole words in the title. A title that also has an engineering, product or DevRel word (engineer, engineering, developer, software, SWE, architect, programmer, advocate, DevRel, product manager, PM, platform) is never excluded, so "Software Engineer, Finance Platform" passes. The department and team fields are never used, because DevRel and Developer Advocate roles often sit in Marketing.
- **Unknown location:** an X-only lead with no stated location passes the location filter and shows as "Location unclear". Only a clearly wrong location filters it out.
- **Boards outside the config:** an X post that links to a posting at a company not in the board list still becomes a lead. The board list changes only when Rahat edits the config.
- **Scoring failures:** retry. If scoring still fails, the lead is saved Unscored and scored on the next scan. The header reports how many couldn't be scored.
- **Sending:**
  - The minimum fit score is 60 (config).
  - New leads that miss the daily cap stay New and compete later.
  - A lead is never sent twice.
  - The first scan scores everything and sends the top 10 as usual.
- **Freshness window:** 30 days (config). The freshness sub-score decays across it, and New leads past it are no longer sent.
- **Closed:** when a posting disappears from its board, the lead is marked Closed quietly, with no message.
- **Empty day:** a short "no new leads" message with counts: scanned, filtered, unscored.
- **Crash:** an error workflow sends "Job Scout scan failed" with the node and the error to the same chat.
- **Suggested contacts:** for a lead from a hiring post, the post's author is the first candidate. X data is stored as handle and reason only.
- **No reminders** for Picked leads in the proof of concept.
- **MCP "set lead status"** can also move a lead back to New, as the undo path.

**Build shape** (ADR 0005)
- An n8n gallery template is one workflow JSON, so Job Scout is one workflow with several triggers.
- Importing a template drops workflow settings. The error workflow must be set up by hand after import, and a sticky note should explain how.

**Docs for ticket work**
- `CONTEXT.md`: the glossary (lead, posting, board, hiring post, pick, pass, suggested contact, fit score, and so on).
- `docs/adr/`:
  - 0001: never contact or apply
  - 0002: no LinkedIn automation
  - 0003: hybrid scoring
  - 0004: X through HTTP Request, not the X node
  - 0005: one workflow, many triggers

## Check with a spike before building

- Telegram URL buttons on Rahat's phone: in-app browser or external browser, and whether Telegram fetches button URLs.
- The "Search LinkedIn" URL opens LinkedIn's people search correctly on the phone.
- The named tunnel: webhook, form and signed-link URLs resolve from the phone.
- Jev vs Claude: score the same 20–30 leads both ways (Rahat's own testing, outside the demo).

## Still open

- Rahat's profile summary text: drafted from the general resume during issue #9 and set in the live config node only (the export ships a placeholder). Waiting for Rahat's edits.
- Deferred with the board: webhook-served page or static site, and the login scheme (see `job-scout-board-serving.md`).
