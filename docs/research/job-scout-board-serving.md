# Job Scout board: serve from n8n webhooks or a static site?

Research date: 2026-09-29. Sources: n8n docs (fetched as `.md` on 2026-09-29), n8n source at tag `n8n@2.41.3` (commit `7f7a8ac`), Coolify docs source (`coollabsio/coolify-docs`, `main` on 2026-09-29), read-only requests to the local n8n 2.41.3 at `http://localhost:5678`, and the Hermes mockups in `~/dev/hermes-job-board/`.

Related: [job-scout-build.md](job-scout-build.md) covers human-in-the-loop (2.3), Data Tables (2.4), `N8N_WEBHOOK_URL` and reverse proxies (2.3), and general risks (4). This doc doesn't repeat them.

**Labels.** **[Doc]** a primary doc says it. **[Source]** I read it in n8n source at `n8n@2.41.3`. **[Observed]** I saw it in a live response or a local file on 2026-09-29. **[Inference]** my reasoning, not tested. **[Opinion]** judgment only. **[Unverified]** no primary source found; test it.

---

## Summary and recommendation

- **Recommendation: serve the board from n8n webhooks, and design it for n8n's default HTML sandbox.** [Opinion]
  - One `GET` webhook returns the board HTML. It uses Basic Auth, so the browser shows its login prompt.
  - Before responding, that workflow signs a short-lived JWT (JWT node) and puts it in the HTML.
  - The page's JavaScript calls the JSON API webhooks with `Authorization: Bearer <jwt>`. Those webhooks use JWT Auth with the same `jwtAuth` credential.
  - The API webhooks read and write Data Tables.
  - The whole board then ships inside the n8n template, and the demo shows that the UI itself is n8n workflows.
- **The key risk is confirmed.** n8n adds `Content-Security-Policy: sandbox ...` to every webhook response, and the policy leaves out `allow-same-origin` [Source]. In practice:
  - The page runs in an opaque origin, so `localStorage` and cookies fail [Doc] [Inference].
  - Browser-cached Basic Auth credentials aren't sent on `fetch` calls [Doc] [Inference].
  - Scripts, forms, modals and popups still work [Source].
  - An instance-wide env var turns the sandbox off: `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true`. Don't use it (section 3).
- **Don't call n8n's public REST API from a browser.** It has Data Table endpoints [Doc]. But it sends no CORS headers: a local preflight got `405` [Observed]. And the API key is a full-access credential on Community edition (section 7).
- **Fallback:** if a spike shows the sandbox breaks something the board needs, use a static site on Coolify.
  - Put it on its own subdomain, not a subpath of the n8n host.
  - Auth: a login webhook returns a JWT, and the page keeps it in `localStorage` (section 8).
- **Before building:** do a one-hour spike on the published local instance to check the [Unverified] items in section 10.

---

## 1. What the board needs [Observed]

- **Columns:** New, Applied, Interviewing, Offer, Passed.
  - Cards show fit score, verification state and remote basis.
  - Dragging a card to Passed opens the modal "Why did this one not work?", with reason chips and an optional note.
  - Source: `Main.dc.html`, `feedback-loop-spec.md` §1.
- **Feedback to Hermes panel:** proposed rules, each with "Apply to brief", "Dismiss" and "Undo" (`feedback-loop-spec.md` §2).
- **Other controls:** a detail drawer with verification evidence, and "Run scan" and "Re-verify all" buttons (`Main.dc.html`).
- **Size and markup:** `Main.dc.html` is 56 KB. It uses `{{...}}` template markup and `support.js`. Either way, it needs a rewrite to plain JS against a real API.
- **API surface this implies [Inference]:**
  - `GET` leads
  - `POST` status change
  - `POST` pass with reason
  - `GET` feedback proposals
  - `POST` rule decision
  - `POST` run scan

## 2. Webhook node (v2.1)

- **Methods:** DELETE, GET, HEAD, PATCH, POST, PUT [Doc] [Source].
  - "Allow Multiple HTTP Methods" (node Settings) gives one output per method [Doc].
  - Only one webhook can exist per path and method [Doc]. A second workflow can't take a path another workflow already holds [Source: `webhook.service.ts`].
