# Job Scout on n8n: instance-level MCP research

Research date: 2026-09-29. Sources: n8n docs (docs.n8n.io, fetched as `.md` on 2026-09-29), n8n source at tag `n8n@2.41.3` (sparse clone of `packages/cli/src/modules/mcp`, `oauth-server`, `public-api`, `@n8n/config`, `@n8n/api-types`, and the MCP Server Trigger node), n8n release notes and v3.0 breaking-changes page, one merged n8n PR, the MCP specification (revision 2026-07-28), Claude Code docs (code.claude.com), and the Claude Help Center article on custom connectors. I also made read-only, unauthenticated GET calls to the local n8n at `http://localhost:5678` on 2026-09-29. I did not log in, create tokens, or change settings.

Builds on [`job-scout-build.md`](job-scout-build.md). That doc covers Data Tables (section 2.4), editions and licensing (2.1), and the durable scheduler. This doc does not repeat them.

**Labels.** **[Doc]** means n8n or Anthropic docs state it. **[Source]** means I read it in n8n source at `n8n@2.41.3`. **[Observed]** means I saw it in a live response on 2026-09-29. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

---

## 1. Summary and recommendation

- **Instance-level MCP is a built-in MCP server at `https://<host>/mcp-server/http`.** It is off by default. You turn it on under **Settings > Instance-level MCP**. It has no license gate, so it works on Community Edition. The transport is Streamable HTTP, and it runs stateless. Clients authenticate with OAuth or a personal "API key" bearer token.
- **An agent can read Data Tables directly in 2.41.3.** The tool is `get_data_table_rows`, and it takes filters, sort, and pagination. It is in the source, but the docs' tools reference doesn't list it yet. No tool can update or delete rows, so "mark lead X applied" needs a workflow.
- **Workflows must be opted in one by one** ("Available in MCP"). `execute_workflow` can start Webhook, Form, Chat, and Schedule triggers, plus Manual in manual mode. It cannot start an Execute Workflow (sub-workflow) trigger. It returns an execution ID right away, so the agent then calls `get_workflow_execution` to read the result.
- **The main risk is scope.** An API-key token gets every tool: it can create and edit workflows, change Data Tables, and read every table the user can see. An OAuth grant can be narrowed to chosen scopes on the consent screen. `dataTable:read` covers every table in reach, not just the Job Scout ones.
- **Recommendation [Opinion]:**
  - Use instance-level MCP for the demo, connected with **OAuth** and scopes limited to `workflow:read`, `workflow:execute`, `execution:read` and `dataTable:read`.
  - Keep resume text out of any Data Table and out of the node parameters of any MCP-exposed workflow. With that done, reads go straight through `get_data_table_rows`. That is one tool call with a synchronous answer, which looks good on camera.
  - Handle writes ("mark applied", "pass with reason") with one Webhook-triggered **"Job Scout: set lead status"** workflow exposed to MCP. Give it a precise description.
  - Hold the MCP Server Trigger in reserve. Use it if Rahat wants a curated tool list with Job Scout-specific names, or needs tighter isolation than scopes allow (section 2.4).

---

## 2. Findings

### 2.1 What it is, how to enable it, endpoint, transport, auth

**Enable**
- UI: **Settings > Instance-level MCP > Enable MCP access**. This needs the instance owner or an admin [Doc: connect-to-n8n-mcp-server].
- Env vars (self-hosted, from 2.20.0): `N8N_MCP_MANAGED_BY_ENV=true` plus `N8N_MCP_ACCESS_ENABLED=true`. This locks the UI toggle [Doc: manage-settings-using-environment-variables].
- `N8N_DISABLED_MODULES=mcp` removes the endpoints and UI entirely [Doc].
- It is a backend module that loads on `main` instances [Source: `mcp.module.ts`]. Instance-level MCP settings went GA in 2.31. That release "removed the preview label" [Doc: release notes 2.31].
- **Edition:** the endpoint gate is only "is MCP access enabled". `authorize()` lets any signed-in user through while it is on [Source: `mcp-protected-resource.ts`]. The only license check in the module is `feat:folders` for the four folder tools [Source: `mcp-scopes.ts` `FOLDER_FEATURE_TOOLS`]. Folders come with free registration [build doc 2.1]. **[Inference]** So Community Edition with a registered license gets every tool relevant to Job Scout.
- Local check: `GET http://localhost:5678/mcp-server/http` returns `404 {"message":"MCP access is disabled"}` with `X-RateLimit-Limit: 100` [Observed]. So the module is loaded and access is off.

