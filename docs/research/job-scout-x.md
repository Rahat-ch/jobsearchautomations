# Job Scout: X (Twitter) research

Research date: 2026-09-29. Sources: X developer docs on docs.x.com fetched as `.md` on 2026-09-29 (pricing, usage and billing, rate limits, Search Posts, operators, pagination, User Search, Users affiliates, Direct Messages, changelog), the X Developer Agreement (last updated April 27, 2026), the X Developer Policy and X's Developer Guidelines page; n8n docs fetched as `.md` on 2026-09-29; n8n source at tag `n8n@2.41.3` (`packages/nodes-base/nodes/Twitter/`, `packages/nodes-base/credentials/TwitterOAuth2Api.credentials.ts`). Public ATS posting URLs checked with unauthenticated GETs. No X endpoint was called, and no app, credential or workflow was created.

**Labels.** **[Doc]** means a primary doc states it. **[Source]** means I read it in n8n's source at `n8n@2.41.3`. **[Observed]** means I saw it live. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

**Scope set by Rahat (2026-09-29):** the automation never sends DMs. It suggests people (name, handle, why), and Rahat contacts them by hand.

---

## 1. Summary and recommendation

- **X's self-serve API is pay-per-use now.** Pay-Per-Use launched February 6, 2026. You buy credits, and each post read costs $0.005 and each user read $0.010 [Doc: pricing page and changelog, fetched 2026-09-29]. There's a 3 million post-read cap per monthly billing cycle [Doc]. Legacy Basic and Pro plans still exist for existing subscribers [Doc: changelog Feb 6, 2026].
- **Recent search (`GET /2/tweets/search/recent`, last 7 days) is enough for a daily run** [Doc]. Full-archive search isn't needed.
- **Call search with the HTTP Request node, not the X node.** At 2.41.3 the X node's Search operation drops `includes` and `meta`. You get no author usernames, no `newest_id` for `since_id`, and no expansions [Source].
- **Use a Bearer Token (app-only) credential for search and user lookup.** App-only auth can't send DMs [Doc], which enforces Rahat's no-DM rule at the credential level [Inference]. n8n's X OAuth2 credential always requests `dm.write`, `like.write` and `follows.write` [Source].
- **Route ATS links into the existing fetchers.** Use `url:` to find posts that link to Ashby, Greenhouse or Lever. Then parse `entities.urls[].expanded_url` into board plus job ID and call the Ashby, Greenhouse or Lever fetcher for structured data [Inference; URL shapes Observed in section 3.6].
- **People to suggest, in order of signal** [Opinion]:
  1. The author of the hiring post itself.
  2. Other authors of recent posts about the role or team.
  3. The company's affiliated accounts (`GET /2/users/{id}/affiliates`), if the company has them.
  4. `GET /2/users/search`, which needs user-context auth.
- **Keep X optional in the forkable template.** Every forker needs their own funded X developer account [Inference]. Ship the X branch disabled or behind a config flag [Opinion].

---

## 2. Access, pricing and limits

**Pricing model** [Doc: docs.x.com/x-api/getting-started/pricing, fetched 2026-09-29]
- "The X API uses pay-per-usage pricing. No subscriptions." You buy credits in the Developer Console (console.x.com), and each request deducts from them.
- Reads are charged per resource returned. Posts: Read costs $0.005 per resource. User: Read costs $0.010. DM Event: Read costs $0.010.
- Writes are charged per request. For example, DM Interaction: Create costs $0.015 and Counts: Recent costs $0.005.
- "Prices are subject to change. Current rates are always available in the Developer Console."
- **Deduplication:** a resource fetched twice in the same UTC day is charged once. It's a "soft guarantee."
- **Failed requests and empty results:** "Only successful responses that return data are billed" [Doc: Usage and Billing].
- **Cap:** "Pay-per-usage plans are capped at 3 million Post reads per monthly billing cycle." Above that, Enterprise.
- **Spending controls:** a per-billing-cycle spending limit blocks requests once reached. Auto-recharge is optional. When credits run out, "API requests will fail until you purchase more credits." The HTTP status for that case is [Unverified].
- **History** [Doc: changelog]:
  - Oct 20, 2025: closed pilot.
  - Feb 6, 2026: launch. "Basic and Pro plans remain available, and existing subscribers can opt in to Pay-Per-Use." "Recently active Legacy Free tier users receive a one-time $10 voucher."
  - Apr 20, 2026: Owned Reads at $0.001, and Following, Likes and Quote-Posts removed from all self-serve tiers.