- **Path params:** `leads/:id` style is supported [Doc]. But n8n **prefixes dynamic paths with the node's webhookId UUID**: the real URL is `/webhook/<uuid>/job-scout/leads/:id` [Source: `node-helpers.ts` `getNodeWebhookPath`, `webhook.service.ts` `findDynamicWebhook`].
  - [Inference] Use static paths and put the lead ID in the JSON body or query string. For example `POST /webhook/job-scout/api` with `{action, lead_id, ...}`, then a Switch node.
- **Respond modes:**
  - Immediately
  - When Last Node Finishes
  - Using 'Respond to Webhook' Node
  - Streaming, which needs a streaming-capable node such as the AI Agent [Doc] [Source].
  - For the board, use "Using 'Respond to Webhook' Node" everywhere [Opinion].
- **Payload:** max 16 MiB by default, set by `N8N_PAYLOAD_SIZE_MAX`. Multipart file uploads are capped at 200 MiB per file by `N8N_FORMDATA_FILE_SIZE_MAX` [Doc] [Source: `endpoints.config.ts`].
- **Request options:**
  - **Raw Body** puts the body in `binary.data`.
  - **Binary File** streams the body to a binary property.
  - **Ignore Bots** returns 403 to link previewers.
  - **IP(s) Allowlist** accepts CIDR ranges and returns 403. Behind a proxy it needs `N8N_PROXY_HOPS`.
  - **Only Run If**: requests that don't match get a 200 and create no execution.
  - Sources: [Doc] [Source: `Webhook.node.ts`].
- **Response Headers:** can set any header except `content-security-policy`, `strict-transport-security` and `clear-site-data`. n8n drops those and logs a warning [Source: `webhook-response-headers.ts` `PROTECTED_HEADERS`]. So a workflow can't relax the sandbox for itself.

## 3. Respond to Webhook and the HTML sandbox (key risk)

- **Respond With options:**
  - All Incoming Items
  - Binary File
  - First Incoming Item
  - JSON
  - JWT Token
  - No Data
  - Redirect (default 307)
  - Text ("sends HTML by default (`Content-Type: text/html`)")
  - Sources: [Doc] [Source: `RespondToWebhook.node.ts` v1.5].
- **Response options:** Response Code and Response Headers. The node runs once, on the first item, so use Aggregate before it to return a list [Doc].
- **What n8n does to every webhook response** [Source: `webhook-request-handler.ts` `setResponseHeaders`, `webhook-helpers.ts`, `core/src/html-sandbox.ts`]:
  - It sets `Content-Security-Policy: sandbox allow-downloads allow-forms allow-modals allow-orientation-lock allow-pointer-lock allow-popups allow-popups-to-escape-sandbox allow-presentation allow-scripts allow-top-navigation-by-user-activation allow-top-navigation-to-custom-protocols`.
  - It sets this on static, streamed and binary responses alike, whatever the content type.
  - The instance-wide CSP is deliberately not applied to webhook routes [Source: `server.ts` comment].
- **Doc vs source:** the docs say HTML is "wrapped in `<iframe>` tags" (since 1.103.0) [Doc]. At 2.41.3 the source says: "The sandboxing mechanism uses CSP headers now, but the name is kept for backwards compatibility" [Source: `security.config.ts`]. The effects are the same kind.
- **Switches:**
  - `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX`, default `false`, covers Webhook responses.
  - `N8N_INSECURE_DISABLE_FORM_HTML_SANDBOX`, default `false`, covers Form Trigger and Send-and-Wait pages.
  - Both are instance-wide. There is no per-workflow switch [Source].
  - n8n's own warning: turning it off "leaves the instance vulnerable to attacks where a malicious user can build a workflow that makes requests using other users' credentials. The correct way to prevent this is to configure forms to be served from a different (sub)domain" [Source: `security.config.ts`].
