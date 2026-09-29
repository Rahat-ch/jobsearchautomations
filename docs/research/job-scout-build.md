# Job Scout on n8n: build research

Research date: 2026-09-29. Sources: n8n docs (docs.n8n.io, fetched as `.md` on 2026-09-29), n8n source at tag `n8n@2.41.3`, the n8n pricing page, the n8n Creator hub (Notion), Lever's `postings-api` README, Greenhouse Job Board API docs, Ashby's public job posting API docs, Anthropic's models overview, and Cloudflare's Quick Tunnels docs. I also made live, unauthenticated GET calls to the Ashby, Greenhouse and Lever public board APIs on 2026-09-29 (Ramp, Vercel, Palantir, Spotify and Zoox boards, plus n8n's own board).

**Labels.** **[Doc]** means a primary doc states it, cited inline. **[Source]** means I read it in n8n's source code at `n8n@2.41.3`. **[Observed]** means I saw it in a live API response on 2026-09-29. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

Local inputs read: `~/dev/hermes-job-board/feedback-loop-spec.md`, `~/dev/hermes-job-board/seed-data.json`, and `~/Desktop/resumes/general/Rahat Chowdhury Resume 2026.html` (about 800 words of text once tags are stripped).

---

## 1. Summary and recommended stack

- **Hosting: build and record on n8n Cloud, and keep a self-hosted Docker copy as a fallback.**
  - The n8n posting points applicants to Cloud: "try n8n out ... and share a screenshot of your first workflow with us. The easiest place to start is here: app.n8n.cloud/register" [Observed, n8n's Ashby board, "Senior Developer Advocate, US", published 2026-09-29].
  - Cloud gives public HTTPS webhook and form URLs with no tunnel. That matters for the Slack/Discord Apply/Pass flow (section 2.3).
  - The Cloud trial is 14 days with Pro features and a cap of 1000 executions. After it expires, n8n deletes the workspace, and you have 90 days to download your workflows [Doc: start-your-free-trial].
  - For daily use after the trial, the choice is Rahat's: Cloud Starter at 20€/mo billed annually (2.5K executions), or free self-hosted Community edition in Docker [pricing page; Doc: choose-how-to-use-n8n]. The flows are the same either way. Self-hosted on a laptop means Slack's in-app buttons and phone-based Pass forms need a tunnel.
- **LLM: the Anthropic Chat Model sub-node, with `claude-sonnet-5-5`.**
  - Anthropic is supported natively, and the model list is fetched live from Anthropic's API [Source].
  - Sonnet 5.5 costs $2/$10 per MTok. Its retirement is "not sooner than September 28, 2027" [Anthropic models overview].
  - Avoid Haiku 4.5 for a long-lived build. Its retirement is "not sooner than October 15, 2026", which is two weeks out.
- **Chat channel: Slack if you use Cloud or a tunnel, Discord if you stay on localhost.**
  - Slack's Send-and-Wait approvals resolve inside Slack and record who clicked. That demos well, but it needs public HTTPS and the app's signing secret [Doc: Slack approvals].
  - Discord's Send-and-Wait buttons are link buttons that open an n8n page [Source]. That also works, but it looks less native.
- **Persistence: n8n Data Tables.** They are on every Cloud plan and in the self-hosted Community edition. The default limit is 200 MiB per instance, and the node has "If Row Does Not Exist" for dedupe [Doc: data-tables; pricing page].
  - Postgres is only worth it if the data must outlive n8n or be queried elsewhere.
  - Skip Google Sheets. It adds OAuth setup and makes the template heavier.
- **Pass-reason capture: an n8n Form Trigger opened from a "Pass" link in the digest, not one Send-and-Wait per lead.** Forms accept query parameters to prefill fields such as `lead_id` [Doc: Form Trigger]. One scan run then ends cleanly instead of leaving N executions waiting.
  - Send-and-Wait approval is the right fit for the feedback loop's "Apply to brief / Dismiss" confirmation, because that needs exactly one decision per proposal.

---

## 2. Findings per question

### 2.1 n8n version, Cloud vs self-hosted, limits, gated features

**Version**
- Latest stable is **2.41.3**, released 2026-09-25. Beta is **2.42.0**, released 2026-09-29. The GitHub releases API marks `n8n@2.41.3` as `latest`, and npm dist-tags show `latest`/`stable` = 2.41.3 and `beta`/`next` = 2.42.0 ([GitHub releases](https://github.com/n8n-io/n8n/releases), [npm](https://registry.npmjs.org/n8n)). The Docker doc prints "Current `stable`: 2.41.3 Current `beta`: 2.42.0" ([install-with-docker](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-docker.md)).
- "n8n releases a new minor version most weeks" [Doc: install-with-docker].
- **n8n 3.0 is due in October 2026.** From 3.0, "n8n is only distributed through Docker", and the `npm install n8n` / `npx n8n` approach "no longer works" ([one-line-setup](https://docs.n8n.io/deploy/host-n8n/install-options/one-line-setup.md)). AI Agent node v1 "will be removed from n8n 3.0" ([AI Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent.md)).

**Self-host install commands (exact, from docs)**

The docs now mark the plain `docker run` page as "**This content is outdated.** Please refer to Install using Docker Compose" [Doc: install-with-docker]. The recommended paths are:

1. The one-line setup, which writes a Compose project with n8n, a code sandbox for n8n Assistant, and SearXNG ([one-line-setup](https://docs.n8n.io/deploy/host-n8n/install-options/one-line-setup.md)):
   ```bash
   curl -fsSL https://get.n8n.io | sh
   # stop:  docker compose -f ./n8n/compose.yml down
   # start: docker compose -f ./n8n/compose.yml up -d
   ```
   It needs the `docker compose` v2 plugin. It uses SQLite by default.
2. A hand-built Compose file, using [`docker/get-n8n-compose.yml`](https://github.com/n8n-io/n8n/blob/master/docker/get-n8n-compose.yml) plus a `.env`, then `docker compose up -d`. This path needs at least 4 GB RAM and 2 vCPUs because of the Docker-in-Docker sandbox ([install-using-docker-compose](https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md)).
3. The older single container. It is still documented, but flagged as outdated [Doc: install-with-docker]:
   ```shell
   docker volume create n8n_data

   docker run -it --rm \
    --name n8n \
    -p 5678:5678 \
    -e GENERIC_TIMEZONE="<YOUR_TIMEZONE>" \
    -e TZ="<YOUR_TIMEZONE>" \
    -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
    -e N8N_RUNNERS_ENABLED=true \
    -v n8n_data:/home/node/.n8n \
    n8nio/n8n
   ```
   `N8N_RUNNERS_ENABLED` "is deprecated from n8n 2.0. You no longer need to set it" [same page]. **[Inference]** For Job Scout, this single container is enough. The Compose stack's sandbox only serves n8n Assistant, which Job Scout doesn't need. Use `GENERIC_TIMEZONE=America/Chicago` so the Schedule Trigger fires on DFW time.

**Cloud trial and plans**
- The trial is 14 days with Pro features, "a limit of 1000 executions and the same computing power as the Starter plan". When it ends, "n8n deletes your workspace". You have 90 days to download workflows ([start-your-free-trial](https://docs.n8n.io/deploy/use-n8n-cloud/start-your-free-trial.md)).
- Pricing page, as rendered 2026-09-29 ([n8n.io/pricing](https://n8n.io/pricing/)):

  | Plan | Price | Executions |
  |---|---|---|
  | Starter | 20€/mo billed annually | 2.5K/mo |
  | Pro | 50€/mo | 10K |
  | Business | 667€/mo, self-hosted only | 40K |

  Concurrent executions are 5 on Starter, 20 on Pro and 200+ on Enterprise. Workflow history is 1 day on Starter and 5 days on Pro. "Data tables" is listed under Core features for Starter, Pro and Enterprise. Pricing is "based on monthly workflow executions, regardless of complexity."
- Cloud-only: **Gateway credits.** These run Anthropic and other models without your own API key, on Cloud Starter and Pro from n8n 2.36.0. They aren't available on Cloud Enterprise or self-hosted. Trials include some free credit, but "Topping up isn't available during a free trial" ([gateway-credits](https://docs.n8n.io/deploy/use-n8n-cloud/gateway-credits.md)).
- Cloud-specific limits:
  - Cloud Code nodes can't import external npm modules. Only `crypto` and `moment` are available.
  - Cloud Python Code nodes can't import any libraries ([Code node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code.md)).

**What the free self-hosted Community edition lacks**

Custom variables, environments, external secrets, external binary storage, log streaming, multi-main, projects, SSO, workflow and credential sharing, and Git version control ([compare editions](https://docs.n8n.io/deploy/host-n8n/community-edition-features.md)). Free registration adds folders, debug in editor, and custom execution data (same page). **[Inference]** Job Scout needs none of the paid features.

**Trade-offs for this project [Inference]**

| | Cloud (trial, then Starter) | Self-hosted Docker on the Mac |
|---|---|---|
| Public URLs for Slack/Discord/forms | Yes, out of the box | Needs a tunnel, and the URL changes on each quick-tunnel restart |
| Runs while the laptop sleeps | Yes | No. The default in-memory scheduler skips missed runs (2.5) |
| Cost | Trial free, then 20€/mo | Free, plus LLM tokens |
| Matches the application's ask | Yes (app.n8n.cloud/register) | Yes, any workflow screenshot |
| Credentials, resume text | Stored at n8n | Stay local |

### 2.2 AI Agent, Structured Output Parser, chat model providers, Claude

**AI Agent node**
- "Connect a chat model and one or more tools, and the agent decides which tools to call." The agent-type setting is deprecated, and all agents are Tools Agents ([AI Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent.md)).
- The docs say "You must connect at least one tool". The current v3 node source marks `ai_tool: { required: false }` and `ai_languageModel: { required: true }` [Source: `AgentV3.node.ts`]. **[Inference]** A tool-less scoring agent should work on v3. Verify in the editor.
- New in 2.40: "Force Tool Call on First Iteration", an option that is off by default ([release notes](https://docs.n8n.io/changelog/release-notes.md)).

**Structured output**
- Turn on **Require Specific Output Format** on the root node, then attach a Structured Output Parser. The parser takes either a JSON example (every field becomes required) or a JSON Schema. `$ref` isn't supported ([Structured Output Parser](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.outputparserstructured.md)).
- The Tools Agent "passes the parser to the model as a formatting tool" ([Tools Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent.md)).
- Caveat: "Structured output parsing is often not reliable when working with agents ... n8n recommends using a separate LLM-chain" ([parser common issues](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.outputparserstructured/common-issues.md)).
- **[Inference]** Scoring doesn't need tools. The **Basic LLM Chain** with the same parser is the more reliable choice, and there is also an **Information Extractor** node. For the demo, an AI Agent node reads better on screen. A fair compromise: use the AI Agent node, and add an Auto-fixing Output Parser or a retry if the parser fails.
- Sub-node gotcha: "In sub-nodes, the expression always resolves to the first item." Put per-posting expressions in the root node's prompt, not in sub-node fields [same pages].

**Chat model providers**

The docs list these chat model sub-nodes: Anthropic, AWS Bedrock, Azure AI Foundry, Cohere, Databricks, DeepSeek, Google Gemini, Google Vertex, Groq, Lemonade, MiniMax, Mistral Cloud, Moonshot Kimi, NVIDIA Nemotron, Ollama, OpenAI, OpenRouter, Qwen Cloud, Vercel AI Gateway and xAI Grok ([docs sitemap](https://docs.n8n.io/sitemap.md)).

**Claude**
- Supported natively through the **Anthropic Chat Model** sub-node (`lmChatAnthropic`). The separate **Anthropic** app node has "Message a Model", document and image analysis, and file operations. Auth is an API key ([Anthropic credentials](https://docs.n8n.io/integrations/builtin/credentials/anthropic.md)).
- The docs page still lists models as "Claude / Claude Instant", which is stale ([Anthropic Chat Model doc](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.lmchatanthropic.md)). The source is current:
  - Node versions 1.3 and later use a searchable list, populated by `listAnthropicModels` against the credential's base URL (default `https://api.anthropic.com`). Any model your key can see is selectable, or you can enter an ID [Source: `LmChatAnthropic.node.ts`, `methods/searchModels.ts`].
  - The newest node version (1.6) defaults to `claude-sonnet-5` [Source].
  - The node has Adaptive thinking with an Effort level (`low` to `max`). It drops temperature and top_p/top_k for models that reject them, such as Opus 4.7 and later [Source].
  - Docs list Prompt Caching options: Disabled, 5 min or 1 h [Doc].
- Current Anthropic lineup ([models overview](https://platform.claude.com/docs/en/models/overview)):

  | Model | API ID | Price per MTok (in/out) |
  |---|---|---|
  | Fable 5.1 | `claude-fable-5-1` | $10/$50 |
  | Opus 5.5 | `claude-opus-5-5` | $4/$20 |
  | Sonnet 5.5 | `claude-sonnet-5-5` | $2/$10 |
  | Haiku 4.5 | `claude-haiku-4-5` | $1/$5 |

  Sonnet 5 is now listed as legacy.
- On Cloud, the Anthropic nodes can use Gateway credits instead of a key [Doc: lmchatanthropic].

**Cost estimate [Inference]**

- Assume about 1.5k tokens of resume, about 1k of instructions, about 2 to 3k of posting text, and about 400 output tokens. That is roughly $0.01 to $0.015 per posting on Sonnet 5.5.
- Pre-filter by title and location before the LLM. Ramp alone listed 155 jobs [Observed].

### 2.3 Human-in-the-loop

**Send and Wait for Response**
- The operation exists on these nodes [Source: `packages/nodes-base/.../sendAndWait*` at 2.41.3]:
  - Slack
  - Discord
  - Telegram
  - Gmail
  - Microsoft Outlook
  - Microsoft Teams
  - Google Chat
  - WhatsApp
  - Send Email (SMTP)
- They share one implementation with three **Response Types** [Source: `utils/sendAndWait/utils.ts`; Doc: [Discord](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.discord.md)]:

  | Response Type | What the user gets |
  |---|---|
  | Approval | Approve only, or Approve plus Disapprove, with custom labels |
  | Free Text | A button that opens a form |
  | Custom Form | A button that opens a form with defined fields, such as a dropdown of reason codes plus a textarea |

  All three support **Limit Wait Time**, as an interval or a date.
- **How buttons work:** by default, buttons are signed links to an n8n page. "Anyone who has the link can respond" ([Slack approvals](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/approvals.md)). Discord builds them as Discord link buttons, component `style: 5` with a `url` [Source: `Discord/v2/helpers/utils.ts`]. **Free text and forms always open a browser page.**
- **Slack native approvals:**
  - Turn on "Capture Who Responded" to get clicks handled inside Slack. The output records the responder, and approvers can be restricted.
  - Requirements: "Your n8n instance to be reachable from Slack over public HTTPS ... an instance running on localhost won't work."
  - Set Interactivity Request URL = `https://<host>/webhook-waiting-slack`, and put the app's Signing Secret in the credential. This works only for the Approval response type. Free Text and Custom Form fall back to link buttons [Doc: Slack approvals].
- **Discord Send and Wait** needs a Bot or OAuth2 credential, not a Discord webhook credential [Source: `Discord/v2/actions/message/index.ts`].

**Wait node**
- Resumes after a time interval, at a specified time, on a webhook call (`$execution.resumeUrl`, with optional auth), or on a form submission ([Wait](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.wait.md)).
- Waits of 65 s or longer offload execution data to the database.
- Has an "Ignore Bots" option for link previewers.

**Form Trigger / n8n Form**
- Has Test and Production URLs. The workflow must be published to use the Production URL.
- Fields can be **prefilled from query parameters**, in production only.
- Auth options are Basic Auth or n8n User Auth ([Form Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.formtrigger.md)).
- **[Inference]** This is the cleanest way to build per-lead Pass links: `https://<host>/form/job-scout-pass?lead_id=ashby%3Aramp%3A<uuid>`. The form holds a reason dropdown with the spec's codes and an optional note. Each submission is its own short execution, so there are no long-lived waiting executions per lead.

**AI Agent tool approval**

The AI Agent can also require human approval before specific tools run ([human-in-the-loop-for-tools](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md)). It isn't needed here.

**Localhost, webhooks and tunnels**
- n8n builds webhook URLs from `N8N_PROTOCOL`, `N8N_HOST` and `N8N_PORT`. Behind a proxy or tunnel, set `N8N_WEBHOOK_URL`, which replaces `WEBHOOK_URL` as of 2.35.0, and set `N8N_PROXY_HOPS=1` ([reverse proxy](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/configure-webhook-urls-with-reverse-proxy.md), [endpoints env vars](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md)).
- n8n's documented tunnel (`pnpm stack --tunnel`) runs from an n8n source checkout, not from the Docker image [Doc: install-with-docker].
- For a Docker install, the practical path is Cloudflare's Quick Tunnel: `cloudflared tunnel --url http://localhost:5678`. It gives a random `trycloudflare.com` subdomain and is "intended for testing and development only" ([Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)). **[Inference]** The URL changes on every restart, so old digest links break. A named Cloudflare tunnel on a domain avoids that.
- **[Inference]** Without a tunnel, link buttons and form links point at `http://localhost:5678/...`. They work only when clicked on the Mac that runs n8n, not from a phone.
- **[Unverified]** Whether Discord's API accepts `http://localhost` URLs in link buttons. Test it before relying on it.

### 2.4 Persistence: dedupe and pass reasons

**Data Tables**
- Built-in tables you can manage from the node, from the UI tab (CSV import and export) or from the `/datatables` API ([data tables](https://docs.n8n.io/build/work-with-data/data-tables.md)).
- Limits:
  - "By default, the total storage used by all data tables in an instance is limited to 200 MiB". Self-hosted can raise this with `N8N_DATA_TABLES_MAX_SIZE_BYTES`.
  - At the limit, inserts and updates fail.
  - "Direct programmatic access to data tables from a Code node isn't supported" (same page).
- Node operations: Get, Insert, Update, Upsert, Delete, **If Row Exists**, and **If Row Does Not Exist** ([Data Table node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable.md)).
- Availability: listed as a Core feature on Cloud Starter, Pro and Enterprise [pricing page]. They are not in the Community edition's list of excluded features [Doc: compare editions].
- **[Inference]** Three tables fit well within limits:
  - `leads`: `lead_id`, company, title, URLs, location, comp, fit, gaps, status, and first_seen.
  - `passes`: `lead_id`, reason_code, note, and ts.
  - `rules`: key, value, and updated_by.

**Remove Duplicates node**
- The "Remove Items Processed in Previous Executions" operation keeps a history of up to 10,000 items by default, scoped per node or per workflow ([Remove Duplicates](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.removeduplicates.md)).
- **[Inference]** It's fine for "seen before". But you can't read or annotate its history, so a Data Table is better when the same rows feed the digest and the feedback loop.

**Alternatives [Inference]**
- **Postgres node:** durable and queryable outside n8n. On self-hosted it could share the n8n Postgres instance if you move off SQLite ([Compose Postgres option](https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md)). It adds setup for anyone who imports the template.
- **Google Sheets:** easy to eyeball and edit by hand. It adds a Google OAuth credential and has quota concerns. It hurts plug-and-play for a template.

### 2.5 Code node and Schedule Trigger

**Code node**
- JavaScript (Node.js, promises, `console.log`) runs in "Run Once for All Items" or "Run Once for Each Item" mode.
- It can't touch the file system or make HTTP requests. Use Read/Write Files and HTTP Request nodes instead ([Code](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code.md)).
- Modules: external npm modules are self-hosted only. Cloud has only `crypto` and `moment`.
- Python:
  - Native Python runs through task runners and is stable in n8n 2. Pyodide is gone in n8n 2.
  - Native Python supports only `_items`/`_item` and bracket access.
  - On Cloud, Python can't import any library (same page).
- Task limits (self-hosted defaults): `N8N_RUNNERS_TASK_TIMEOUT` = 300 s per task, and `N8N_RUNNERS_MAX_PAYLOAD` = 1 GiB ([task-runner env vars](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/task-runners.md)).
- `EXECUTIONS_TIMEOUT` defaults to `-1` (off), and `EXECUTIONS_TIMEOUT_MAX` defaults to 3600 s ([llms-full export of the executions env vars](https://docs.n8n.io/llms-full.txt)).
- **[Inference]** Normalizing three ATS payloads and applying location rules is well within these limits. Use JavaScript, since Python on Cloud is more restricted.

**Schedule Trigger**
- Intervals run from seconds to months, plus custom cron with an optional seconds field. The workflow must be published ([Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger.md)).
- Timezone: the workflow setting wins, then the instance setting. The self-hosted default is `America/New York`, and Cloud detects the owner's timezone at signup.
- Changes to the interval or to variables take effect only after re-publishing. The schedule counts from publish time ([common issues](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/common-issues.md)).
- **Missed runs.**
  - The default in-memory scheduler "never runs missed executions".
  - The durable scheduler (2.36+) is off by default. It needs both `N8N_SCHEDULER_ENABLED=true` and `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=true`.
  - With it on, the node's "If Execution Is Missed" setting can run a catch-up execution ([durable scheduler](https://docs.n8n.io/deploy/host-n8n/configure-n8n/durable-scheduler.md)).
  - **[Inference]** This matters if the Mac is asleep at 7am.

### 2.6 Import and export of workflow JSON; credentials

- Workflows are JSON. Editor menu options: Download, Import from URL, Import from File, or copy-paste nodes ([export and import](https://docs.n8n.io/build/manage-workflows/export-and-import.md)).
- Credential handling:
  - "Exported workflow JSON files include credential names and IDs" but not the secrets.
  - The warning also says "HTTP Request nodes may contain authentication headers when imported from cURL". Remove or anonymize those before sharing (same page).
- **[Inference]** Anything hardcoded in a Set or Code node travels with the export. That includes resume text, a Slack channel ID and a Discord guild ID.
- CLI:
  - `n8n export:workflow --id=<ID> --output=file.json`.
  - `n8n export:credentials` exports credentials in encrypted form by default. The `--decrypted` flag exports them in plain text ([CLI](https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line.md)).
  - The newer `.n8np` package format through the n8n CLI is in Preview [Doc: export and import].
- Cloud: workflows can be downloaded from the admin dashboard, including for 90 days after a trial ends [Doc: start-your-free-trial].

### 2.7 Template gallery (Creator program)

- Process ([n8n Creator hub](https://n8n.notion.site/n8n-Creator-hub-7bd2cbe0fce0449198ecb23ff4a2f76f), linked from [use templates](https://docs.n8n.io/build/ways-of-building-workflows/use-templates.md)):
  1. Register at `creators.n8n.io`.
  2. Export the workflow JSON.
  3. Write a description.
  4. Submit it in the Creator Dashboard.
- Throttle for new creators: "New (unverified) creators can submit one template at a time, and can only submit another after the previous one is approved." After 3 approved templates you become verified, which allows batches of up to 4 and paid templates.
- Main rules ([Template submission guidelines](https://n8n.notion.site/99598944767340dab402c90b124b1f77)):
  - Sticky notes are "mandatory".
  - "Don't use hardcoded API keys in the HTTP node".
  - Remove personal identifiers such as sheet IDs, channels and emails.
  - Rename all nodes.
  - Use a Set node to group user-configurable variables.
  - Titles follow "Action verb thing being manipulated to/on/in/from where" in sentence case, with no emojis.
  - Descriptions run about 200 words, in Markdown with no HTML. Suggested sections are Who's it for / How it works / How to set up / Requirements / How to customize.
  - Low-effort templates "won't get published".
- Sticky note rules ([Sticky note guidelines](https://n8n.notion.site/2aa5b6e0c94f8058b0aefddd02655887)):
  - Exactly one yellow overview sticky, top-left, 100 to 300 words, with `### How it works` and `### Setup`.
  - White section stickies are required for workflows of 4 or more nodes, under 50 words each.
  - Red warning stickies are optional and sparing.
- **Review timeline: not documented.** The hub's "Approval Process" heading has no body text [Observed]. The docs note "n8n is working on a creator program ... details are likely to change" [Doc: use templates].

### 2.8 ATS public APIs

| | Ashby | Greenhouse | Lever |
|---|---|---|---|
| List endpoint | `GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true` ([Ashby docs](https://developers.ashbyhq.com/docs/public-job-posting-api)) | `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true` ([Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)) | `GET https://api.lever.co/v0/postings/{SITE}?mode=json` (EU: `api.eu.lever.co`), with `skip`/`limit` ([Lever README](https://github.com/lever/postings-api/blob/master/README.md)) |
| Single job | Not needed; the list includes descriptions | `.../jobs/{job_id}?pay_transparency=true` | `.../postings/{SITE}/{POSTING-ID}` |
| Auth for GET | Not stated in docs. Worked unauthenticated [Observed] | "authentication is not required for any GET endpoints" | "GET requests require no authentication" (POST needs a key) |
| Rate limits | Not documented. Response had `cache-control: public, max-age=60` [Observed] | Not documented for the Job Board API | Documented only for application POSTs (2/sec, then 429) |
| Location | `location`, `secondaryLocations[].location`, `address.postalAddress` | `location.name` (free text such as "Remote - United States", "Hybrid - San Francisco") and `offices[]` | `categories.location`, `categories.allLocations[]`, `country` (ISO-2) |
| Remote status | `isRemote` (bool) and `workplaceType` (`OnSite`/`Remote`/`Hybrid`) | No field. Parse `location.name` | `workplaceType`, documented as `unspecified`/`on-site`/`remote`/`hybrid` |
| Compensation | `compensation.compensationTierSummary`, `scrapeableCompensationSalarySummary`, `summaryComponents[]` (`minValue`, `maxValue`, `currencyCode`, `interval`), plus `shouldDisplayCompensationOnJobPostings` | `pay_input_ranges[]` (`min_cents`, `max_cents`, `currency_type`) when `pay_transparency=true` | `salaryRange{currency, interval, min, max}` (optional), plus `salaryDescription` |
| Description | `descriptionPlain`, `descriptionHtml` | `content` (HTML-escaped) | `descriptionPlain`, `lists[]`, `additionalPlain` |

**Observed quirks (2026-09-29)**
- **Ashby / Ramp:**
  - 155 jobs. `workplaceType`: 126 Hybrid, 15 OnSite, 14 Remote.
  - `isRemote` was `true` on 140 of them, so **`isRemote` isn't a usable remote signal.**
  - 29 Hybrid jobs have a `Remote (US)` entry in `secondaryLocations`. Example: "Software Engineer, Frontend" has primary location "New York, NY (HQ)", `workplaceType: Hybrid`, and secondary locations Remote (Canada), San Francisco, Remote (US) and Miami.
  - Some `workplaceType: Remote` jobs have primary location "New York, NY (HQ)".
  - Compensation came back on all 155 jobs, but `shouldDisplayCompensationOnJobPostings` was false on 7.
- **Greenhouse / Vercel:** 91 jobs, 8 of them "Remote - United States". `pay_input_ranges` was empty even with `pay_transparency=true`, on both the list and single-job endpoints. The salary appeared only inside `content` HTML ("$208,000 - $312,000"). **Expect to parse comp from the description.**
- **Lever:**
  - Live `workplaceType` values were `onsite`/`hybrid`/`remote` (Palantir, Spotify, Zoox). The README says `on-site`. Match both.
  - `salaryRange` was present on 189 of 200 Zoox postings and 0 of Palantir's 318 or Spotify's 80.
  - Unknown sites return `{"ok":false,"error":"Document not found"}`.
- **n8n itself** is on Ashby. The job board name is `n8n`. "Senior Developer Advocate, US" has `workplaceType: Remote` and location "United States" [Observed]. **[Inference]** It makes a natural first result in the demo.

**Remote-US filter [Inference], ordered strictest first.** Hermes' `location_not_real` pass reason is about exactly this case.
1. `workplaceType == Remote` (or Lever `remote`), and the primary location is US or the text says "Remote (US)" or "United States".
2. `workplaceType == Hybrid`, with "Remote (US)" only in `secondaryLocations`. Mark it `remote_basis = "secondary_only"` and let the LLM read the description for hub or office requirements. Don't auto-accept it.
3. Greenhouse: `location.name` matches `/^remote\b.*(united states|us\b|usa)/i`.
4. The DFW-hybrid exception from the Hermes profile (base Frisco, TX): hybrid and location contains Dallas, Frisco, Plano or Austin(?). **Rahat should confirm Austin** (see section 5).

### 2.9 Short demo video for a DevRel application [Opinion]

- The posting asks for a workflow screenshot, not a video. A video is extra, so keep it short: 90 seconds to 2.5 minutes.
- Suggested structure:
  1. **Problem (10 s):** "I job-hunt with a custom agent; here it is rebuilt in n8n."
  2. **Canvas tour (30 s):** show the stickies and the three stages.
  3. **Live run (45 s):** scan, then the scored digest lands in Slack or Discord. The n8n Senior DevRel role should appear.
  4. **Pass flow (30 s):** click Pass, pick "Remote claim is soft", and see the row in the Data Table.
  5. **Feedback loop (30 s):** a proposed rule arrives, you click Apply to brief, and the rules table updates.
  6. **Close (10 s):** the template link and what you'd teach with it.
- Record at 1080p with the canvas zoomed to fit. Pin data on the scan nodes so the run is deterministic. Show one real failure-handling detail, such as the Ashby `isRemote` trap. Real edge cases play better with a technical audience than a clean happy path.

---

## 3. Build plan

Assumes Cloud trial first. Effort figures are rough [Opinion].

### (a) MVP: screenshot- and demo-ready (about 1 day)
1. Build a **Schedule Trigger** (daily, workflow timezone America/Chicago) plus a **Manual Trigger** for demos.
2. Add a **Set "Config"** node:
   - The company list as `[{company, ats, board}]`. Seed it from the seed-data companies plus n8n.
   - Title keywords.
   - Comp floor.
   - Resume text, pasted as plain text for the MVP.
3. Split the list, run a **Switch on `ats`**, then call three **HTTP Request** nodes.
4. Add a **Code "Normalize"** node (JavaScript). It outputs one schema: `lead_id = ats:board:jobId`, company, title, url, apply_url, location_text, workplace, remote_basis, comp_min, comp_max, comp_text, description_plain, published_at.
5. Add a **Filter** for title keywords and the remote-US rules from 2.8.
6. Dedupe with **Data Table `leads` → If Row Does Not Exist** on `lead_id`, then a **Limit** node (for example 15) for cost control.
7. Score with an **AI Agent** (or Basic LLM Chain) using the **Anthropic Chat Model** (`claude-sonnet-5-5`) and a **Structured Output Parser**. Example schema: `{fit_score: 0-100, sub_scores:{role_seniority, technical_overlap, product_ownership, location_certainty, domain_alignment}, gaps: string[], why_fit: string, remote_evidence: string, comp_extracted: {min,max,currency}|null}`.
8. **Data Table Insert** into `leads`, then **Filter** on fit ≥ threshold, **Aggregate**, and a **Code** node that formats the digest.
9. Send the digest with **Slack → Send Message** (Block Kit) or **Discord → Send**. Each lead gets an **Apply** link (the ATS apply URL) and a **Pass** link (the Form URL, prefilled with `lead_id`).
10. Add stickies, rename nodes, pin a sample run, then take the screenshot.

### (b) Daily-usable (about 1 to 1.5 days)
1. Build a **"Job Scout – Pass" workflow**:
   - A Form Trigger with fields `lead_id` (hidden or prefilled), reason (dropdown of the spec's codes, shown with their chip labels) and note (textarea).
   - Data Table Update `leads.status = passed` and Insert into `passes`.
   - Form response text: "Passed. Reason logged for the next scan." (from the spec).
   - Turn on n8n User Auth or Basic Auth.
2. Add a **"Mark applied"** link: a second form, or the same form with an action field. It updates `status = applied`.
3. Move the company list and rules from the Set node into Data Tables `companies` and `rules`, so they can be edited without re-publishing.
4. Add an error workflow and a "0 new leads" digest line, so silence is distinguishable from failure.
5. Decide on hosting. On Cloud Starter, the schedule runs regardless of the laptop. On self-hosted, turn on the durable scheduler plus "Run the Most Recent Missed Execution", and set up a named tunnel if you want links from a phone.

### (c) Feedback loop (about 1 day)
1. Build a **"Job Scout – Learn" workflow**, triggered weekly or after N new passes.
2. Read `passes` since the last review, group them by `reason_code` in a Code node, and apply the spec's threshold ("about 5 with reasons before I propose changes").
3. For each code over the threshold, map it to a candidate rule change. Use the spec's "Hermes adjustment" column: `comp_below_range` raises `comp_floor`, `seniority_mismatch` adds a title exclusion, and so on.
4. Have the LLM write only the human-readable sentence, such as "3 passes for comp below range → raising the floor to $190k". Compute the numbers in code.
5. Send with **Slack (or Discord) → Send and Wait**, response type Approval, double buttons labeled **Apply to brief** / **Dismiss**, and Limit Wait Time of 7 days.
6. On approve, Upsert into `rules` with provenance (lead_ids and date range). On dismiss, write a `dismissed_until = now + 30d` row, per the spec's "I will not propose this again for 30 days".
7. Nothing changes without a click. This matches the spec's "I do not change the brief on my own."

### (d) Template gallery and video (about 1 day, plus review wait)
1. Strip personal data:
   - Resume text becomes a placeholder in the Config Set node, with a sticky explaining how to paste yours.
   - Remove channel and guild IDs and the real company list, or keep a public example list.
2. Add one yellow overview sticky (100 to 300 words, `### How it works` / `### Setup`) and white section stickies.
3. Title it in the required format. Example: "Score remote job postings from Ashby, Greenhouse and Lever against your resume with Claude".
4. Split into two submissions if needed: one template at a time until the first is approved.
5. Record the video per 2.9.

---

## 4. Risks and gotchas

- **n8n 3.0 lands in October 2026.** It removes npm distribution and AI Agent v1 [Doc]. Build on 2.41.x with the current node versions, and state the tested version in the template description.
- **The Structured Output Parser is less reliable on agents** [Doc]. Validate in a Code node, and route failures to a "needs review" branch instead of dropping the lead.
- **Sub-node expressions resolve to the first item only** [Doc]. Keep per-posting data in the root node's prompt.
- **Remote detection:** Ashby's `isRemote` is almost always true on Ramp's board, and `workplaceType` and `secondaryLocations` disagree [Observed]. Lever's docs and live enum spelling differ [Observed vs Doc]. Greenhouse has no structured remote field [Doc].
- **Comp is often only in the description text**, as with Vercel on Greenhouse [Observed]. Have the LLM extract it and store it with `comp_source`.
- **The public board APIs don't document rate limits** for GETs. Scan each board once per run, with a small wait between requests (HTTP Request batching). **[Inference]** Board names differ from company names, and unknown boards return 404 or `Document not found`. Handle errors per company so one bad board doesn't fail the run.
- **Link prefetchers:** Slack and Discord may fetch URLs to build previews. **[Inference]** A GET that changes state, such as "Mark applied" on a plain Webhook, could fire by itself. Use Form URLs (a GET only renders; the POST submits), or turn on "Ignore Bots" on Webhook and Wait nodes [Doc: Wait].
- **Slack in-app approvals need public HTTPS plus a signing secret.** Without the secret, "the buttons render but clicks don't resume the workflow" [Doc].
- **Localhost:** without a tunnel, forms and waiting links open only on the host Mac. Quick-tunnel URLs change on restart [Doc: Cloudflare].
- **Missed schedules on a sleeping laptop** are skipped by default [Doc: durable scheduler].
- **The Cloud trial deletes the workspace** at expiry and caps it at 1000 executions [Doc]. Download the JSON before day 14.
- **Code nodes can't read Data Tables directly** [Doc]. Read the rows with a Data Table node first and pass them in.
- **Model retirement:** Haiku 4.5 is "not sooner than October 15, 2026" [Anthropic]. Pin `claude-sonnet-5-5`, or re-check before choosing Haiku.
- **Exports carry anything hardcoded,** including the resume text with a phone number and email [Inference, based on Doc: export]. Scrub it before sharing or submitting.
- **Stale docs:** the Anthropic Chat Model page still lists "Claude / Claude Instant" [Doc], and the AI Agent page says a tool is required while the v3 source says otherwise [Source]. Trust the editor over those pages.

---

## 5. Open questions for Rahat

1. **Hosting after the trial:** pay for Cloud Starter (20€/mo), or self-host in Docker? If self-hosting, is a named Cloudflare tunnel on a domain you own acceptable?
2. **Channel:** Slack (native in-app approvals, more setup) or Discord (link buttons, and it fits the DevRel/community story)?
3. **Scoring:** Hermes' tooltip says "Scored in code, not by the agent." Should the LLM return sub-scores and a Code node apply fixed weights, or should the LLM return the total?
   - The seed data's maximums suggest weights of 25/20/15/15/10/10/5 [Inference, from max values in `seed-data.json`].
   - Recommendation: sub-scores from the LLM, weights in code.
4. **Pass-reason codes:** the spec lists 10 codes. `seed-data.json` also uses `role_too_backend` and `location_mismatch`, which aren't in the spec's table. Which set is canonical?
5. **Location policy:** Remote-US only, or also DFW hybrid? Which metros count as commutable? Should "Hybrid with Remote (US) as a secondary location" (Ramp pattern) surface as `needs_review` or be dropped?
6. **Target company list:** which companies and board names? Should the public template ship with an example list?
7. **Resume:** use the general resume or the DevRel one? For the template, a pasted-text placeholder or a file read (self-hosted only)?
8. **Comp floor** and the **fit threshold** for the digest.
9. **The video:** show real company names and real postings, or pinned sample data?
10. **Template scope:** publish all three workflows (Scan, Pass, Learn) as one template or several? New creators can have only one submission in review at a time.

---

## 6. Sources

**n8n**
- GitHub releases: https://github.com/n8n-io/n8n/releases
- npm registry: https://registry.npmjs.org/n8n
- Choose how to use n8n: https://docs.n8n.io/choose-how-to-use-n8n.md
- Cloud trial and plans: https://docs.n8n.io/deploy/use-n8n-cloud/start-your-free-trial.md
- Gateway credits: https://docs.n8n.io/deploy/use-n8n-cloud/gateway-credits.md
- Compare editions: https://docs.n8n.io/deploy/host-n8n/community-edition-features.md
- Install with Docker: https://docs.n8n.io/deploy/host-n8n/install-options/install-with-docker.md
- Install using Docker Compose: https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md
- One-line setup: https://docs.n8n.io/deploy/host-n8n/install-options/one-line-setup.md
- Install with npm (tunnel section): https://docs.n8n.io/deploy/host-n8n/install-options/install-with-npm.md
- Compose file: https://github.com/n8n-io/n8n/blob/master/docker/get-n8n-compose.yml
- Reverse proxy webhook URLs: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/configure-webhook-urls-with-reverse-proxy.md
- Endpoint env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md
- Task runner env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/task-runners.md
- Durable scheduler: https://docs.n8n.io/deploy/host-n8n/configure-n8n/durable-scheduler.md
- Scheduler env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/scheduler.md
- Command line: https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line.md
- Release notes: https://docs.n8n.io/changelog/release-notes.md
- AI Agent: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent.md
- Tools Agent: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent.md
- Structured Output Parser: https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.outputparserstructured.md
- Structured Output Parser common issues: https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.outputparserstructured/common-issues.md
- Anthropic Chat Model: https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.lmchatanthropic.md
- Anthropic node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.anthropic.md
- Anthropic credentials: https://docs.n8n.io/integrations/builtin/credentials/anthropic.md
- Docs sitemap (provider list): https://docs.n8n.io/sitemap.md
- Full docs export: https://docs.n8n.io/llms-full.txt
- Slack approvals: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/approvals.md
- Discord node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.discord.md
- Discord credentials: https://docs.n8n.io/integrations/builtin/credentials/discord.md
- Wait node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.wait.md
- Form Trigger: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.formtrigger.md
- Webhook workflow development: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/workflow-development.md
- Human-in-the-loop for tools: https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md
- Data tables: https://docs.n8n.io/build/work-with-data/data-tables.md
- Data Table node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable.md
- Remove Duplicates: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.removeduplicates.md
- Code node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code.md
- Schedule Trigger: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger.md
- Schedule Trigger common issues: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/common-issues.md
- Export and import: https://docs.n8n.io/build/manage-workflows/export-and-import.md
- Use templates: https://docs.n8n.io/build/ways-of-building-workflows/use-templates.md
- Build and manage agents (Preview; not used here): https://docs.n8n.io/build/build-and-manage-agents.md
- Source files at `n8n@2.41.3`:
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/nodes-langchain/nodes/llms/LMChatAnthropic/LmChatAnthropic.node.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/nodes-langchain/nodes/llms/LMChatAnthropic/methods/searchModels.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/nodes-langchain/nodes/agents/Agent/V3/AgentV3.node.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/nodes-base/utils/sendAndWait/utils.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/nodes-base/nodes/Discord/v2/helpers/utils.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/nodes-base/nodes/Discord/v2/actions/message/index.ts
- Pricing: https://n8n.io/pricing/
- Creator program page: https://n8n.io/creators/
- Creator hub: https://n8n.notion.site/n8n-Creator-hub-7bd2cbe0fce0449198ecb23ff4a2f76f
- Template submission guidelines: https://n8n.notion.site/99598944767340dab402c90b124b1f77
- Sticky note guidelines: https://n8n.notion.site/2aa5b6e0c94f8058b0aefddd02655887
- n8n Senior Developer Advocate, US posting: https://jobs.ashbyhq.com/n8n/33e46e4f-85b9-49ca-a010-16586c118c50

**ATS**
- Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api
- Greenhouse Job Board API: https://docs.greenhouse.io/job-board.html
- Lever Postings API: https://github.com/lever/postings-api/blob/master/README.md
- Live calls (2026-09-29):
  - `api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true`
  - `api.ashbyhq.com/posting-api/job-board/n8n`
  - `boards-api.greenhouse.io/v1/boards/vercel/jobs?content=true&pay_transparency=true`
  - `api.lever.co/v0/postings/{palantir,spotify,zoox}?mode=json`

**Other**
- Anthropic models overview: https://platform.claude.com/docs/en/models/overview
- Cloudflare Quick Tunnels: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/
