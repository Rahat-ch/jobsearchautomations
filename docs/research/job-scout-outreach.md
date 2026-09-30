# Job Scout: finding people to contact

Research date: 2026-09-29. Sources: LinkedIn User Agreement (effective November 3, 2025), Professional Community Policies and the "Prohibited software and extensions" help page on linkedin.com; LinkedIn API docs on learn.microsoft.com; n8n docs fetched as `.md` (plus `llms-full.txt`); n8n source at tag `n8n@2.41.3`; n8n's verified community node registry (`api.n8n.io/api/community-nodes`, the URL the 2.41.3 editor queries); the n8n Creator hub and Template submission guidelines (Notion); n8n's Customer Acceptable Use Policy; Anthropic's web search tool docs; Brave, Google, Microsoft, Tavily, Exa, Hunter, Apollo and GitHub docs and pricing pages. I also made unauthenticated GET calls to the Ashby (n8n), Greenhouse (Instacart), Lever (Spotify) and GitHub public APIs. No account, credential or workflow was created, and nothing was logged in to.

**Labels.** **[Doc]** means a primary doc states it. **[Source]** means I read it in n8n's source at `n8n@2.41.3`. **[Observed]** means I saw it live on 2026-09-29. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

**Scope (from Rahat, 2026-09-29).** Job Scout never sends DMs or messages to anyone. It suggests who to contact and why, and Rahat reaches out by hand. "Pull up the application" means the apply link plus key facts (pay, location, why it fits). Draft message text is out of scope for the proof of concept. X is covered in a separate doc.

---

## 1. Summary and recommendation