- **What this means for a page served by a webhook** (sandbox on):

  | Feature | Works? | Basis |
  |---|---|---|
  | Inline and CDN `<script>` | Yes (`allow-scripts`; the CSP has no `script-src`) | [Source] [Inference] |
  | `fetch` to n8n webhooks | Yes, as a CORS request with `Origin: null`. n8n echoes the origin when Allowed Origins is `*` | [Source] [Inference] |
  | `localStorage`, `sessionStorage`, `document.cookie` | No, because the origin is opaque | [Doc] "local storage will fail" [Inference] |
  | Basic Auth cached by the browser, on `fetch` | No | [Doc] "Authentication headers aren't available" |
  | An explicit `Authorization` header set by JS | Yes. n8n answers OPTIONS with 204 before auth and echoes the requested headers | [Source] |
  | `<form>` POST | Yes (`allow-forms`) | [Source] |
  | `alert`/`confirm`, `target=_blank` links | Yes (`allow-modals`, `allow-popups-to-escape-sandbox`) | [Source] |
  | Relative URLs | Docs say no; that may be left over from the iframe design | [Doc] [Unverified] |
  | HTML5 drag and drop | Probably yes | [Unverified] |

- **How n8n works around its own sandbox:** Form Trigger's n8n User Auth reads the `n8n-auth` cookie on the top-level GET. It then embeds an `x-auth-token` for later POSTs, "from the sandboxed form page that can't send cookies" [Source: `Form/utils/utils.ts`]. The docs give the same advice: "embedding a short-lived access token within the HTML" [Doc]. The recommended board auth copies this pattern.
- **Gotcha: `{{ }}` in the HTML [Inference].** To inject the JWT, the Respond node's body must be an expression, and n8n evaluates every `{{ ... }}` inside it. Two ways around it:
  - Keep the board HTML in a fixed (non-expression) field and splice the token in with a Code node.
  - Or avoid `{{` in the board's JS.

## 4. Auth options

- **Webhook node:**
  - Basic Auth, Header Auth, JWT Auth and None [Doc].
  - The source also has "n8n User Auth (OAuth2)", value `n8nOAuth2` [Source: `Webhook/description.ts`].
- **Basic Auth:** on failure, n8n returns 401 with `WWW-Authenticate: Basic realm="Webhook"`, so a top-level page load gets the browser's native prompt [Source: `Webhook.node.ts`]. It suits the HTML page. It doesn't suit sandboxed `fetch` calls (section 3).
- **Header Auth:** needs JS to hold the secret. That works on a static site. On a webhook page it means baking a long-lived secret into the HTML [Inference].
- **JWT Auth:**
  - Reads `Authorization: <scheme> <token>` and runs `jwt.verify` with the credential's secret or public key and algorithm [Source: `Webhook/utils.ts`].
  - The JWT node signs tokens with the same `jwtAuth` credential type and has an "Expires In" claim, default 3600 s [Source: `Jwt.node.ts`].
  - Respond to Webhook can also return `{token}` directly [Source].
  - [Inference] `jsonwebtoken` rejects expired tokens by default.
- **n8n session auth on a Webhook: no.** The `n8nOAuth2` mode wants an OAuth2 bearer token from n8n's OAuth server (built for MCP clients, with dynamic client registration), not the editor's session cookie [Source: `workflow/src/n8n-oauth2-auth.ts`, `oauth.controller.ts`].
  - The Webhook docs page doesn't list it [Doc].
  - Release notes say the related "Require Workflow Execute Permission" toggle "is only visible behind the `N8N_ENV_FEAT_WEBHOOK_PRIVATE_CREDENTIALS` environment flag" [Doc: release notes].
  - A browser page would need a full OAuth PKCE client. Not worth it here [Opinion].
- **Form Trigger's n8n User Auth** does use the session: "Unauthenticated visitors loading the form are redirected to the n8n sign-in page" [Doc]. But Form pages can't carry the board (section 9).
- **IP allowlist:** not useful for a phone on mobile data [Inference].

## 5. CORS

- **Headers are only added when the request has an `Origin` header** [Source: `webhook-request-handler.ts`].
  - `Access-Control-Allow-Methods` lists the registered methods.
  - `Access-Control-Allow-Origin` echoes the origin, or picks from the node's "Allowed Origins (CORS)" list.
  - OPTIONS gets `204`, `Access-Control-Max-Age: 300`, and the requested headers echoed back. It never reaches the workflow and runs no auth.
- **No `Access-Control-Allow-Credentials` header is ever set on production webhooks.** The permissive dev CORS middleware only runs in development [Source: `abstract-server.ts`, `middlewares/cors.ts`].
  - [Inference] A cross-origin page can't use cookies or browser-cached Basic Auth, because `credentials: 'include'` fails.
  - An explicit `Authorization` header set by JS still works.