- **[Unverified]** Current Basic and Pro prices, caps and endpoint access. docs.x.com no longer lists them, and developer.x.com returned HTTP 402 to a fetch.

**Which access unlocks search** [Doc: Search Posts intro]
- Recent search: "Available to all developers." Last 7 days, up to 100 posts per request.
- Full-archive search: "Available to pay-per-use and Enterprise customers." Back to 2006, up to 500 per request, app-only auth only.

**Rate limits** [Doc: docs.x.com/x-api/fundamentals/rate-limits, fetched 2026-09-29; the page doesn't vary them by plan]

| Endpoint | Per app | Per user | Notes |
|---|---|---|---|
| `GET /2/tweets/search/recent` | 450/15 min | 300/15 min | 10 default, 100 max results; 512-char query |
| `GET /2/tweets/search/all` | 1/sec, 300/15 min | 1/sec | 500 max results; 1024-char query |
| `GET /2/users/by/username/:username`, `/2/users/:id` | 300/15 min | 900/15 min | |
| `GET /2/users/search` | 300/15 min | 900/15 min | but see section 4 on auth |
| `GET /2/usage/tweets` | 50/15 min | — | |

- Per-app limits apply with a Bearer Token. Per-user limits apply with OAuth 1.0a or OAuth 2.0 user tokens [Doc].
- A daily run makes a handful of calls, so rate limits won't matter. Cost will [Inference].

**What a key tells you, and how Rahat can check their plan**
- An API key, secret or bearer token doesn't show which plan or tier the account is on. Keys identify the app, and the plan belongs to the developer account [Inference; Doc: Getting Access lists what each credential is for].
- **Where Rahat can check** [Doc]: console.x.com shows credit balance, usage by endpoint and app, cost tracking, and the account's rate limits.
- **From the API:**
  - `GET /2/usage/credits` returns the pay-per-use credit balance in USD.
  - `GET /2/usage/tweets` returns daily usage and `project_cap`, the monthly post limit.
  - **[Inference]** A legacy Basic or Pro project would likely show a different `project_cap` than 3,000,000.
  - Rahat can run either call. I didn't.

**Cost for a daily run** [Inference, arithmetic on the rates above]
- Posts cost 0.5 cents each. Three queries that each return a full page of 100 new posts cost $1.50 per run. A day with 40 new matching posts costs $0.20.
- `since_id` means each post is paid for once, even across overlapping queries on the same UTC day (deduplication).
- **[Unverified]** Whether author objects returned through `expansions=author_id` are billed as User: Read ($0.010 each). The pricing page doesn't say. Check the console's by-endpoint usage after a test run.
- Set a spending limit in the console before the first scheduled run [Opinion].

---

## 3. Searching for job posts

### 3.1 Query rules [Doc: Build a query, Search Operators]
- **Length:** self-serve recent search allows 512 characters, full-archive 1,024, and Enterprise 4,096.
- **Syntax:** space is AND, plus `OR`, parentheses, and `-` for negation. AND binds before OR. Don't negate a group; negate each term instead.
- **Standalone vs conjunction-required:** keywords, `"phrases"`, `from:`, `to:`, `@`, `url:`, `list:` and `conversation_id:` stand alone. `has:links`, `is:retweet`, `is:reply`, `is:verified` and `lang:` need at least one standalone operator.
- **`url:`** does a "Tokenized match on URL (matches `url` or `expanded_url` fields)". So it sees through t.co links.
- **Engagement operators:** `min_likes:`, `min_replies:` and `min_reposts:` were deprecated Jan 19, 2026 and restored with the new search index on May 4, 2026.
- **Retweets:** since May 4, 2026, "retweets are no longer returned in keyword-based search results" [Doc: changelog]. `-is:retweet` is now redundant but harmless.
- **No bio operators in search:** search doesn't support `bio:`, `bio_name:` or `bio_location:`. They exist only on the filtered stream [Doc: stream recovery note].

### 3.2 Request parameters [Doc: Search Posts Recent OpenAPI]
- `query` (required). `max_results` from 10 to 100, default 10.
- `start_time`, which must be within the last 7 days, and `end_time`.
- `since_id` and `until_id`. You can send at most one of `start_time`/`since_id`, and at most one of `end_time`/`until_id`.
- `next_token` (or `pagination_token`), and `sort_order` (`recency` or `relevancy`).
- **Suggested fields:** `tweet.fields=created_at,author_id,entities,lang,conversation_id`, `expansions=author_id`, and `user.fields=username,name,description,url,affiliation,verified`.
- **URL entities:** `entities.urls[]` carries `expanded_url` ("The fully resolved URL"), `unwound_url` ("The final destination after following redirects"), `display_url`, `title` and `description`.
- The response carries `data[]`, `includes.users[]` and `meta` (`newest_id`, `oldest_id`, `result_count`, `next_token`).

### 3.3 Pagination and daily incremental runs [Doc: Pagination]
- Results come newest first. Repeat with `next_token` until the response has none. "The next_token does not expire."
- **Polling pattern:** send `since_id` = the last stored `newest_id`.
  - When a run has several pages, keep the `newest_id` from the **first** page, and send the same `since_id` with each `next_token`.
  - Store one `newest_id` per query in the config Data Table [Opinion].
- **[Unverified]** What recent search does with a `since_id` older than 7 days. If the workflow was down for more than 7 days, fall back to `start_time` = now minus 7 days [Opinion].
- Cap pages per query, for example 3, to bound cost [Opinion].

### 3.4 Example queries [Opinion; none were run]
Rahat edits these in the forkable config. Replace the `COMPANY_*` placeholders.

1. **Hiring posts that link to an ATS** (187 characters):
   `("developer advocate" OR "developer relations" OR devrel) (hiring OR "we're hiring" OR "join us" OR "open role") (url:ashbyhq.com OR url:greenhouse.io OR url:lever.co) lang:en -is:retweet`
2. **Remote-US DevRel hiring, any link** (224 characters):
   `("developer advocate" OR "developer relations" OR devrel OR "developer experience") (hiring OR "we're hiring" OR "now hiring") (remote OR "remote us" OR "us remote" OR "united states") has:links lang:en -is:retweet -is:reply`
3. **Watch-list companies' own accounts** (138 characters):
   `(from:COMPANY_HANDLE_1 OR from:COMPANY_HANDLE_2 OR from:COMPANY_HANDLE_3) (hiring OR "join us" OR "open role" OR "we're hiring") has:links`
4. **People at a company talking about the role**, for section 4 (140 characters):
   `(@COMPANY_HANDLE OR "COMPANY NAME") ("developer advocate" OR devrel OR "developer relations") (hiring OR "my team" OR "join us") -is:retweet`

- **[Unverified]** Whether `url:ashbyhq.com` matches `jobs.ashbyhq.com/...` through tokenization. The docs say "tokenized match" without giving subdomain examples. Test once, or use `url:"jobs.ashbyhq.com"`.
- Keyword search can't tell "remote US" from "remote EU". Keep the existing remote-US filter and LLM scoring downstream [Inference].

### 3.5 X's own advice
- "Using broad operators like a single keyword or hashtag is not recommended — it will match a massive volume of Posts and quickly consume your usage limits" [Doc].
- X has a Query Builder tool at developer.x.com/apitools/query [Doc].

### 3.6 Routing expanded URLs into the ATS fetchers
Public posting URL shapes, from each ATS's own API on 2026-09-29 [Observed]:
- **Ashby:** `https://jobs.ashbyhq.com/{board}/{jobId}`. Apply URL: the same plus `/application` (n8n board).
- **Greenhouse:** `https://job-boards.greenhouse.io/{token}/jobs/{id}` (Vercel). Instacart's `absolute_url` is its own domain instead: `https://instacart.careers/job/?gh_jid={id}`.
- **Lever:** `https://jobs.lever.co/{site}/{postingId}`. Apply URL: the same plus `/apply` (Spotify).

**Routing, all [Inference]:**
- A Code node applies regexes to `expanded_url`, falling back to `unwound_url`. The captures give board or site plus job ID, which call the existing single-job endpoints from `job-scout-build.md` section 2.8.
- A `gh_jid` query parameter on any domain signals Greenhouse, but the board token isn't in the URL. Those leads need a lookup table or an LLM guess, so mark them "unrouted."
- Posts with no ATS link become "X-only leads." They carry the post URL (`https://x.com/{username}/status/{id}`) and the author as the first contact.

---

## 4. Finding people at a company to suggest

The goal: for a picked lead, list 3 to 5 people with name, handle, and why. Rahat contacts them by hand.

| Method | Endpoint | Auth | Cost | Notes |
|---|---|---|---|---|
| Hiring post's author | already in `includes.users` from search | Bearer | free if included; [Unverified] | Strongest signal: this person posted the role [Opinion] |
| Recent posts about company + role | recent search, query 4 above, `expansions=author_id` | Bearer | $0.005 per post | Authors are often employees or recruiters. Their bios need checking [Inference] |
| Company affiliates | `GET /2/users/{id}/affiliates` (`max_results` 1–1000) | Bearer, OAuth2 user or OAuth 1.0a | [Unverified]; likely User: Read | Docs give only the path and parameters. **[Inference]** It lists accounts carrying the company's affiliate badge, so it only works for companies that have affiliates. No rate limit is listed |
| User keyword search | `GET /2/users/search` | **User context only**: the OpenAPI security lists `OAuth2UserToken` (`users.read`, `tweet.read`) or `UserToken`, not `BearerToken` | $0.010 per user; **default `max_results` is 100** | Matches "name, username, or content in their bio". The query pattern is `^[A-Za-z0-9_' ]{1,50}$`: 50 characters, no operators, no quotes. The docs page's example uses a Bearer token, which conflicts with the spec. Test before relying on it |
| Profile lookup | `GET /2/users/by/username/:username` | Bearer | $0.010 per user | To fetch bio, affiliation and URL for a handle already known |

- **User object fields useful for "why":** `description` (bio), `affiliation` (`description`, `url`, `user_id[]`), `url`, `location`, `verified`, `receives_your_dm` and `most_recent_post_id` [Doc: UserFields enum].
- **Budget:** always set `max_results` on user search, for example 10 ($0.10 at most). The default of 100 costs up to $1.00 per call [Inference, arithmetic].
- **Feasibility [Opinion]:** reliable for companies that post hiring on X or have affiliates. Weak for everything else. It's no replacement for LinkedIn, which stays in Rahat's Claude sessions per the Scope decision.
- **Policy limits for this feature** [Doc: Developer Policy, Agreement, Guidelines]:
  - The Agreement bars making X Content available for "investigating or tracking X users."
  - The Guidelines list "Profiling, tracking, or monitoring users without consent" as prohibited.
  - Off-X matching, such as tying a handle to an email or LinkedIn profile, is allowed without opt-in only on "Public data," and "Never match if it would surprise the user."
  - **[Opinion]** Run the lookup only when Rahat picks a lead. Store handle, user ID and a one-line reason. Don't watch individuals over time.

---

## 5. DMs

- The API has `POST /2/dm_conversations/with/:participant_id/messages`, and the n8n X node has a "Create Direct Message" operation. Automated DMs are allowed "only after user DMs you first" [Doc: Developer Guidelines; Developer Policy, "Always get explicit consent before sending people automated ... Direct Messages"].
- **Out of scope by Rahat's decision.** Job Scout never sends DMs.

---

## 6. The n8n X node at 2.41.3

- **Operations** [Source: `V2/*Description.ts`; Doc: node page]:
  - Tweet: Create, Delete, Like, Retweet, Search.
  - User: Get, by username, ID or "me".
  - Direct Message: Create.
  - List: Add member.
  - There's no user search, affiliates or usage operation. The node is `usableAsTool`.
- **Credential** [Source: `TwitterOAuth2Api.credentials.ts`]: X OAuth2 API only.
  - Grant type `pkce` (user context), authorization URL `https://x.com/i/oauth2/authorize`, token URL `https://api.x.com/2/oauth2/token`.
  - It always requests a fixed scope list that includes `tweet.write`, `like.write`, `follows.write`, `dm.write`, `dm.read`, `list.write` and `offline.access`.
  - Its UI notice still says "Some operations require a Basic or Pro API."
  - OAuth 1.0a was deprecated in n8n 0.236.0 [Doc: credentials page].
- **Docs and source disagree on rate limits.** n8n's credential doc says this credential "uses the OAuth 2.0 Bearer Token authentication method, so you'll be subject to app rate limits." The source uses PKCE user tokens, and X applies per-user limits to user tokens (300/15 min for recent search) [Source; Doc: X rate limits; Inference].
- **Search operation** [Source: `TwitterV2.node.ts`, `GenericFunctions.ts`, `TweetDescription.ts`]:
  - Calls `GET https://api.x.com/2/tweets/search/recent`.
  - Sends only `query`, `start_time`, `end_time`, `sort_order`, `tweet.fields` and `max_results` (the Limit, default 50).
  - "Return All" forces `max_results=10` and loops on `next_token`.
  - `twitterApiRequest` returns only the response's `data`, so `includes` (author users) and `meta` (`newest_id`) are lost. There's no `expansions`, `user.fields`, `since_id` or `next_token` input.
  - **[Inference]** A Limit below 10 or above 100 gets a 400 from X, since the API accepts 10–100.
  - The field help text says "500 characters maximum" (X says 512) and mentions "Academic Research access," which is outdated.
- **Use the HTTP Request node instead.**
  - For search, affiliates and profile lookup: **Authentication → Generic → Bearer Auth** with the app's Bearer Token [Doc: n8n HTTP Request credentials list "Bearer auth (generic credential type)"; Doc: X accepts Bearer for these endpoints].
  - Pagination mode "Update a Parameter in Each Request" can set `next_token` from `$response.body.meta.next_token` [Doc: n8n HTTP Request pagination].
  - For `/2/users/search`, which needs a user token: a generic OAuth2 credential with PKCE and only `tweet.read users.read offline.access`, or n8n's X OAuth2 credential as a Predefined Credential Type. The second carries `dm.write` and the other write scopes [Doc: n8n custom API actions; Inference].

---

## 7. Terms for storing and showing X data

- **Content compliance** [Doc: Developer Policy]: "If you store X Content offline, you must keep it up to date." Delete or modify within 24 hours of a request from X or the account owner. The Agreement adds deleted, protected or suspended content. After API access ends, delete within 10 business days [Doc: Guidelines].
- **Redistribution** [Doc: Developer Policy]:
  - Third parties may receive only Post, DM and User IDs, capped at 1,500,000 Post IDs per entity per 30 days.
  - Up to 500 public Post or User objects per person per day are allowed only by non-automated means.
  - **[Inference]** A Telegram message to Rahat's own chat, from Rahat's own app, is display to the app's user, not redistribution. Each person who forks the template uses their own key and sees only their own results.
- **Display** [Doc: Agreement, Guidelines]:
  - Modify X Content "only to format it for display." Don't strip timestamps. No iframes.
  - Follow the Display Requirements and Brand Guidelines.
  - **[Opinion]** In Telegram, show the author handle, date and a link to the post, not edited post text.
- **AI use** [Doc: Agreement III.A(k)]: X Content may not be used to "fine-tune or train a foundation or frontier model." **[Inference]** Sending post text to Claude for scoring isn't training.
- **Sensitive data:** don't infer or store health, political, religious and similar attributes about X users [Doc: Guidelines].
- **Minimal storage [Opinion]:**
  - Store post ID, author ID, handle, `expanded_url`, `created_at` and a short reason in Data Tables.
  - Purge X rows when a lead is closed or after 30 days.
  - This keeps the 24-hour deletion duty small without a compliance job. X offers batch compliance at `/2/compliance/jobs` if ever needed [Doc: rate limits page].

---

## 8. Open questions for Rahat

- **Plan:** is the X account on pay-per-use credits, a legacy Basic or Pro plan, or legacy Free? Check console.x.com (plan, credit balance, rate limits), or run `GET /2/usage/credits` and `GET /2/usage/tweets` yourself.
- **Budget:** what monthly spending limit should be set in the console for Job Scout?
- **Credentials:** does the existing app have a Bearer Token available? Is it OK to create a second, read-only app for Job Scout so the keys used in n8n can't write?
- **Hermes' queries:** what queries does Mina run on X today? Share the query strings (not keys) so the first config matches Hermes for the parallel run.
- **Watch list:** which company X handles go into query 3?
- **Template:** should X ship enabled or disabled by default?

---

## 9. Sources

**X developer docs** (fetched 2026-09-29; every page also available as `.md`)
- Pricing: https://docs.x.com/x-api/getting-started/pricing
- Usage and Billing: https://docs.x.com/x-api/fundamentals/post-cap
- Rate limits: https://docs.x.com/x-api/fundamentals/rate-limits
- About the X API: https://docs.x.com/x-api/getting-started/about-x-api
- Getting Access: https://docs.x.com/x-api/getting-started/getting-access
- Usage endpoints: https://docs.x.com/x-api/usage/introduction and https://docs.x.com/x-api/usage/get-usage-credits
- Search Posts: https://docs.x.com/x-api/posts/search/introduction
- Build a query: https://docs.x.com/x-api/posts/search/integrate/build-a-query
- Operators: https://docs.x.com/x-api/posts/search/integrate/operators
- Pagination: https://docs.x.com/x-api/posts/search/integrate/paginate
- Integration guide: https://docs.x.com/x-api/posts/search/integrate/overview
- Search Recent reference: https://docs.x.com/x-api/posts/search-recent-posts
- Search All reference: https://docs.x.com/x-api/posts/search-all-posts
- User Search: https://docs.x.com/x-api/users/search/introduction and https://docs.x.com/x-api/users/search-users
- Affiliates: https://docs.x.com/x-api/users/get-affiliates
- Manage DMs: https://docs.x.com/x-api/direct-messages/manage/introduction and https://docs.x.com/x-api/direct-messages/manage/integrate
- Changelog: https://docs.x.com/changelog
- Full docs: https://docs.x.com/llms-full.txt
- Developer Guidelines: https://docs.x.com/developer-guidelines
- Developer Agreement: https://docs.x.com/developer-terms/agreement
- Developer Policy: https://docs.x.com/developer-terms/policy
- Automation Rules (linked from the Policy; returned a bot challenge, not read): https://help.x.com/rules-and-policies/x-automation

**n8n docs** (fetched 2026-09-29)
- X node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.twitter.md
- X credentials: https://docs.n8n.io/integrations/builtin/credentials/twitter.md
- HTTP Request node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest.md
- HTTP Request credentials: https://docs.n8n.io/integrations/builtin/credentials/httprequest.md
- Custom API actions: https://docs.n8n.io/integrations/builtin/custom-api-actions-for-existing-nodes.md

**n8n source at `n8n@2.41.3`** (under https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/nodes-base/)
- `nodes/Twitter/Twitter.node.ts`
- `nodes/Twitter/V2/{TwitterV2.node,GenericFunctions,TweetDescription,UserDescription,DirectMessageDescription,ListDescription}.ts`
- `credentials/TwitterOAuth2Api.credentials.ts`

**ATS URL checks** (unauthenticated GETs, 2026-09-29)
- `api.ashbyhq.com/posting-api/job-board/n8n`
- `boards-api.greenhouse.io/v1/boards/{instacart,vercel}/jobs`
- `api.lever.co/v0/postings/spotify`