- **LinkedIn automation is out.** User Agreement 8.2 bans software, scripts, bots, crawlers and "browser plugins and add-ons" that scrape or copy the Services, and bots that "send or redirect messages" [Doc]. LinkedIn's help page says members using such tools "risk having their accounts restricted or shut down" [Doc]. A browser agent on Rahat's own logged-in account puts the account they job-hunt with at risk.
- **LinkedIn's official API can't do this.** Open products give only the signed-in member's own name, headline, photo and email, plus posting [Doc]. Other members' profiles and people search need partner programs [Doc]. n8n's LinkedIn node has one operation: Post → Create [Source].
- **Recommended: Claude with the web search server tool, called from n8n's Anthropic node.** At 2.41.3 the node's "Message a Model" operation has Web Search, Max Uses and Allowed/Blocked Domains options [Source]. Claude searches the open web, returns 3–5 people with name, title, a public profile link, a one-line reason and cited sources [Doc: citations always on]. Cost is $10 per 1,000 searches plus tokens [Doc].
- **Add cheap, clean signals around it:** the posting text (it often names the manager's role, not the person) [Observed], and for devtools companies, GitHub org public members [Doc; Observed].
- **Trigger: a "Find people" URL button on each lead message**, pointing at a Webhook with "Ignore Bots" on and a signed `lead_id` [Opinion]. The result is a new Telegram message: apply link, pay, location, fit line, then the people list. Rahat opens the links and reaches out by hand.
- **Keep the template compliant.** n8n's template guidelines don't ban ToS-violating templates in writing [Doc; Unverified that no such rule exists], but a portfolio template for a DevRel role that automates LinkedIn would teach users to break LinkedIn's terms [Opinion].

---

## 2. LinkedIn's rules

**User Agreement, effective November 3, 2025** (linkedin.com/legal/user-agreement)

- Section 8 intro: the Dos and Don'ts and the Professional Community Policies limit what you can do "unless otherwise explicitly permitted by LinkedIn in a separate writing (e.g., through a research agreement)" [Doc].
- **8.2 Don'ts, relevant items (verbatim)** [Doc]:
  - "Develop, support or use software, devices, scripts, robots or any other means or processes (such as crawlers, browser plugins and add-ons or any other technology) to scrape or copy the Services, including profiles and other data from the Services;"
  - "Override any security feature or bypass or circumvent any access controls or use limits of the Services (such as search results, profiles, or videos);"
  - "Copy, use, display or distribute any information (including content) obtained from the Services, whether directly or through third parties (such as search tools or data aggregators or brokers), without the consent of the content owner (such as LinkedIn for content it owns);"
  - "Use bots or other unauthorized automated methods to access the Services, add or download contacts, send or redirect messages, create, comment on, like, share, or re-share posts, or otherwise drive inauthentic engagement;"
  - "Interfere with the operation of, or place an unreasonable load on, the Services (e.g., spam, denial of service attack, viruses, manipulating algorithms);"
  - The first item also bans using another's account "(such as sharing log-in credentials or copying cookies)".
- **3.4 Limits:** "LinkedIn reserves the right to restrict, suspend, or terminate your account if you breach this Contract or the law or are misusing the Services (e.g., violating any of the Dos and Don'ts or Professional Community Policies)." It also reserves the right to limit "your ability to contact other Members" [Doc].
- The Agreement has no numbered sub-items inside 8.2. Cite them by quoting the text [Observed].

**"Prohibited software and extensions" help page** (answer a1341387) [Doc]
- "we don't permit the use of any third party software, including 'crawlers', bots, browser plug-ins, or browser extensions that scrape, modify the appearance of, or automate activity on LinkedIn's website."
- "Any member who uses tools for such purposes is in violation of the User Agreement. This means that they risk having their accounts restricted or shut down."
- LinkedIn says it keeps improving "technical measures and defenses against the operation of scraping, automation, and other tools" [Doc].

**Professional Community Policies** [Doc]
- "Do not spam members or the platform." This covers "untargeted, irrelevant, obviously unwanted, unauthorized, inappropriate commercial or promotional, or gratuitously repetitive messages", and using invitations "to send promotional messages to people you don't know".
- Restricted goods include "sale of scraped data".
- "Repeated or egregious offenses can result in account restriction."

**Account risk, stated plainly**
- A browser agent (Airtop, Browserbase, Browser Use, Puppeteer, or any "browser-use type thing") that searches LinkedIn or opens profiles while logged in as Rahat is the case the help page describes: third-party software automating activity on LinkedIn's website [Doc]. The stated consequence is restriction or shutdown of that account [Doc].
- Running it on a cloud browser with a saved login profile (for example Airtop's "Save profile on termination" [Source]) doesn't change what the tool does on LinkedIn [Inference].
- How often LinkedIn detects low-volume automation is [Unverified]. LinkedIn publishes no thresholds.
- **[Opinion]** During an active job search, Rahat's LinkedIn account is the channel for recruiters and for the manual outreach this feature feeds. Losing it costs more than the feature saves.

**The public-template angle**
- n8n's Template submission guidelines (Creator hub, fetched 2026-09-29) cover quality, sticky notes, no hardcoded keys, no personal identifiers and no plagiarism. They say nothing about third-party terms of service [Doc; Observed].
- n8n's Customer Acceptable Use Policy (March 2026) bans processing personal data "without a lawful basis", "unauthorized profiling or tracking of individuals" and spam "in violation of applicable law". It has no clause on breaking a third party's ToS [Doc].
- n8n's verified community node registry includes several LinkedIn-automation packages, for example "Browserflow for LinkedIn", "Linked API", "Waalaxy" and "Periodix LinkedIn" [Observed]. **[Inference]** n8n's verification checks security and code quality, not the target site's terms. That is not a signal that LinkedIn allows it.
- **[Opinion]** For a DevRel application, a template that shows compliant design (official APIs, cited public sources, a human sends every message) is the stronger portfolio piece.

---

## 3. LinkedIn's official APIs

**Open permissions (self-serve, any developer)** [Doc: Getting Access, updated 2026-06-03]

| Product | Permission | What it gives |
|---|---|---|
| Sign in with LinkedIn using OpenID Connect | `profile` | The authenticated member's name, headline and photo |
| Sign in with LinkedIn using OpenID Connect | `email` | The authenticated member's primary email |
| Share on LinkedIn | `w_member_social` | Post, comment and like on behalf of the authenticated member |

- "Open Permissions are the only permissions that are available to all developers without special approval" [Doc].
- Sales Navigator data (`r_sales_nav_profiles` and others) needs SNAP partner approval. Talent integrations need a Talent partner application. Compliance is closed [Doc].
- **Other members' profiles:** "The use of this API is restricted to those developers approved by LinkedIn". To read another member you need a Person ID, "available only via certain limited access APIs". "You may never store data returned from the Profile API for members other than the authenticated member" [Doc: Profile API].
- **People search:** no open product offers it [Doc: Getting Access lists none]. **[Inference]** A regular developer app can't list employees at a company.

**n8n's LinkedIn node at 2.41.3** [Source: `packages/nodes-base/nodes/LinkedIn/`]
- One resource, Post, with one operation, Create (as a person or an organization; text, article or image; visibility Connections or Public).
- Credentials: `linkedInOAuth2Api` requests `w_member_social` plus `profile,email,openid` (or legacy `r_liteprofile,r_emailaddress`), with optional `w_organization_social`. `linkedInCommunityManagementOAuth2Api` requests `w_member_social w_organization_social r_basicprofile`.
- It calls `/v2/userinfo` or `/v2/me` only to find the posting member's ID. No search or read operations exist.

---

## 4. Compliant ways to answer "who at company X should I contact"

### 4a. Search APIs that return public profile URLs

| Option | Status and cost (as of 2026-09-29) | In n8n |
|---|---|---|
| Brave Search API | Search plan $5 per 1,000 requests, $5 monthly free credits, 50 qps [Doc: brave.com/search/api] | Verified community node `@brave/n8n-nodes-brave-search` 1.1.8 [Observed]; or HTTP Request |
| Google Custom Search JSON API | "closed to new customers"; existing customers have until January 1, 2027 [Doc] | Not usable for a new setup |
| Bing Search APIs | Retired August 11, 2025 [Doc: Microsoft Lifecycle] | Gone |
| SearXNG | Self-hosted metasearch. n8n's one-line installer (`get.n8n.io`) bundles it for n8n Assistant's web search [Doc] | Built-in SearXNG Tool node (AI Agent tool) [Source]; or HTTP Request |
| Tavily | 1,000 free credits/month, then $0.008/credit [Doc: pricing] | Verified community node `@tavily/n8n-nodes-tavily` 0.5.1 [Observed] |
| Exa | Search $4 per 1,000 requests, $10 free monthly credits [Doc: pricing]. Has a `people` category "for finding people profiles" [Doc] | Verified community node `n8n-nodes-exa-official` 0.4.1 [Observed] |
| SerpApi | Not priced here | Built-in SerpApi Tool node [Source] |

- **Brave storage terms:** "If you would like to store the API results in part or whole ... you will need to subscribe to a plan that explicitly grants storage rights" [Doc]. **[Inference]** Keeping names and URLs in a Data Table may count as storing results. Check Brave's full terms before relying on it.
- **LinkedIn-specific terms:** none of the search API pages I read restrict returning `linkedin.com` results [Observed]. I didn't read each vendor's full terms of service [Unverified].
- **SearXNG on Coolify:** Rahat's Coolify setup (see `job-scout-coolify.md`) starts from the plain n8n template, which doesn't include SearXNG [Inference]. SearXNG gets its results by querying other engines, so it inherits their terms [Inference].
- **The UA clause on search tools:** 8.2 bans copying or displaying information "obtained from the Services ... through third parties (such as search tools ...)" without consent [Doc]. **[Inference]** Surfacing a name, title and profile link for Rahat to open by hand is far from scraping. Storing or redisplaying profile text (headline, experience) copied from search snippets moves closer to that clause. Keep only name, title, URL and a reason that cites a non-LinkedIn source where possible.

### 4b. Claude with the web search server tool (recommended)

**The tool** [Doc: platform.claude.com web-search-tool]
- Versions: `web_search_20250305` (basic), `web_search_20260209` (dynamic filtering), `web_search_20260318` (adds `response_inclusion`).
- Parameters: `max_uses`, `allowed_domains` or `blocked_domains` (not both), `user_location`.
- "Citations are always enabled for web search." Each citation has `url`, `title` and up to 150 characters of `cited_text`.
- "When displaying API outputs directly to end users, citations must be included to the original source." **[Inference]** Put the source link next to each suggested person in Telegram.
- It is on by default unless an org admin turned it off in the Claude Console.
- **Price:** "$10 per 1,000 searches, plus standard token costs for search-generated content." Search results count as input tokens [Doc].

**In n8n at 2.41.3**
- **Anthropic node → Text → Message a Model** has Options: Web Search (boolean), Web Search Max Uses (default 5), Web Search Allowed Domains, Web Search Blocked Domains [Source: `vendors/Anthropic/actions/text/message.operation.ts`].
  - It sends `type: 'web_search_20250305'`, the basic version [Source]. Dynamic filtering needs the HTTP Request node [Inference].
  - It handles `pause_turn` by resending, up to 3 times [Source].
  - "Simplify Output" returns `content` (all blocks, including citations) and an optional `merged_response` (text only) [Source]. A Code node pulls citations out of `content` [Inference].
  - The node has no structured-output parser. Ask for JSON in the prompt and parse it in a Code node [Inference].
- **The Anthropic Chat Model sub-node (AI Agent path) has no web search option** at 2.41.3 [Source: `LmChatAnthropic.node.ts`]. Use the Anthropic app node, or HTTP Request to `/v1/messages`.

**How it would work for one lead** [Opinion]
- Input: company name, domain, job title, team (Ashby `team`/`department`), and the posting text.
- Prompt: find 3–5 current employees relevant to this role (likely hiring manager, team lead, recruiter for the function, a peer on the team). For each, return name, title, a public profile URL only if it appears in a search result (never guess a URL), a one-line reason, and the source URL.
- Leave domains unrestricted so Claude can use team pages, blogs, talks and GitHub for the reason line. Set Max Uses to 3–5 to cap cost.
- **Cost per lead [Inference]:** 5 searches = $0.05 in search fees, plus input tokens for the results at the model's rate. Token volume is unmeasured. Read `usage.server_tool_use.web_search_requests` and token counts in a spike.
- **Accuracy [Inference]:** titles in search results can be stale. The Telegram message should show the source link so Rahat can check before reaching out.

### 4c. Data from the posting and the company

- **ATS fields:** the Ashby, Lever and Greenhouse public APIs have no hiring-manager or recruiter field [Observed: field lists from n8n, Spotify and Instacart boards].
- **Posting text often names the manager's role, not the person.** Two of 34 n8n postings and several Instacart postings say who the role reports to, for example "You'll report directly to our VP People" or "reporting to the Head of IT and Enterprise Security" [Observed]. **[Inference]** Pass this line to Claude as a search hint.
- **GitHub org members** (useful for devtools companies):
  - `GET /orgs/{org}/members` returns concealed members only to org members. `GET /orgs/{org}/public_members` lists public members [Doc].
  - `n8n-io` had 19 public members. The list items have `login`, `html_url` and `avatar_url` but no `name` [Observed]. Names and bios need `GET /users/{login}` per member [Inference].
  - Unauthenticated limit is 60 requests per hour; a personal token gets 5,000 [Doc].
  - n8n's GitHub node has Organization → Get Members, which calls `/orgs/{owner}/members` [Source].
- **Company team or about pages:** Claude's web search reaches these without extra setup [Inference].

### 4d. Enrichment APIs (brief)

- **Hunter:** built-in n8n node with Domain Search, Email Finder and Email Verifier [Source]. Domain Search returns `first_name`, `last_name`, `position`, `seniority`, `department`, `linkedin` and `sources`, filterable by seniority and department [Doc]. Free plan: 50 credits/month, API included; Starter $49/month (pricing page, 2026-09-29) [Doc].
- **Apollo:** verified community node `@apolloio/n8n-nodes-apollo` 0.3.1 [Observed]. People API Search (`/mixed_people/api_search`) filters by company domain and title, uses "0 credits", and returns no emails or phones [Doc].
- **Clearbit:** a built-in n8n node still exists [Source]. Its current signup and API status after the HubSpot acquisition is [Unverified]. The FAQ page returned 403.
- **[Inference]** Hunter's and Apollo's `linkedin` fields come from data brokers. UA 8.2 names "data aggregators or brokers" as a route for information obtained from LinkedIn. Emails aren't needed because Rahat reaches out on LinkedIn by hand. **[Opinion]** Skip these for the proof of concept.

---

## 5. Browser automation in n8n (for completeness, not recommended)

| Option | Kind at 2.41.3 | Notes |
|---|---|---|
| Airtop | **Built-in** node [Source: `nodes-base/nodes/Airtop`] | Cloud browser. Sessions, saved profiles, windows, "Query page", "Smart scrape page", click, type, and an Agent operation [Doc; Source] |
| Browserless | Verified community node `n8n-nodes-browserless-api` 1.2.1 [Observed] | Headless browser API |
| Browserbase | Verified community node `n8n-nodes-browserbase` 1.4.0 [Observed] | "Browser automation, web search, and page fetches" |
| Browser Use | Verified community node `n8n-nodes-browser-use-cloud` 1.2.1 [Observed] | Natural-language browser agent |
| Anchor Browser | Verified community node `n8n-nodes-anchorbrowser` 0.1.12 [Observed] | Browser automation API |
| Firecrawl | Verified community node `@mendable/n8n-nodes-firecrawl` 2.1.4 [Observed] | Scrape, crawl and search |
| Puppeteer | Unverified npm package `n8n-nodes-puppeteer` 1.5.0 [Observed: npm; not in the verified registry] | Needs Chromium in the container |

- **Community nodes on self-hosted CE:** allowed by default. `N8N_COMMUNITY_PACKAGES_ENABLED`, `N8N_VERIFIED_PACKAGES_ENABLED` and `N8N_UNVERIFIED_PACKAGES_ENABLED` all default to `true` [Doc]. Verified nodes install from the nodes panel by the owner or an admin [Doc]. "Unverified community nodes aren't available on n8n cloud" [Doc].
- **Risks n8n lists:** community nodes "have full access to the machine that n8n runs on" and to workflow data [Doc].
- **Templates with community nodes are accepted.** The guidelines say to add "A disclaimer that it's self-hosted only" and "A workflow image at the top (since previews don't render)" [Doc: Template submission guidelines].
- **Link fix for the build doc:** the Template submission guidelines URL in `job-scout-build.md` (`.../99598944767340dab402c90b124b1f77`) now shows "This page couldn't be found". The Creator hub links to `https://n8n.notion.site/Template-submission-guidelines-9959894476734da3b402c90b124b1f77` [Observed].
- **[Opinion]** The recommended path uses only built-in nodes (Anthropic, HTTP Request, GitHub, Telegram, Data Table). That keeps the template importable on n8n Cloud with no self-hosted disclaimer.

---

## 6. The "pick a lead" flow

This builds on `job-scout-telegram.md` sections 5, 7 and 8. It doesn't repeat them.

**Trigger options for "Find people"**

| | URL button → Webhook (recommended) | Send-and-Wait "Approve Within Chat" per lead | Callback button + Telegram Trigger |
|---|---|---|---|
| Tap opens | A browser page that says "Working on it" [Inference] | Nothing; stays in chat [Source] | Nothing; stays in chat [Doc] |
| Executions | One short run per tap | One waiting execution per lead [Source] | One short run per tap |
| Extra setup | Webhook with Ignore Bots [Source: Webhook `ignoreBots`] and a signed `lead_id` [Opinion] | None | A Telegram Trigger, which claims the bot's one webhook and must forward `nhitl1|` taps [Source] |

- **[Opinion]** Use the URL button for the proof of concept. It matches the Pass button (URL → Form) and needs no Trigger. Move to a callback button if a Trigger is added later for `/scan`; `find|<lead_id>` must fit Telegram's 64-byte `callback_data` limit [Doc].
- **Guard against repeats [Inference]:** check a `contacts` Data Table first. If people were already found for this lead, resend the stored result instead of searching again.

**The people-finding sub-workflow [Opinion]**
1. Webhook receives `lead_id` and token. Verify the token and respond at once with a short HTML page.
2. Data Table: read the lead (company, domain, title, team, apply URL, pay, location, fit line from scoring).
3. Optional: GitHub Get Members for companies flagged as devtools.
4. Anthropic Message a Model with Web Search on, Max Uses 3–5, and the prompt from 4b.
5. Code node: parse the JSON, drop any person without a source URL, keep 3–5.
6. Data Table: insert rows into `contacts` (lead_id, name, title, profile_url, reason, source_url, found_at).
7. Telegram: send one message (well under 4096 characters [Doc]).

**What arrives in Telegram [Opinion]**

```
n8n · Senior Developer Advocate, US
Apply: <apply link>
$<pay range> · Remote (US) · <one-line fit>

People to contact:
1. <Name> — <Title>
   <profile link> · <one-line reason> · source: <link>
2. ...
```

- No draft message text in the proof of concept. If added later, it would be one editable line per person, shown in the message for Rahat to copy [Opinion].
- Nothing in the flow sends to anyone except Rahat's own chat. This is Rahat's scope decision, not a finding.

---

## 7. Recommendation for the demo

- **Path:** Anthropic node with Web Search, fed by the lead's stored data and the posting's "reports to" line; GitHub public members as an optional extra for devtools companies [Opinion].
- **Why it demos well [Opinion]:** one tap in Telegram, a visible Claude step in the n8n canvas, and a reply with names, titles, links and a cited reason for each. It uses only built-in nodes and no LinkedIn login.
- **What the viewer sees on camera [Opinion]:** tap "Find people" on the n8n DevRel lead, switch to the n8n execution view, then back to Telegram for the result, then Rahat opening one profile by hand.
- **Say it out loud in the video [Opinion]:** the automation suggests; a person decides and reaches out. That framing matches LinkedIn's rules and n8n's human-in-the-loop story.
- **Spike before building:** one Message a Model call with Web Search on a real lead, to measure tokens, cost per lead, how often profile URLs appear in results, and title accuracy.

---

## 8. Open questions for Rahat

- **Risk tolerance:** confirm that no LinkedIn automation runs on your account, not even read-only browsing by an agent.
- **How many people per lead** (3? 5?) and which roles to prefer: hiring manager, team peers, recruiter, or DevRel/community people?
- **Profile links:** LinkedIn only, or also GitHub, X, personal sites when that's what the search finds?
- **Storage:** keep suggested contacts in a Data Table (dedupe, later review), or send them to Telegram only?
- **Spend cap:** is about $0.05 in search fees per lead, plus tokens, acceptable? Should "Find people" run only on tap, never automatically for top leads?
- **Template:** ship "Find people" in the public template, or keep it in Rahat's own instance only?

---

## Sources

**LinkedIn**
- User Agreement (effective November 3, 2025): https://www.linkedin.com/legal/user-agreement
- Professional Community Policies: https://www.linkedin.com/legal/professional-community-policies
- Prohibited software and extensions: https://www.linkedin.com/help/linkedin/answer/a1341387
- Getting Access to LinkedIn APIs: https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access
- Profile API: https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api
- People API overview: https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/overview

**n8n docs and policies**
- Community nodes, installation: https://docs.n8n.io/integrations/community-nodes/installation-and-management.md
- Install verified community nodes: https://docs.n8n.io/integrations/community-nodes/installation-and-management/install-verified-community-nodes.md
- Community node risks: https://docs.n8n.io/integrations/community-nodes/risks.md
- Submit community nodes: https://docs.n8n.io/connect/create-nodes/deploy-your-node/submit-community-nodes.md
- Full docs dump (env vars, one-line setup with SearXNG): https://docs.n8n.io/llms-full.txt
- Airtop node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.airtop.md
- Anthropic node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.anthropic.md
- Creator hub: https://n8n.notion.site/n8n-Creator-hub-7bd2cbe0fce0449198ecb23ff4a2f76f
- Template submission guidelines: https://n8n.notion.site/Template-submission-guidelines-9959894476734da3b402c90b124b1f77
- Customer Acceptable Use Policy: https://n8n.io/legal/customer-acceptable-use-policy/
- Verified community node registry: https://api.n8n.io/api/community-nodes

**n8n source at `n8n@2.41.3`** (under https://github.com/n8n-io/n8n/blob/n8n@2.41.3/)
- `packages/nodes-base/nodes/LinkedIn/{LinkedIn.node.ts,PostDescription.ts,GenericFunctions.ts}`
- `packages/nodes-base/credentials/{LinkedInOAuth2Api,LinkedInCommunityManagementOAuth2Api}.credentials.ts`
- `packages/@n8n/nodes-langchain/nodes/vendors/Anthropic/actions/text/message.operation.ts`
- `packages/@n8n/nodes-langchain/nodes/vendors/Anthropic/transport/index.ts`
- `packages/@n8n/nodes-langchain/nodes/llms/LMChatAnthropic/LmChatAnthropic.node.ts`
- `packages/@n8n/nodes-langchain/nodes/tools/{ToolSearXng,ToolSerpApi}/`
- `packages/nodes-base/nodes/{Airtop,Hunter,Github,Clearbit}/`
- `packages/nodes-base/nodes/Webhook/description.ts`
- `packages/cli/src/modules/community-packages/community-node-types-utils.ts`
- `packages/frontend/editor-ui/src/features/settings/communityNodes/components/nodeCreator/CommunityNodeInfo.vue`

**Anthropic**
- Web search tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool

**Search and enrichment vendors**
- Brave Search API: https://brave.com/search/api/
- Google Custom Search JSON API: https://developers.google.com/custom-search/v1/overview
- Bing Search APIs retirement: https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement
- Tavily pricing: https://www.tavily.com/pricing
- Exa search reference: https://exa.ai/docs/reference/search
- Exa pricing: https://exa.ai/pricing
- Hunter API v2: https://hunter.io/api-documentation/v2
- Hunter pricing: https://hunter.io/pricing
- Apollo People API Search: https://docs.apollo.io/reference/people-api-search

**GitHub and ATS**
- Org members: https://docs.github.com/en/rest/orgs/members?apiVersion=2022-11-28
- REST rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- Ashby: https://api.ashbyhq.com/posting-api/job-board/n8n
- Lever: https://api.lever.co/v0/postings/spotify?mode=json
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/instacart/jobs?content=true