- **Allowed Origins can fail open.** The option lookup matches `parameters.path === path` and `parameters.httpMethod === method` [Source: `live-webhooks.ts` `findAccessControlOptions`]. [Inference] In these cases no options are found and n8n echoes any origin:
  - dynamic paths (the stored path lacks the UUID prefix)
  - multiple-method nodes (`httpMethod` is an array)
  - paths entered with a leading `/`
- **CORS isn't the security boundary here; auth is.** [Opinion]
- **Sandboxed page:** it sends `Origin: null`. With a specific Allowed Origins list, n8n answers with the list's first entry and the browser blocks the call. Leave Allowed Origins at `*` for the n8n-served option [Source] [Inference].

## 6. URLs, publishing, and execution cost

- **Test vs production URLs:**
  - The test URL `/webhook-test/...` listens for 120 s. It deregisters after one call [Doc] [Source: `test-webhooks.ts`].
  - So a page that makes several calls must be built against production URLs.
  - Production URLs work only while the workflow is published [Doc].
  - [Inference] Each change to the page means editing, publishing, then reloading.
- **Host and proxy settings:** see build research 2.3 (`N8N_WEBHOOK_URL`, `N8N_PROXY_HOPS`). The path prefix `webhook` can be changed with `N8N_ENDPOINT_WEBHOOK` [Source].
- **Every page load and every API call is one execution.**
  - Defaults: `EXECUTIONS_DATA_SAVE_ON_SUCCESS=all`, `EXECUTIONS_DATA_SAVE_ON_ERROR=all`, pruning on, max age 336 h (14 days), max count 10,000 [Source: `executions.config.ts`] [Doc].
  - Per workflow, "Save successful production executions" overrides the default [Doc].
  - [Inference] Set it to "Do not save" on the board workflows, for three reasons:
    - Each `GET leads` would otherwise store the whole leads list.
    - The embedded JWT would land in saved execution data.
    - Board traffic would count toward the 10,000 cap and push scan runs out of history sooner.
  - Keep failed executions for debugging.
- **n8n Cloud:** executions count against plan limits (see build research 2.1). That matters for template users on Cloud, not for Rahat's self-hosted instance [Inference].
- **Latency:** there's no primary number for a Webhook → Data Table Get → Respond round trip [Unverified]. Measure it in the spike.

## 7. Data Tables behind the API, and the public REST API

- **Data Table node row operations:** Get (conditions, Return All or Limit, Order By), Insert, Update (by conditions), Upsert, Delete (with Dry Run), If Row Exists, and If Row Does Not Exist [Doc] [Source: `DataTable/actions/row/`].
  - Conditions: `eq`, `neq`, `gt`/`gte`/`lt`/`lte`, `isEmpty`, `isNotEmpty`, `isTrue`/`isFalse`, and `like`/`ilike` [Source: `DataTable/common/methods.ts`].
- **Enough for the board [Inference]:**
  - `GET leads`: Get → Aggregate → Respond JSON.
  - `status`: Update `leads` where `lead_id` eq body value.
  - `pass`: Insert into `passes`, then Update `leads.status`.
  - `rule decision`: Upsert `rules`.
  - "Run scan": Execute Workflow with "wait" off, then respond immediately.
- **Public REST API:**
  - Endpoints under `/api/v1/data-tables/{id}/rows`: GET with filter, sort and pagination (limit max 250); POST insert; PATCH `/update`; POST `/upsert`; DELETE `/delete`. Auth is the `X-N8N-API-KEY` header [Doc].
  - Key scopes such as `dataTableRow:read` exist on Enterprise only [Doc].
  - The API isn't available during the Cloud free trial [Doc].
- **The public API can't be called cross-origin from a browser.**
  - The only CORS header it sets is on `openapi.yml` [Source: `public-api/index.ts`].
  - A local preflight `OPTIONS /api/v1/data-tables` returned `405 {"message":"OPTIONS method not allowed"}` [Observed].