**Endpoint and transport**
- Path: `/mcp-server/http`. The UI shows the full URL under **Connect a client > Server URL** [Doc; Source: `@RootLevelController('/mcp-server')`].
- `N8N_MCP_BASE_URL` sets a different public MCP hostname, from 2.31.0 [Doc: endpoints env vars; Source: `mcp.config.ts`].
- **Streamable HTTP, stateless.**
  - `POST /mcp-server/http` builds a fresh server and transport per request.
  - `GET` returns `405` because the server never offers a server-to-client listen stream.
  - `HEAD` returns `401` with `WWW-Authenticate: Bearer ... resource_metadata=...` for auth discovery.
  - [Source: `mcp.controller.ts`]
- It serves the current MCP revision (**2026-07-28**, whose first request is `server/discover`). Older 2025-era clients use a "stateless legacy fallback" [Source: `mcp.controller.ts` comments; MCP spec versioning]. The spec marks the old HTTP+SSE transport deprecated [MCP spec: deprecated features].
- Rate limit: `N8N_MCP_SERVER_RATE_LIMIT`, default 100 requests per IP per 5 minutes. `0` disables it [Source: `mcp.config.ts`; Doc].

**Auth**
- **OAuth (recommended by n8n).** Discovery and dynamic client registration go through n8n's shared OAuth server (`/mcp-oauth/register`, `/authorize`, `/token`, `/revoke`) [Doc: endpoints env vars].
  - Access tokens last 1 hour. Refresh tokens last 30 days [Source: `oauth-token.service.ts`].
  - From 2.32, the consent screen lets the user pick **All, Read only, or Custom** scopes. "Out-of-scope tools are not listed or callable" [Doc: release notes 2.32; Source: `mcp.service.ts` `registerIfAllowed`].
- **API key.** This is a personal token, generated the first time you open the **API key** tab. The client sends it as `Authorization: Bearer <token>` [Doc].
  - It is a JWT with audience `mcp-server-api`, `scopes: []`, and no `exp` [Source: `mcp-api-key.service.ts`].
  - Scopes are `undefined` for API keys, which "exposes all tools" [Source: `mcp.service.ts`, `mcp-server-middleware.service.ts`].
  - It is separate from the public REST API key (`X-N8N-API-KEY`).
- **Scopes** (`MCP_INSTANCE_SCOPES`): `workflow:read`, `workflow:write`, `workflow:execute`, `execution:read`, `agent:read|write|execute`, `credential:read`, `dataTable:read`, `dataTable:write`, `project:read`, `project:write`, `tag:read`, `communityPackage:install`, `aiPreference:read` [Source: `@n8n/api-types/src/schemas/mcp.schema.ts`].
- User permissions still apply on top of token scopes. For example, Data Table reads check the user's `dataTable:readRow` scope on the project [Source: `data-table-proxy.service.ts`].

### 2.2 Tools exposed (n8n 2.41.3)

**Which tools register.** The scope-to-tool map is in `mcp-scopes.ts` [Source]. Builder tools need `N8N_MCP_BUILDER_ENABLED`, which defaults to `true` [Source: `endpoints.config.ts`]. Agent tools need the Preview `agents` module. The four instance-context tools need PostHog flag `114_instance_activity_context`. Three of them also need the `instance-ai` module [Doc; Source].

| Scope | Tools |
|---|---|
| `workflow:read` | `search_workflows`, `get_workflow_details`, `get_workflow_history`, `get_workflow_version`, `get_workflow_versions_diff`, builder helpers (`search_nodes`, `get_node_types`, `get_workflow_best_practices`, `get_workflow_sdk_reference`, `validate_workflow`, `validate_node_config`), context tools (`get_instance_context`, `get_instance_activity`, `expand_instance_activity`, `get_node_usage`) |
| `workflow:write` | `create_workflow_from_code`, `update_workflow`, `archive_workflow`, `restore_workflow_version`, `publish_workflow`, `unpublish_workflow`, `move_workflows_to_folder` |
| `workflow:execute` | `execute_workflow`, `test_workflow`, `prepare_workflow_pin_data` |
| `execution:read` | `get_workflow_execution`, `search_workflow_executions` |
| `dataTable:read` | `search_data_tables`, `get_data_table_rows` |
| `dataTable:write` | `create_data_table`, `rename_data_table`, `add_data_table_column`, `delete_data_table_column`, `rename_data_table_column`, `add_data_table_rows` |
| `credential:read` | `list_credentials` (never returns secrets), `list_n8n_gateway_services`, `explore_node_resources` |
| `project:*`, `tag:read` | `search_projects`, `search_folders`, `create_folder`, `update_folder`, `list_workflow_tags` |
| others | agent tools (Preview), `install_community_node` (OAuth scope only, never via API key), `get_user_preferences` (flag-gated) |

