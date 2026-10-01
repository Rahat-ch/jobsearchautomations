# Job Scout: status

Last updated: 2026-10-01. Phase: **spec published** as [issue #1](https://github.com/Rahat-ch/jobsearchautomations/issues/1). Tickets come next, from `/to-tickets`.

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
- **Demo focus: automated job retrieval** (decided 2026-10-01): scan, filter, score, ping and triage. No people search: the Claude "Find people" step was dropped for cost (about $0.20 per tap); each lead keeps a free Search LinkedIn link (ADR 0002, amended).

## Decisions made

| Area | Decision | Notes |
|---|---|---|
| Engine | n8n, self-hosted | Community Edition is free. Running costs: Jev (about $0.0002 per lead, estimated), Claude fit lines for the leads that are sent, and X reads ($0.005 per post, capped in config). |
| Hosting | Local Docker n8n on Rahat's Mac Mini, which runs 24/7 (decided 2026-09-29) | Used for the demo and the Hermes parallel run. Coolify is deferred; its research stays in `job-scout-coolify.md`. Phone buttons reach local n8n through a named Cloudflare tunnel on a subdomain of Rahat's Cloudflare-managed domain (decided 2026-09-30). The web-form Pass design stays. |
| UI | None for the proof of concept; Telegram only | The Hermes board (columns New, Applied, Interviewing, Offer, Passed, the pass-reason modal and the "Feedback to Hermes" panel) is deferred. Research is kept in `job-scout-board-serving.md`. |
| Notifications | Telegram | Daily ping with per-lead buttons. See Decisions for the spec. |
| Sources | Ashby, Greenhouse, Lever, X | Scanned daily. X uses Mina's five query buckets. |
| Starting companies | n8n, PostHog, Ramp (Ashby); Instacart (Greenhouse); Palantir, Spotify (Lever) | Checked 2026-09-29: board names resolve and return jobs. |
| Comp floor | $180K base | |
| Scoring and writing | Jev scores, code weights, Claude writes | Hybrid (decided 2026-09-30). Claude uses the Anthropic node, including Web Search for people. |
| Storage | n8n Data Tables | `leads`, `passes`, `referrals`, `state`. Config lives in the config node. No full resume text in n8n; scoring uses a short profile summary. |
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
| [`research/job-scout-x-spike.md`](research/job-scout-x-spike.md) | X spike for #16: Mina's queries run once, results by bucket, ATS link patterns, cost, refinements |
| [`research/job-scout-find-people-spike.md`](research/job-scout-find-people-spike.md) | Find people spike (not built; dropped for cost): prompt, JSON schema, node settings, quality on 3 real leads, cost and latency |
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

**X default queries** (Mina's five buckets, last 7 days, each ending in `-is:retweet lang:en`; the largest is 464 of 512 characters)
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
- **Claude:** writes the fit line only for the leads that make the daily cap. No other Claude calls.
- **Role family required** (decided 2026-09-30): a lead whose role family is "None of these" (Jev's top answer) is never sent, whatever its fit score. The lead's `selection_reason` records why a lead was held back.
- **Consultants** (decided 2026-09-30): Technical Consultant and Solutions Consultant roles count as FDE/Solutions; accounting, finance or business-process consulting (such as Partner Consultant, Accounting) does not.
- **Account management and customer success** (decided 2026-10-01, issue #11): Technical Account Manager, Account Manager and Customer Success Manager roles are not FDE/Solutions. Customer Success Engineer roles are. The family's description says so, which changes Jev's request, so unsent leads are judged again on the next scan.
- **Partner roles** (decided 2026-10-01): partner, alliances and systems-integrator consulting roles (such as Ramp's Senior Partner Consultant, Systems Integrators) are not FDE/Solutions. Technical and Solutions Consultants still are. Technical Program Manager stays in DevEx/Product PM.
- **Hourly pay** (decided 2026-10-01): hourly base pay counts toward the pay floor at 2,080 hours a year, on every ATS. The message shows the hourly range and the yearly estimate, such as "$28.37 – $32.94 an hour, ≈ $59K – $68.5K a year".
- **Fit line model:** Claude Sonnet 5.5 (`claude-sonnet-5-5`).
- **Seniority:** Senior, Lead and Founding Engineer are the focus. Junior, mid-level, Staff+ and manager titles score low.
- **Referral:** 0 by default. A Telegram button on a lead marks "I have a referral" and adds the referral points.
- **Keys:** the template needs three, for Telegram, Anthropic and TypeSafe.

**Telegram**
- **Bot:** display name "Job Scout", username `jobscout_n8n_bot`. The username can't be changed later.
- **Messages:** one header message ("Job Scout: N new leads today", with sound), then one silent message per lead. Each lead shows role, company, pay, location, fit score with its breakdown, a one-line reason it fits, and "Referral available" when set.
- **Buttons on each lead:** Open posting, Applied, Referral, Pass, Search LinkedIn. (Find people was dropped on 2026-10-01; see Scope.)
- **Lead states:** New, then Applied or Passed.
  - **Applied** records that Rahat submitted the application. It works from New or Picked. The lead stops appearing.
  - **Pass** means "not for me". It opens a short form with the lead prefilled, a required reason code and an optional note. The link is signed. The lead stops appearing.
  - **Referral** flags the lead's company, so every current and future lead from it gets the referral points.
  - **No undo button.** Fix a mis-tap on the Data tables page, or ask Claude over MCP.
- **Pass-reason codes:** the 10 codes in the Hermes spec's section 1 table. Drop the seed data's `role_too_backend` and `location_mismatch`.
- **Not in the proof of concept:** phone commands, a Telegram Trigger, the "learn from passes" step (after the parallel run), and the "sent automatically with n8n" line (turned off).

**Action links** (built in issue #12, 2026-10-01)
- **Buttons:** each lead message has two rows: **Open posting**, then **Applied**, **Referral** and **Pass** (Pass added in issue #13). Search LinkedIn comes in #14.
- **Signature:** HMAC-SHA256 of `<action>:<lead key>` with the signing secret, as hex, cut to the first 32 characters (128 bits), compared character by character in constant time. An Applied signature doesn't work on Referral, or the reverse.
  - The secret is 32 random bytes in hex, made on the first run by the Crypto node's Generate action and kept in the `state` Data Table (`key` `signing_secret`). It isn't in the config, the repo or any message.
  - The HMAC is written out in JavaScript in the three Code nodes that sign (one shared block). At 2.41.3 the Code node can't `require('crypto')` unless `NODE_FUNCTION_ALLOW_BUILTIN` allows it (the task runner's default is none), and the Crypto node v2's HMAC reads its secret from a Crypto credential, which every template importer would have to create. The tests check every link against Python's `hmac`.
  - **Links don't expire.** Both actions only change the job seeker's own tracking and a second tap changes nothing, and a lead message can be tapped weeks later. To revoke every link, delete the `signing_secret` row; the next run makes a new secret.
  - Anyone who can read the `state` table (an MCP token with `dataTable:read`) or the saved executions can make valid links.
- **Webhooks:** GET `/webhook/job-scout/applied` and `/webhook/job-scout/referral` (static paths), with `lead` and `sig` in the query string, "Ignore Bots" on, and a Respond to Webhook node that returns a short HTML page: 200 when done or already done, 403 "Invalid link" for a bad or missing signature (nothing changes), 404 for an unknown lead, 409 for Applied on a Passed lead. The page is the confirmation; there's no Telegram reply.
- **Public base URL:** n8n 2.41.3 has no expression for a Webhook node's production URL. `$execution.resumeUrl` is `<webhook base>webhook-waiting/<execution id>`, where the base is `N8N_WEBHOOK_URL` or `WEBHOOK_URL` (`url.service.js`, `get-additional-keys.js`), so the links drop the last two path segments and add `webhook/job-scout/...`. No config field and nothing hard-coded, so a forked template points at its own host. It assumes n8n's default `webhook/` prefix (`N8N_ENDPOINT_WEBHOOK`).
- **One config, then route:** every trigger runs **Job Scout config** and the same setup (create the `leads`, `state` and `referrals` tables if missing, read the referrals and the secret). **Route by trigger** then sends the run down the scan, Applied or Referral path, by which trigger ran (`$('<trigger>').isExecuted`). Later triggers can join the same router. In tests, pinning the config node to `jobscout_test_` covers every path.
- **Applied:** a New or Picked lead becomes `applied` with `applied_at`. The scan selects only `new` leads, so it is never sent again. A second tap writes nothing.
- **Referral:** saves the company in `referrals` (`company_key`, `company`, `lead_key` it was set from, `set_at`). The company key is the company name in lower case with only letters and digits, so a later source that spells it "PostHog" matches the `posthog` board. Right away, the company's unsent leads get `sub_referral` 1 and the referral points swapped into `fit_score` (no Jev calls), and a lead held back only by the minimum fit score becomes eligible if it now reaches it. Every scan then sets the referral sub-score from the table, so new leads from the company get it too, and their messages show "Referral available" under the company. Messages already sent aren't edited. A second tap for the same company writes nothing.
- **Schema:** `applied_at` (date) on `leads`; new tables `state` (`key`, `value`) and `referrals`. The workflow creates missing tables, but not missing columns.

**Pass form** (built in issue #13, 2026-10-01)
- **Link:** the Pass button opens `<base>form/job-scout/pass?lead=<key>&sig=<sig>&title=<title>&company=<company>`, built like the other action links from `$execution.resumeUrl` with n8n's default `form/` prefix (`N8N_ENDPOINT_FORM`). The signature is the same HMAC over `pass:<lead key>`. The title and company are only shown on the form; the page after submitting shows the lead as stored.
- **What the form can show:** at 2.41.3 a Form Trigger renders its page without running the workflow, so it can't read a Data Table. Its expressions do see the request (`$json.query`, `webhook-context.js`), so the description shows the title and company from the link (HTML-escaped, then n8n's own sanitizer). `lead` and `sig` fill two hidden fields from the query (`prepareFormData` in `Form/utils/utils.ts`; at 2.41.3 this also works on the test URL).
- **Fields:** title "Pass on this lead"; **Reason**, a required dropdown of the ten labels; **Anything else? (optional)**, a textarea with the Hermes placeholder; button "Pass"; no n8n attribution; Ignore Bots on (bots get 401).
- **Form Trigger version 2.1, not 2.6:** from 2.2 on, a Form Trigger refuses to run when any Respond to Webhook node follows it (`validateResponseModeConfiguration`; it checks every node downstream), and every trigger here leads through **Route by trigger** to **Show page**. Version 2.1's "Using Respond to Webhook node" mode answers the form through **Show page**; the form page puts the returned HTML in place of the form, whatever its status. Moving to 2.2+ would mean form-ending pages (n8n Form node) and a webhook response that isn't a Respond to Webhook node.
- **On submit:** a bad or missing signature gets 403 "Invalid link" and changes nothing; an unknown lead 404; no reason, or one that isn't one of the ten labels, 400 "Pick a reason" (the form also requires it). A New or Picked lead becomes `passed` with `passed_at`; an Applied lead gets 409 and isn't changed. The reason code, the note and the date go in `passes`, one row per lead (upsert on `lead_key`).
- **Passing again** (decided for #13): the lead keeps its status and first `passed_at`, and the passes row gets the new reason and note (an empty note clears the old one). So a wrong reason can be fixed from the same link, and `passes` never holds two rows for one lead.
- **Never sent again:** the scan reads only `new` leads, so a Passed lead is never sent.
- **Schema:** `passed_at` (date) on `leads` (added to both tables, rows kept, and to the create step); new table `passes` (`lead_key`, `reason_code`, `note`, `passed_at`), created in the setup chain.
- **Still to check on the phone (#15):** whether Telegram fetches button URLs. "Ignore Bots" answers known bots with 403, and a GET from a real browser acts at once. Opening the Pass form changes nothing; only submitting it does.

**People search** (dropped 2026-10-01)
- No Claude people search. A "Search LinkedIn" button opens LinkedIn's own people search, prefilled; Rahat browses by hand. No LinkedIn automation (ADR 0002).

**Tracking**
- **n8n Data Tables**, stored in local n8n's SQLite database:
  - `leads`: status and a date for each status change, plus referral.
  - `passes`
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
  - Built in issue #10 (2026-10-01): n8n retries a node only when its first item fails, and then re-sends every item (`workflow-execute.js`, `checkFailure` reads `data[0][0].json.error`). So **Ask Jev** sends each request once with no node retry, and the requests that failed go to **Ask Jev again**: a second try, and up to two more tries 5 s apart if the first of them fails again.
  - A lead that still fails gets `scoring_state` `unscored` and `selection_reason` `unscored`. It isn't sent, and the next scan judges it again because only `scored` leads with an unchanged fingerprint are skipped.
  - The header adds "· N couldn't be scored (retrying next scan)" only when N > 0.
  - If Claude's fit line fails for a lead, the lead is still sent, without a fit line. Claude has no second pass (only the node's own retry, when the first item fails).
- **Sending:**
  - The minimum fit score is 60 (config).
  - New leads that miss the daily cap stay New and compete later.
  - A lead is never sent twice.
  - The first scan scores everything and sends the top 10 as usual.
- **Freshness window:** 30 days (config), counted from when Job Scout first sees the lead; New leads first seen longer ago are no longer sent. The freshness sub-score decays by the posting's age (the earlier of published and first seen) over the same 30 days, so old postings rank lower but aren't excluded on day one (decided 2026-09-30).
- **Closed:** when a posting disappears from its board, the lead is marked Closed quietly, with no message.
  - Only boards fetched successfully in that scan close leads; a failed fetch closes nothing (built in issue #7, 2026-10-01).
  - `closed_at` is recorded whatever the lead's status (New, Picked, Applied, Passed, or filtered). A closed lead is never judged or sent, and its `selection_reason` is `closed`.
  - If the posting is listed again, `closed_at` is cleared and the lead is open again (same key, no new lead).
- **Reading boards** (issue #7, 2026-10-01; checked against the live Instacart, Palantir and Spotify boards):
  - Greenhouse: the location comes from `location.name` only, and the workplace type is read from it ("Remote", "Hybrid", "on-site"). The `offices` list is ignored, because Instacart's Canada copies of a role list "Remote - United States" as an office.
  - Greenhouse pay: `pay_input_ranges` (one range per group of states at Instacart). Ranges titled OTE, commission, bonus or incentive are skipped. The ranges carry no interval, so amounts under $1,000 are taken as hourly.
  - Lever: live `workplaceType` is `onsite`, `hybrid` or `remote`; `on-site` (the docs' spelling) is also accepted. `country` places the primary location, and `allLocations` are secondary locations. Pay comes from `salaryRange` in USD per year or per month. Lever has no company name, so the company is the site name, as with Ashby.
  - Location: a non-remote place with no city is "Location unclear" only when it names the US or a metro's region ("United States", "Texas"); a lone city outside the metros ("Stockholm", "San Francisco- Hybrid") fails. Common non-US cities and countries are listed for places with no country code.
- **Empty day:** a short "no new leads" message with counts: scanned, filtered, unscored.
  - Built in issue #10 (2026-10-01) as one silent message: "Job Scout: no new leads today" and "N postings scanned · N filtered out · N couldn't be scored". Scanned counts the postings fetched in this scan; filtered counts those that failed a hard rule, including a salary Jev found in the description below the floor; unscored counts the leads whose Jev request still failed.
  - If no board could be fetched at all, the scan fails at Normalize postings on purpose, so the crash alert reports it instead of an empty day.
- **Crash:** an error workflow sends "Job Scout scan failed" with the node and the error to the same chat.
  - **Answer (issue #10, 2026-10-01): the workflow can be its own error workflow, with no setting at all.** In n8n 2.41.3 (`execute-error-workflow.js`), when a run fails and the workflow has no `settings.errorWorkflow`, n8n runs the failing workflow's own Error Trigger ("Start internal error workflow"), for any mode except `error`. Setting `errorWorkflow` to the workflow's own ID also works; the only check is that a run in `error` mode doesn't call itself again. Either way n8n runs the published version (`loadErrorWorkflowData`), and only for non-manual runs (`execution-lifecycle-hooks.js` skips mode `manual`).
  - So Job Scout has an Error Trigger (**Scan crashed**) → **Build crash alert** → **Send crash alert**. Nothing has to be set after a template import. The alert reads the chat ID from the config node's parameters (`$('Job Scout config').params`), which works without that node running, so `telegramChatId` must stay a plain value.
  - Text: "Job Scout scan failed at <step>: <error>" plus a link to the failed execution. A Code node's error carries no node name, so the step comes from `execution.lastNodeExecuted`, which is the node that failed.
  - Checked once for real on 2026-10-01: a published copy with a broken Board list node, run in production mode through MCP, failed (execution mode `trigger`), n8n ran its own Error Trigger (mode `error`), and Telegram returned `ok: true` for a "[Test]" alert. The copy was deleted.
- X data is stored as IDs, handles and links only.
- **MCP "set lead status"** can also move a lead back to New, as the undo path.

**Build shape** (ADR 0005)
- An n8n gallery template is one workflow JSON, so Job Scout is one workflow with several triggers.
- Importing a template drops workflow settings. The crash alert doesn't need one: the workflow's own Error Trigger runs when no error workflow is set (issue #10). A sticky note says so.

**Docs for ticket work**
- `CONTEXT.md`: the glossary (lead, posting, board, hiring post, pass, fit score, and so on).
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