- **Putting an n8n API key in a browser page is a bad idea.**
  - On Community edition the key can't be scoped, so it can do everything the owner's account can through the API: read, change and delete workflows and executions, read and wipe Data Tables, and create and publish new workflows.
  - Anyone who opens devtools, views source, or sees it in a screen recording has it.
  - A webhook API only exposes the operations you built, and the JWT in the page expires.
  - Basis: [Doc] for scopes and endpoints, [Inference] for the impact.

## 8. Static site on Coolify (the alternative)

- **Deploy options** [Doc: Coolify]:
  - The **Static** build pack serves committed files with Nginx. Set Base Directory (e.g. `/dist`). Nginx config can be edited under Configuration > General, and needs a redeploy.
  - For a build step, use **Nixpacks** or Railpack with "Is it a static site?" and a Publish Directory, or a **Dockerfile**.
  - Source: a public repo, a deploy key, or a Git App.
- **Domain and HTTPS:** put `https://board.example.com` in Domains. Traefik or Caddy then gets and renews the certificate. DNS must point at the server, and ports 80 and 443 must reach the proxy [Doc: Coolify].
- **Subpath:** `https://n8n.example.com/board` is supported. The more specific path wins, and the prefix is stripped by default [Doc: Coolify].
- **Basic auth:** Coolify can add Traefik basic auth to an app [Doc: Coolify].
- **Subpath vs subdomain [Inference]:**
  - **Subpath (same origin as n8n):**
    - No CORS, and the browser sends cached Basic Auth on same-origin `fetch`.
    - But the board then runs on the editor's origin. It renders third-party job text and LLM output, so any XSS bug could call n8n's `/rest` API with the `n8n-auth` session cookie.
    - That is the attack n8n's sandbox exists to block (section 3).
  - **Subdomain:**
    - Cross-origin. n8n never sends `Allow-Credentials`, so JS must send an explicit header.
    - `localStorage` works, so a login webhook can check a password and return a JWT (Respond to Webhook → JWT Token) for the page to store.
    - The `n8n-auth` cookie has no `Domain` attribute (host-only), so the board subdomain never receives it [Source: `auth.service.ts`].

## 9. n8n Form pages

- **Custom HTML field:** it "doesn't support `<script>`, `<style>`, or `<input>` elements" [Doc: Form].
- **Custom Form Styling:** overrides the form's CSS only [Doc].
- **Form Ending page with "Show Text":** allows scripts, but only shows after a submission [Doc], and gets the same sandbox CSP [Source: `applyFormSandboxCSP`].
- **Verdict:** Forms suit the pass-reason link in the Telegram digest (build research 2.3), not a drag-and-drop board [Opinion].

## 10. Comparison and spike checklist