**The tools Job Scout would use**, with input and output [Doc: mcp-server-tools-reference, checked against Source]:

- `search_workflows(query?, projectId?, tags?, limit≤200, sortBy?, folderId?, includeSubfolders?)`
  - Returns `{data:[{id, name, description, active, triggerCount, availableInMCP, tags, ...}], count}`.
  - It lists **every** workflow the user can see, not only MCP-enabled ones, but only as previews [Doc].
- `get_workflow_details(workflowId, detailLevel?: "full"|"execution")`
  - Returns `{workflow:{..., nodes, connections, settings, description, canExecute}, triggerInfo}`.
  - Credential references are cut down to `{id, name}` [Source: `sanitizeNodeCredentials`].
  - All other node parameters are returned as-is. **[Inference]** That includes sticky-note text, Code node code, and prompts.
  - `detailLevel: "execution"` omits the graph (from 2.35.0).
  - `triggerInfo` is prose that tells the agent how to call each trigger.
- `execute_workflow(workflowId, executionMode: "manual"|"production", triggerNodeName?, inputs?)`
  - `inputs` is a union keyed on `type`: `{type:"webhook", webhookData:{method?, query?, body?, headers?}}`, `{type:"form", formData}`, or `{type:"chat", chatInput}`.
  - Returns `{executionId, status:"started"|"error", error?}` **without waiting** [Doc; Source].
  - Production mode needs a published version and supports Webhook, Form, Chat and Schedule triggers. Manual mode also supports Manual Trigger [Source: `SUPPORTED_PRODUCTION_MCP_TRIGGERS`].
  - Multi-step forms and human-in-the-loop waits aren't supported [Doc].
  - **How inputs reach the workflow:** n8n doesn't make an HTTP call. It starts the run at the trigger node, with the MCP inputs pinned as that node's output (`{headers, query, body}` for Webhook) [Source: `execute-workflow.tool.ts` `getPinDataForTrigger`].
  - **[Inference]** So the Webhook node's own auth isn't checked on MCP runs, and a Respond to Webhook reply never reaches the agent.
- `get_workflow_execution(workflowId, executionId, includeData?, nodeNames?, truncateData?)`
  - Returns metadata, plus full run data when `includeData` is true.
  - `nodeNames` limits the data to named nodes [Doc; Source].
- `search_workflow_executions(workflowId?, status?, startedAfter?, startedBefore?, limit≤200, cursor?)`
  - Returns metadata only.
  - It is limited to MCP-enabled workflows [Source: `search-executions.tool.ts` filters `availableInMCP`].
- `search_data_tables(query?, projectId?, limit≤100)`
  - Returns tables with `id`, `projectId`, and columns (`name`, `type`) [Doc].