| | A. n8n webhook page (sandbox on) | B. n8n webhook page, sandbox off | C. Coolify static, subdomain | D. Coolify static, n8n subpath |
|---|---|---|---|---|
| Setup | Workflows only | Workflows plus an instance env var | Repo, Coolify app, DNS | Repo, Coolify app, path route |
| Auth | Basic prompt for the page, then a short-lived JWT in the HTML for the API | Basic for everything (cached, same origin) | Login webhook returns a JWT kept in `localStorage` | Basic, same origin |
| CORS | `Origin: null`; keep `*` | None | Allowed Origins set to the board; explicit header | None |
| Browser storage | None; keep state in memory or the URL hash | Yes | Yes | Yes |
| Security | n8n's default posture | Weakens every webhook page on the instance | Good | Board XSS reaches the n8n session |
| Ships in the n8n template | Yes, HTML inline in Respond | Yes, but importers must set an env var (Cloud users can't [Inference]) | No | No |
| Demo value | High: "the UI is a workflow" [Opinion] | Same, with a caveat | Lower | Lower |
| Maintenance | HTML edited in the n8n editor and published; can be versioned as exported JSON | Same | Normal git and deploy | Normal git and deploy |

**Spike checklist before building option A [Unverified]:**
- relative URLs
- drag and drop
- the Basic prompt on the phone
- the JWT fetch, with the preflight
- whether a JWT 401 carrying `WWW-Authenticate: Basic` triggers a prompt
- round-trip latency with a 200-lead table
- whether the template importer keeps webhook paths

---

## Open questions for Rahat

1. **Hostnames:** which domain or subdomain will n8n use on Coolify? Do you want the board under the same host (option A) or on a separate board subdomain?
2. **Demo framing:** should the video show "the board is served by n8n itself" (option A), or treat the board as a separate front end?
3. **Template scope:** should the published template include the board workflow, or only the scan, pass and learn workflows?
4. **Login:** is one shared Basic Auth username and password acceptable for a single-user board, or do you want per-device tokens?
5. **Rewrite scope:** should the board be a from-scratch plain-JS rewrite of the Hermes mockup, or do you want to keep a framework (which pushes toward option C)?

---

## Sources

**n8n docs**
- Webhook: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook.md
- Webhook common issues: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/common-issues.md
- Webhook workflow development: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/workflow-development.md
- Respond to Webhook: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook.md
- Form: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.form.md
- Form Trigger: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.formtrigger.md
- Data Table node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable.md
- Data Table row operations: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable/rows.md
- Public API, Data Table: https://docs.n8n.io/connect/n8n-api/data-table.md
- Public API authentication and scopes: https://docs.n8n.io/connect/n8n-api/authentication.md
- Workflow settings: https://docs.n8n.io/build/manage-workflows/configure-workflow-settings.md
- Manage execution data: https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/manage-execution-data.md
- Release notes: https://docs.n8n.io/changelog/release-notes.md
- Full docs export: https://docs.n8n.io/llms-full.txt

**n8n source at `n8n@2.41.3`** (base: https://github.com/n8n-io/n8n/blob/n8n@2.41.3/)
- `packages/cli/src/webhooks/webhook-request-handler.ts` (CORS, OPTIONS, CSP on responses)
- `packages/cli/src/webhooks/webhook-response-headers.ts` (protected headers, `applySandboxCSP`)
- `packages/cli/src/webhooks/webhook-helpers.ts` (Respond node binary and buffer paths)
- `packages/cli/src/webhooks/live-webhooks.ts` (`findAccessControlOptions`)
- `packages/cli/src/webhooks/webhook.service.ts` (dynamic paths, path conflicts)
- `packages/cli/src/webhooks/test-webhooks.ts`, `packages/cli/src/constants.ts` (test webhook lifetime)
- `packages/cli/src/server.ts`, `packages/cli/src/abstract-server.ts`, `packages/cli/src/middlewares/cors.ts`
- `packages/cli/src/public-api/index.ts`
- `packages/cli/src/auth/auth.service.ts` (auth cookie attributes)
- `packages/cli/src/modules/oauth-server/oauth.controller.ts`
- `packages/core/src/html-sandbox.ts`
- `packages/@n8n/config/src/configs/security.config.ts`, `endpoints.config.ts`, `executions.config.ts`, `data-table.config.ts`
- `packages/workflow/src/node-helpers.ts`, `packages/workflow/src/n8n-oauth2-auth.ts`
- `packages/nodes-base/nodes/Webhook/Webhook.node.ts`, `description.ts`, `utils.ts`
- `packages/nodes-base/nodes/RespondToWebhook/RespondToWebhook.node.ts`
- `packages/nodes-base/nodes/Jwt/Jwt.node.ts`
- `packages/nodes-base/nodes/DataTable/actions/row/`, `common/methods.ts`
- `packages/nodes-base/nodes/Form/utils/utils.ts`

**Coolify docs** (source: https://github.com/coollabsio/coolify-docs, `content/docs/`)
- Static build pack: https://coolify.io/docs/applications/builds/static
- Deploy with Nixpacks: https://coolify.io/docs/applications/builds/nixpacks/deploy
- Domains (HTTPS, paths, prefix stripping): https://coolify.io/docs/core/networking/domains
- Traefik basic auth: https://coolify.io/docs/core/networking/proxy/traefik/basic-auth

**Local observations (2026-09-29)**
- `curl -X OPTIONS http://localhost:5678/api/v1/data-tables` with an `Origin` header returned `405`.
- `curl -X OPTIONS http://localhost:5678/webhook/does-not-exist` returned `500` with `Access-Control-Allow-Methods: OPTIONS`.
- `~/dev/hermes-job-board/Main.dc.html`, `feedback-loop-spec.md`, `seed-data.json`, `canvas.json`.