- `get_data_table_rows(dataTableId, projectId, filter?, sortBy?, limit≤100, skip?)`
  - `filter` = `{type:"and"|"or", filters:[{columnName, condition, value}]}`.
  - `condition` ∈ `eq, neq, like, ilike, gt, gte, lt, lte, isEmpty, isNotEmpty`.
  - The system columns `id`, `createdAt` and `updatedAt` can be filtered.
  - `sortBy` = `"<column>:asc|desc"`.
  - Returns `{rows, count}`. Dates come back as ISO strings.
  - The tool is annotated `readOnlyHint: true`.
  - [Source: `tools/data-table/get-data-table-rows.tool.ts`; conditions from `data-table-filter.schema.ts`]
  - Added by [PR #35956](https://github.com/n8n-io/n8n/pull/35956), merged 2026-08-14. It is not in the docs' tools reference as of 2026-09-29.
- `add_data_table_rows(dataTableId, projectId, rows[1..1000])` inserts rows only [Doc].

**Which workflows are visible**
- Every workflow needs **Available in MCP**. You can set it from workflow settings, the workflow card menu, **Settings > Instance-level MCP > Workflows exposed**, or in bulk per project or folder (from 2.24) [Doc].
- The server enforces it on details, execute, and execution reads: "Workflow is not available in MCP" [Source: `validateMcpWorkflow`]. Archived workflows are refused.
- Per the docs, only published workflows with a webhook, form, schedule, or chat trigger qualify [Doc]. **[Unverified]** I didn't find a trigger-type check in the toggle endpoint. The check is enforced when `execute_workflow` runs.
- "Auto-expose new workflows" is off by default and "rolling out gradually from 2.36.0" [Doc].
- Exposure is per instance, not per client. Every connected client sees every MCP-enabled workflow [Doc].
- **The workflow description is the agent's routing signal.** `search_workflows` matches on it and returns it. The `execute_workflow` tool text tells the agent to consult the description before running [Doc; Source: tool description string]. Edit it from **Workflows exposed** or the workflow menu (**Edit description**) [Doc].

### 2.3 Data Tables through MCP, and the workflow pattern for writes

- **Reads: direct.** An agent with `dataTable:read` can answer "leads with fit ≥ 80 this week" in one or two calls: `search_data_tables(query:"leads")`, then `get_data_table_rows` with `fit gte 80` and `createdAt gte <Monday ISO>`, sorted `fit:desc` [Source]. Joins such as passes→leads take a second call. The `or` filter type handles several `lead_id eq` matches. There is no `in` operator.
- **Writes: via a workflow.** MCP has no update-row or delete-row tool [Source: tool list]. `add_data_table_rows` could append to `passes`, but it would skip Job Scout's own validation [Inference].
- **Pattern: "Job Scout: set lead status"** [Inference, based on the tool semantics above]:
  - Trigger: a **Webhook** node, POST. It can't be an Execute Workflow Trigger, because MCP can't start that.
  - Nodes: Webhook → validate `body.lead_id` and `body.status` against an allowed list → Data Table **Update** (and a `passes` **Insert** when the status is `passed`) → a final Set node named **`Result`** that returns `{lead_id, old_status, new_status}`.
  - Publish it and turn on **Available in MCP**.
  - Description, for example: "Set a Job Scout lead's status. Webhook POST body: `{lead_id: string, status: 'applied'|'interviewing'|'offer'|'passed', reason_code?: string, note?: string}`. Run with `execute_workflow` in production mode, then read node `Result` via `get_workflow_execution(includeData: true, nodeNames: ['Result'])`."
  - The agent does three calls: `execute_workflow`, then `get_workflow_execution`, and a retry if the status is still `running`.
  - Give the Webhook node header auth anyway. Its public URL stays reachable outside MCP, and MCP runs skip that check.
- **Optional read workflows.** A "Job Scout: explain passes" workflow (Webhook, `company` in the query) could pre-join `passes` and `leads` and summarize. Use this if Rahat doesn't want to grant `dataTable:read` [Inference].

### 2.4 Alternatives: MCP Server Trigger node and the REST API

**MCP Server Trigger node**
- One workflow acts as its own MCP server. It exposes only the tool nodes attached to it, such as the Custom n8n Workflow Tool [Doc: mcptrigger].
- URLs: production `https://<host>/mcp/<path>` and test `/mcp-test/<path>`. The path segments come from `N8N_ENDPOINT_MCP` and `N8N_ENDPOINT_MCP_TEST` [Source: `endpoints.config.ts`; Doc].
- Transport: SSE and Streamable HTTP. Node v1 uses `/sse` and `/messages` sub-paths. v2 serves Streamable HTTP at the path itself, with GET, POST and DELETE [Source: `McpTrigger.node.ts`, versions 1, 1.1, 2, 2.1].
- Auth options: None, Bearer, Header, or **n8n User Auth (OAuth2)** (v2+, from 2.27). There is a "Require Workflow Execute Permission" toggle and an optional **Instructions** field sent to clients (2.36) [Source; Doc: release notes].
- The Data Table node has `usableAsTool: true` [Source: `DataTable.node.ts`]. **[Inference]** So a "Job Scout tools" workflow could attach Data Table tool nodes and Custom Workflow Tool nodes (Execute Workflow Trigger sub-workflows) directly. Tool results come back in the tool call, with no execution polling.
- On claude.ai, custom connectors ask for n8n sign-in even with Authentication = None [Doc].

**Trade-offs [Opinion]**

| | Instance-level MCP | MCP Server Trigger |
|---|---|---|
| Setup | One toggle, one connection | One workflow to build and maintain |
| Tool names the agent sees | Generic (`get_data_table_rows`, `execute_workflow`) | Job Scout-specific (`list_leads`, `mark_applied`) |
| Result of an action | Async: execute, then read the execution | Returned in the tool call |
| Exposure | Scope-level; `dataTable:read` covers all tables | Only the tools you attach |
| Demo story for n8n DevRel | Shows n8n's flagship MCP feature, including "the agent can also build workflows" | Shows the "build your own MCP server in n8n" pattern, which can ship as a template |

For "an agent queries Job Scout", both work. Instance-level demos the product better. The trigger gives the cleaner, safer surface.

**Public REST API (non-MCP)**
- It covers Data Tables fully: `GET/POST /api/v1/data-tables`, `/data-tables/{id}/rows` (GET with a JSON `filter`, POST insert), `/rows/update`, `/rows/upsert`, `/rows/delete`, `/rows/clear`, plus column endpoints [Source: `public-api/v1/openapi.yml`, `handlers/data-tables/spec`].
- Auth uses the `X-N8N-API-KEY` header. Key scopes are Enterprise-only, so a Community Edition key has full access [Doc: n8n-api/authentication].
- The docs also point agents at the **n8n CLI**, which wraps this API [Doc: n8n-api].
- Fine for scripts. It has no tool discovery, so it's no MCP moment [Opinion].

### 2.5 Connecting Claude Code and Claude Desktop; reverse proxy

**Claude Code** (connects from Rahat's machine, so `http://localhost:5678` also works) [Doc: mcp-client-examples; Claude Code MCP docs]:
```bash
# OAuth (recommended): add, then run /mcp in Claude Code and pick the server to sign in
claude mcp add --transport http n8n https://<n8n-host>/mcp-server/http

# API key (full-access token): header auth
claude mcp add --transport http n8n-mcp https://<n8n-host>/mcp-server/http \
  --header "Authorization: Bearer ${N8N_MCP_TOKEN}"
```
- Claude Code expands `${VAR}` in `.mcp.json` `url` and `headers`, so the token can stay out of files [Doc: Claude Code MCP].
- If a configured `Authorization` header is rejected, Claude Code reports a failure. It does not fall back to OAuth [Doc].
- Output over 25,000 tokens is capped (`MAX_MCP_OUTPUT_TOKENS`) [Doc]. **[Inference]** Keep `get_data_table_rows` limits small, and use `nodeNames` and `truncateData` on `get_workflow_execution`.

**Claude Desktop**
- Use **Customize > Connectors > Add custom connector**, paste the Server URL, then approve in n8n [Doc: Claude Help Center]. n8n's page says "Settings > Connectors" [Doc: mcp-client-examples].
- The connection "originates from Anthropic's servers, not from your machine". The server "must be reachable over the public internet" [Doc: Claude Help Center].
- So Desktop needs the Coolify URL, not localhost.
- n8n documents an API-key alternative through a local `npx supergateway --streamableHttp ... --header` stdio bridge [Doc: mcp-client-examples].

**Reverse proxy (Coolify, public HTTPS)**
- Forward the `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` headers. Otherwise clients "may fail to connect or fall back to an older protocol version" [Doc].
- Set `N8N_PROXY_HOPS=1` and correct `X-Forwarded-*` headers [Doc: reverse-proxy webhook URLs].
- **[Inference]** This also makes the per-IP rate limit see real client IPs instead of the proxy's IP.
- The OAuth resource URL comes from the instance base URL, or from `N8N_MCP_BASE_URL`. A mismatch with the public host would break the token audience check [Source: `mcp.config.ts`, `mcp-server-middleware.service.ts`].
- Streaming and timeouts:
  - The instance endpoint is request/response with no GET stream [Source].
  - `execute_workflow` returns at once. `test_workflow` is synchronous for up to 5 minutes by default [Doc].
  - **[Inference]** Default proxy timeouts are enough for instance MCP.
  - The nginx advice (`proxy_buffering off`, `gzip off`, `Connection ''`) is written for the MCP Server Trigger's `/mcp/` path [Doc: mcptrigger]. Apply it there if that node is used.
- **[Unverified]** How Coolify's default proxy (Traefik) handles these headers and buffering. I checked no Coolify primary source for this.

### 2.6 Security

- **API key = every tool.** A leaked key can do all of the following [Source: `getAllowedToolNames`]:
  - read, create, edit, archive, publish and unpublish workflows
  - run exposed workflows
  - read execution data
  - list credential names
  - create tables, delete columns and insert rows in any Data Table the user can reach
- The key has no expiry. **Rotating** it in the **API key** tab revokes the previous key [Doc; Source]. API-key clients don't appear in **Connected clients** [Doc].
- **OAuth tokens are narrower and revocable.** Scopes are chosen at consent. Access tokens last 1 hour and refresh tokens 30 days. You can revoke per client under **Connected clients** [Doc; Source].
- Set **Allowed callback URLs** to "Only trusted URLs". The default allows any [Doc].
- **What exposure reveals:**
  - For any MCP-enabled workflow, `get_workflow_details` returns every node parameter, with credentials reduced to id and name [Source]. **[Inference]** Sticky notes and any resume text inlined in a Set node or prompt go to the agent, and on to the model provider.
  - `get_workflow_execution(includeData)` returns full run data [Source]. That includes any rows or LLM inputs the run touched.
  - `search_workflows` shows names and descriptions of all workflows [Doc].
- **Limiting exposure to Job Scout** [Inference]:
  - Enable MCP only on the status-update workflow, and any read workflows.
  - Don't expose the Scan/Score workflow if its prompt or nodes hold resume text.
  - Grant only the scopes in section 1.
  - Community Edition has no projects [build doc 2.1], so everything sits in the personal project, and `dataTable:read` reaches every table there.
  - Keep resume text out of Data Tables. Options: in a credential, or in a workflow that stays unexposed. Or skip `dataTable:read` and use read workflows.
- An MCP-run Webhook workflow skips the Webhook node's own auth [Source, see 2.2]. Validate inputs inside the workflow.
- Turning MCP off disconnects and revokes every client [Doc].

### 2.7 n8n 3.0 and recent MCP changes

- **3.0 (October 2026):** the breaking-changes page lists **no MCP changes** [Doc: v30-breaking-changes]. Items that matter here:
  - Docker-only installs.
  - The "Any workflow" sub-workflow caller policy is deprecated ahead of removal in v3 [Doc: release notes 2.37].
  - Chat Hub is off by default.
- **[Inference]** `docker-compose.yml` pins `n8nio/n8n:latest`, so a pull after 3.0 ships moves the local instance across the major version.
- **Recent MCP changes** [Doc: release notes]:
  - 2.22.5-exp: workflow-card toggle (A/B test). Project/folder bulk toggle from 2.24 [Doc: connect page].
  - 2.27: MCP Server Trigger gains n8n OAuth2.
  - 2.31: instance MCP GA; `N8N_MCP_BASE_URL`.
  - 2.32: scope picker on OAuth consent.
  - 2.33: new settings layout, **Connect a client** dialog, allowed callback URLs.
  - 2.35: `detailLevel`; `scopes` and `canExecute` removed from search results.
  - 2.36: `triggerNodeName`, CORS for MCP headers, trigger **Instructions**, auto-expose rollout.
  - 2.37: `folderId` search.
  - Mid-August (PR #35956): `get_data_table_rows`.
- The docs already mention 2.42.0 behavior, for example credential descriptions [Doc: tools reference]. Check the version notes when reading them against 2.41.3.

---

## 3. Example agent queries and which workflow answers them

| Agent query | Tool path (instance-level MCP) | Workflow needed? |
|---|---|---|
| "What new leads scored above 80 this week?" | `search_data_tables("leads")` → `get_data_table_rows(filter: fit gte 80 AND createdAt gte <Mon>, sortBy "fit:desc")` | No (needs `dataTable:read`) |
| "Why did I pass on Ramp roles?" | `get_data_table_rows(leads, company ilike "%ramp%")` → `get_data_table_rows(passes, or: lead_id eq …)` | No. Optional "explain passes" workflow |
| "Mark lead X applied" | `get_workflow_details(set-status, "execution")` → `execute_workflow(production, webhook body {lead_id, status:"applied"})` → `get_workflow_execution(includeData, nodeNames:["Result"])` | Yes: "Job Scout: set lead status" |
| "Did last night's scan run? How many failed?" | `search_workflow_executions(workflowId: scan, startedAfter: …)` | Scan workflow must be MCP-enabled |
| "Run a scan now" | `execute_workflow(scan, production)` (Schedule trigger, no inputs) | Scan workflow MCP-enabled |

---

## 4. Open questions for Rahat

1. **Instance-level MCP or MCP Server Trigger for the demo, or both?** Instance-level shows off n8n's feature. The trigger gives named tools and synchronous answers.
2. **Where does resume text live?** This decides whether an agent can safely get `dataTable:read`.
3. **Which scopes should the demo grant?** Read-only plus execute, or also `workflow:write`, to show "the agent edits Job Scout"?
4. **Should the Scan/Score workflow be MCP-enabled?** That allows "run a scan now" and execution checks, but its node parameters become readable.
5. **Which clients go on camera?** Claude Code (works against localhost) or Claude Desktop (needs the public Coolify URL)?
6. **Which statuses can an agent set?** For example, should an agent be allowed to mark `passed` without the pass-reason form?

---

## 5. Sources

**n8n docs** (fetched 2026-09-29)
- Connect to n8n MCP server: https://docs.n8n.io/connect/connect-to-n8n-mcp-server.md
- MCP client connection examples: https://docs.n8n.io/connect/connect-to-n8n-mcp-server/mcp-client-examples.md
- MCP server tools reference: https://docs.n8n.io/connect/connect-to-n8n-mcp-server/mcp-server-tools-reference.md
- Use n8n MCP server: https://docs.n8n.io/build/ways-of-building-workflows/connect-to-n8n-mcp-server.md
- MCP Server Trigger: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger.md
- Manage settings using environment variables: https://docs.n8n.io/deploy/host-n8n/configure-n8n/manage-settings-using-environment-variables.md
- Endpoint env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md
- Reverse proxy webhook URLs: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/configure-webhook-urls-with-reverse-proxy.md
- n8n API and authentication: https://docs.n8n.io/connect/n8n-api.md, https://docs.n8n.io/connect/n8n-api/authentication.md
- Release notes: https://docs.n8n.io/changelog/release-notes.md
- v3.0 breaking changes: https://docs.n8n.io/changelog/v30-breaking-changes.md
- Full docs export and sitemap: https://docs.n8n.io/llms-full.txt, https://docs.n8n.io/sitemap.md

**n8n source at `n8n@2.41.3`** (base: https://github.com/n8n-io/n8n/blob/n8n@2.41.3/)
- `packages/cli/src/modules/mcp/`: `mcp.module.ts`, `mcp.controller.ts`, `mcp.config.ts`, `mcp-scopes.ts`, `mcp.service.ts`, `mcp-server-middleware.service.ts`, `mcp-api-key.service.ts`, `mcp-protected-resource.ts`, `mcp.constants.ts`, `mcp.settings.controller.ts`
- `packages/cli/src/modules/mcp/tools/`: `execute-workflow.tool.ts`, `get-workflow-details.tool.ts`, `get-execution.tool.ts`, `search-executions.tool.ts`, `workflow-validation.utils.ts`, `schemas.ts`, `webhook-utils.ts`, `data-table/get-data-table-rows.tool.ts`
- `packages/cli/src/modules/oauth-server/`: `oauth-token.service.ts`, `oauth-consent.service.ts`
- `packages/cli/src/modules/data-table/data-table-proxy.service.ts`
- `packages/cli/src/public-api/v1/openapi.yml` and `handlers/data-tables/`
- `packages/@n8n/config/src/configs/endpoints.config.ts`
- `packages/@n8n/api-types/src/schemas/mcp.schema.ts`, `data-table-filter.schema.ts`
- `packages/@n8n/nodes-langchain/nodes/mcp/McpTrigger/McpTrigger.node.ts`
- `packages/nodes-base/nodes/DataTable/DataTable.node.ts`
- PR #35956 "Add MCP tool to read data table rows": https://github.com/n8n-io/n8n/pull/35956

**MCP specification**
- Versioning (current revision 2026-07-28): https://modelcontextprotocol.io/specification/versioning
- Streamable HTTP transport: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- Deprecated features: https://modelcontextprotocol.io/specification/2026-07-28/deprecated

**Anthropic**
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Custom connectors using remote MCP: https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp

**Observed**
- `GET http://localhost:5678/mcp-server/http` → `404 {"message":"MCP access is disabled"}` (2026-09-29)
