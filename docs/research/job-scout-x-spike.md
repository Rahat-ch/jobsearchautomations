# Job Scout: X search spike (issue #16)

Spike date: 2026-10-01. It ran six recent-search calls with Rahat's pay-per-use Bearer token to check the queries, the response shape and the cost before #16 is built. It made no n8n changes. Background research: `job-scout-x.md`.

**Labels.** **[Observed]** means I saw it in a live response on 2026-10-01. **[Doc]** means a primary doc states it. **[Hermes]** means Mina's saved output from a Hermes run on Rahat's machine. **[Inference]** and **[Opinion]** as in `job-scout-x.md`.

**What's not here.** No post text, names, handles or user IDs from the live results. The counts and URL shapes below are the findings; the fixtures use synthetic posts.

---

## 1. Summary

- **Mina's five queries work as written and fit the limit.** The longest is 464 of 512 characters. `docs/status.md` says "about 370"; it's 464.
- **Almost every result is a job-feed account, not the hiring company.** 17 of the 23 authors in the sample were job feeds or aggregators. No post was an X-only opening from the hiring company itself.
- **The ATS-link query had the best yield.** All 10 of its posts linked a posting on Ashby, which routes straight into the existing fetchers. The five buckets together produced 1 ATS link in 40 posts.
- **Cost matched $0.005 per unique post, and author expansions seemed free.** 50 posts came back, 47 unique. The prepaid balance fell by $0.23.
- **`/2/usage/tweets` didn't move.** It showed `project_usage` `"0"` before and after. Count reads in the workflow from `meta.result_count`.
- **Prefer `unwound_url`.** Shorteners resolve in `unwound_url` but not in `expanded_url`.
- **Lever site names are case-sensitive.** Keep them exactly as they appear in the URL.

---

## 2. Queries

### 2.1 Run in the spike

The five buckets are Mina's query strings, copied unchanged from the Hermes X scan script. The sixth is new.

| # | Name | Length | Query |
|---|---|---|---|
| 1 | `pm_devex_remote` | 464 | `(("product manager" OR "technical product manager" OR "senior product manager" OR "product lead" OR "group product manager" OR "platform product manager" OR "developer experience product") ("developer experience" OR DevEx OR "developer platform" OR devtools OR "developer tools" OR APIs OR SDK OR integrations OR "developer productivity" OR "AI developer") (hiring OR "we are hiring" OR opening OR apply)) (remote OR "remote US" OR "US remote") -is:retweet lang:en` |
| 2 | `pm_devex_dfw` | 455 | `(("product manager" OR "technical product manager" OR "senior product manager" OR "product lead" OR "group product manager" OR "platform product manager") ("developer experience" OR DevEx OR "developer platform" OR devtools OR APIs OR SDK OR integrations OR "developer productivity" OR "AI developer") (hiring OR opening OR apply)) (Dallas OR DFW OR Frisco OR Plano OR Irving OR Arlington OR Richardson OR Addison OR McKinney OR Texas) -is:retweet lang:en` |
| 3 | `fde_solutions` | 297 | `(("forward deployed engineer" OR "AI solutions engineer" OR "solutions architect" OR "solutions engineer" OR "field engineer" OR "customer engineer") (hiring OR "we are hiring" OR opening OR apply)) (remote OR "remote US" OR Texas OR Dallas OR DFW OR Frisco OR Plano OR Irving) -is:retweet lang:en` |
| 4 | `product_frontend` | 320 | `(("senior frontend engineer" OR "frontend engineer" OR "product engineer" OR "senior product engineer" OR "software engineer" OR "founding engineer") (React OR "Next.js" OR TypeScript OR "React Native" OR frontend OR AI) (hiring OR opening OR apply)) (remote OR "remote US" OR Texas OR Dallas OR DFW) -is:retweet lang:en` |
| 5 | `devrel` | 215 | `(("developer relations" OR DevRel OR "developer advocate" OR "developer experience" OR DevEx OR "partner engineer") (hiring OR opening OR apply)) (remote OR "remote US" OR Texas OR Dallas OR DFW) -is:retweet lang:en` |
| 6 | `ats_link` | 309 | `(url:"jobs.ashbyhq.com" OR url:"greenhouse.io" OR url:"jobs.lever.co") ("product manager" OR "developer relations" OR DevRel OR "developer advocate" OR "developer experience" OR "solutions engineer" OR "forward deployed" OR "product engineer" OR "frontend engineer" OR "founding engineer") -is:retweet lang:en` |

- **`url:`** is a "Tokenized match on URL (matches `url` or `expanded_url` fields)", and the docs' own example quotes a full URL: `url:"https://developer.x.com"` [Doc: Search operators]. The quoted host `url:"jobs.ashbyhq.com"` matched: all 10 posts linked `jobs.ashbyhq.com` through a `t.co` link [Observed].
- **Greenhouse and Lever are unconfirmed in this query.** No Greenhouse or Lever link was among the 10 newest results, so `url:"greenhouse.io"` and `url:"jobs.lever.co"` are still unconfirmed. Mina's last run did see both ATSes in X posts (section 4.2) [Hermes].
- **`-is:retweet`** is redundant since May 4, 2026, when keyword search stopped returning retweets [Doc: changelog]. It's kept for parity with Hermes.

### 2.2 Suggested refinements (not run)

**[Opinion]** These drafts haven't been run. Test them against Mina's strings before switching.

- **First-person hiring words.** Replace `(hiring OR "we are hiring" OR opening OR apply)` with first-person phrases. In the sample, "apply" and "hiring" matched every job feed's "Apply here" and "X is hiring". The ATS-link query still catches company and employee posts that link a posting, whatever their wording.
- **Shorter title lists.** A phrase matches inside longer text, so `"product manager"` already covers "senior", "technical", "group" and "platform product manager" [Inference]. Likewise, `"frontend engineer"` covers "senior frontend engineer" and `"solutions engineer"` covers "AI solutions engineer". Dropping the redundant titles saves the characters the new hiring phrases need.
- **Drop one hashtag.** Add `-#RemoteJobs`, a hashtag the job feeds in the sample used.

| Name | Length | Draft |
|---|---|---|
| `pm_devex_remote` | 389 | `("product manager" OR "product lead") ("developer experience" OR DevEx OR "developer platform" OR devtools OR "developer tools" OR APIs OR SDK OR integrations OR "developer productivity" OR "AI developer") ("we're hiring" OR "we are hiring" OR "I'm hiring" OR "my team is hiring" OR "join my team" OR "join our team") (remote OR "remote US" OR "US remote") -#RemoteJobs -is:retweet lang:en` |
| `pm_devex_dfw` | 454 | `("product manager" OR "product lead") ("developer experience" OR DevEx OR "developer platform" OR devtools OR "developer tools" OR APIs OR SDK OR integrations OR "developer productivity" OR "AI developer") ("we're hiring" OR "we are hiring" OR "I'm hiring" OR "my team is hiring" OR "join my team" OR "join our team") (Dallas OR DFW OR Frisco OR Plano OR Irving OR Arlington OR Richardson OR Addison OR McKinney OR Texas) -#RemoteJobs -is:retweet lang:en` |
| `fde_solutions` | 372 | `("forward deployed engineer" OR "AI solutions engineer" OR "solutions architect" OR "solutions engineer" OR "field engineer" OR "customer engineer") ("we're hiring" OR "we are hiring" OR "I'm hiring" OR "my team is hiring" OR "join my team" OR "join our team") (remote OR "remote US" OR Texas OR Dallas OR DFW OR Frisco OR Plano OR Irving) -#RemoteJobs -is:retweet lang:en` |
| `product_frontend` | 355 | `("frontend engineer" OR "product engineer" OR "software engineer" OR "founding engineer") (React OR "Next.js" OR TypeScript OR "React Native" OR frontend OR AI) ("we're hiring" OR "we are hiring" OR "I'm hiring" OR "my team is hiring" OR "join my team" OR "join our team") (remote OR "remote US" OR Texas OR Dallas OR DFW) -#RemoteJobs -is:retweet lang:en` |
| `devrel` | 309 | `("developer relations" OR DevRel OR "developer advocate" OR "developer experience" OR DevEx OR "partner engineer") ("we're hiring" OR "we are hiring" OR "I'm hiring" OR "my team is hiring" OR "join my team" OR "join our team") (remote OR "remote US" OR Texas OR Dallas OR DFW) -#RemoteJobs -is:retweet lang:en` |
| `ats_link` | 331 | `(url:"jobs.ashbyhq.com" OR url:"greenhouse.io" OR url:"lever.co") ("developer experience product" OR "technical product manager" OR "developer relations" OR DevRel OR "developer advocate" OR DevEx OR "solutions engineer" OR "forward deployed" OR "product engineer" OR "frontend engineer" OR "founding engineer") -is:retweet lang:en` |

**What the ATS-link draft changes:**
- **Narrower PM titles.** It swaps bare `"product manager"` for DevEx and technical PM titles. In the spike, 7 of the 10 ATS-linked posts were generic PM roles.
- **Broader Lever match.** It widens `url:"jobs.lever.co"` to `url:"lever.co"` so it would also match Lever's EU host `jobs.eu.lever.co` [Doc: Lever postings API README]. Whether the tokenized match works that way is [Unverified].

**Still to check before relying on the drafts:**
- How X tokenizes apostrophes in `"we're hiring"` and `"I'm hiring"` [Unverified].
- **Other ideas:**
  - Add a muted-authors list to the config for persistent job-feed accounts. Apply it in code, and as `-from:` terms where a query has room. Reads are billed before code can drop a post, so excluding in the query saves money.
  - Keep `pm_devex_dfw`. It returned nothing in the spike, and nothing in Mina's last 7-day run, but empty responses aren't billed ("Only successful responses that return data are billed") [Doc: Usage and Billing].

---

## 3. Response shape [Observed]

Request: `GET https://api.x.com/2/tweets/search/recent` with `max_results=10`, `tweet.fields=created_at,author_id,entities,lang`, `expansions=author_id` and `user.fields=username,name,description,verified`. All six calls returned HTTP 200.

```
{
  "data": [ Post, ... ],              // newest first
  "includes": { "users": [ User, ... ] },
  "meta": { "newest_id", "next_token", "oldest_id", "result_count" }
}
```

- **Post:** `author_id`, `created_at` (`2026-10-01T13:47:50.000Z`), `edit_history_tweet_ids` (returned without being requested, `[id]` for an unedited post), `entities` (only present when the post has any), `id` (string), `lang`, `text`.
- **`entities` keys seen:** `urls`, `mentions`, `hashtags`.
  - `mentions[]`: `start`, `end`, `username`, `id`. A mention is often the hiring company's account.
  - `hashtags[]`: `start`, `end`, `tag`.
- **`entities.urls[]`, two shapes:**
  - **Web link:** `url` (the `t.co` link), `expanded_url`, `display_url` (truncated with "…"), `start`, `end`, `unwound_url`, `status` (HTTP status of the final URL, 200), `title` (the page's HTML title, such as the job title on an Ashby page), `description`, and `images[]` (`url`, `width`, `height`). Every web link in the sample had `unwound_url`, `status` and `title`.
  - **Attached media or a link to another X post:** `url`, `expanded_url` (`https://x.com/{username}/status/{id}/photo/1` or `/video/1`), `display_url` (`pic.x.com/...`), `start`, `end`, and `media_key` (`3_{id}`) for media. There's no `unwound_url`, `status` or `title`. A link to another post looks like `https://twitter.com/{username}/status/{id}`, without `media_key`.
- **User** (in `includes.users`, one per author, deduplicated): `description`, `id`, `name`, `username`, `verified`. `verified` was false for every author. `verified_type` is the field that carries blue/business/government [Doc: user.fields enum].
- **`meta` with results:** `newest_id`, `next_token`, `oldest_id`, `result_count`. All five non-empty calls returned a `next_token`. `previous_token` didn't appear.
- **`meta` with no results:** the whole body is `{"meta": {"result_count": 0}}`. There's no `data`, `includes` or `newest_id`, so keep the stored `since_id` unchanged.
- **Headers:** `x-rate-limit-limit` (450), `x-rate-limit-remaining`, `x-rate-limit-reset` (epoch seconds) and `x-access-level` (`read`). No cost header.
- **Long posts:** `text` stops at about 280 characters (the longest in the sample was 308, counting `t.co` links). One multi-role post lost its later posting links in the cut, so its `entities.urls` held only the first two. The Post schema has a `note_post` field, "The full content of the Post, including text beyond 280 characters", with its own `entities` [Doc: Search Recent OpenAPI, `tweet.fields` enum]. **Recommendation:** request `tweet.fields=created_at,author_id,entities,lang,note_post` and read posting links from both `entities.urls` and `note_post.entities.urls`. That field wasn't requested in the spike, so its response key is [Unverified].
- **Duplicates across queries:** 3 of the 50 posts came back from two queries each. Deduplicate by post `id` before routing.

### 3.1 Usage endpoints [Observed]

- **`GET /2/usage/tweets`** with `days=3&usage.fields=daily_project_usage,project_cap,project_usage,cap_reset_day`:
  - It returned `{"data": {"cap_reset_day": 30, "daily_project_usage": {"project_id": "..."}, "project_cap": "3000000", "project_id": "...", "project_usage": "0"}}`.
  - Numbers came back as strings, and `daily_project_usage` had no per-day array, unlike the docs' example.
  - `project_usage` stayed `"0"` right after 50 reads, so it lags or doesn't cover pay-per-use reads [Inference].
- **`GET /2/usage/credits`** returned `{"data": {"free_balance", "free_grants": [], "prepaid_balance", "total_balance"}}` in USD.
- Neither call changed the balance.

---

## 4. What the queries found

### 4.1 This spike (10 newest posts per query, 2026-10-01)

| Query | Returned | Specific openings | Links an ATS posting | No posting link | Digest / list posts | Noise | From the hiring company |
|---|---|---|---|---|---|---|---|
| `pm_devex_remote` | 10 | 6 | 0 | 5 | 3 | 1 | 0 |
| `pm_devex_dfw` | 0 | – | – | – | – | – | – |
| `fde_solutions` | 10 | 9 | 0 | 2 | 0 | 1 | 0 |
| `product_frontend` | 10 | 8 (4 distinct roles) | 1 (Ashby) | 1 | 2 | 0 | 0 |
| `devrel` | 10 | 6 | 0 | 3 | 2 | 2 | 0 |
| `ats_link` | 10 | 10 | 10 (all Ashby) | 0 | 0 | 0 | 1 (an employee) |

- **"No posting link"** means the post had only an attached image, a link to another X post, or no link at all. Every one was a job-feed repost, typically an image card or "comment for the link", not the company's own post. None would make a good X-only lead.
- **Specific openings that link elsewhere** went to aggregator sites: job-board clones, remote-job feeds and a Telegram channel.
- **Authors (23 unique):**
  - 17 job feeds or aggregators
  - 1 person who curates openings at other companies
  - 1 employee of the hiring company
  - 1 news account
  - 3 unrelated people (an anecdote, a resume service and a general post)
  - No recruiters or founders appeared in this small sample.
- **Fit:**
  - Many openings were outside the location rules: Europe, India, Africa and San Francisco hybrid.
  - The `devrel` bucket matched "developer experience" engineering roles. No Developer Advocate title came back.
  - `product_frontend` returned one role five times, once per country.

### 4.2 Mina's last Hermes run (same five queries, 7-day window ending 2026-09-26, up to 100 per query) [Hermes]

- **Per query:** `pm_devex_remote` 10, `pm_devex_dfw` 0, `fde_solutions` 47, `product_frontend` 100 (the per-request maximum, so more existed), `devrel` 15. That's 164 unique posts.
- **Links:** 5 posts linked an ATS posting: 2 Greenhouse, 2 Lever, 1 Ashby. 61 had no external link.
- **Most common link hosts:** job-feed sites, chat-group invites, Telegram, Indeed, URL shorteners and LinkedIn.

### 4.3 What this means for #16 [Inference]

- **Merged leads come mainly from the ATS-link query.** They route into the fetchers with no Jev call for "is this real".
- **X-only leads will be rare, and Jev's "real opening" check matters.** Most no-link posts are job-feed reposts with no company link. A first-party post (a founder or manager saying "my team is hiring") is the case worth keeping.
- **The suggested-contact rule needs a guard.** A job-feed account isn't a useful contact. Jev or code should skip authors whose bio reads as a job feed.

---

## 5. Routing expanded URLs

Read `unwound_url`, falling back to `expanded_url`. In Mina's run, 28 of 145 web links had an `unwound_url` that differed from `expanded_url`, including shorteners that resolve elsewhere [Hermes]. In the spike, all 39 matched [Observed]. Skip any URL whose host is `x.com` or `twitter.com`.

| ATS | URL shapes seen in X posts | Pattern (board, job ID) | Notes |
|---|---|---|---|
| Ashby | `https://jobs.ashbyhq.com/{board}/{uuid}`, sometimes with `?utm_source=...&utm_medium=social&utm_campaign=post` or `?embed=js` [Observed] | `^https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})(?:/application)?/?(?:[?#]\|$)` | `/application` is the apply URL [Doc: Ashby posting API `applyUrl`]. Board names can contain a dot (a real board of the form `company.com` resolves on the posting API) [Observed]. The API accepted a board name in different case [Observed]. |
| Greenhouse | `https://job-boards.greenhouse.io/{token}/jobs/{id}` [Hermes] | `^https?://(?:job-boards\|boards)\.greenhouse\.io/([^/?#]+)/jobs/(\d+)/?(?:[?#]\|$)` | `boards.greenhouse.io/{token}/jobs/{id}` 301-redirects to `job-boards.` [Observed]. `boards.greenhouse.io/embed/job_app?for={token}&token={id}` also redirects; read `for` and `token` from the query. The board-list API accepted a token in different case [Observed]. |
| Lever | `https://jobs.lever.co/{site}/{uuid}`, sometimes with a trailing `/` [Hermes] | `^https?://jobs(?:\.eu)?\.lever\.co/([^/?#]+)/([0-9a-f-]{36})(?:/apply)?/?(?:[?#]\|$)` | `/apply` is the apply URL, and `jobs.eu.lever.co` is the EU host [Doc: Lever postings API README]. **Site names are case-sensitive:** a real site seen with a capital letter returned 200 from `api.lever.co/v0/postings/{site}` and 404 when lowercased [Observed]. Keep the site exactly as in the URL. |
| Ashby, job ID only | `https://{company}/careers?ashby_jid={uuid}` [Observed] | query parameter `ashby_jid` | No board in the URL. Ashby job IDs are UUIDs, so match against existing leads' Ashby job IDs; otherwise mark the post unrouted [Inference]. |
| Greenhouse, job ID only | `https://{company}/job/?gh_jid={id}` (Instacart's `absolute_url` has this form) [Observed via the Greenhouse API] | query parameter `gh_jid` | No board token in the URL. Match against existing leads' Greenhouse job IDs; otherwise unrouted [Inference]. |

- **Tested.** These patterns were run against every URL in the spike and the URL shapes above. They routed all 12 Ashby posting links and the one `ashby_jid` link, and left job-feed sites, Telegram and X media links unrouted.
- **Two cases deferred.** Greenhouse's EU host is not in the job board API docs, and `boards-api.eu.greenhouse.io` didn't resolve, so it's left out.

---

## 6. Cost [Observed]

- **Spend:** six search calls, 50 posts returned, 47 unique.
- **Prepaid balance:** fell by $0.23 between the before and after checks of `GET /2/usage/credits`.
  - That fits 47 × $0.005 = $0.235, so posts returned twice on the same UTC day were charged once.
  - 50 × $0.005 = $0.25 would be outside the rounding.
  - The 23 authors returned through `expansions=author_id` added no visible User: Read charge. At $0.010 each they would have added $0.23.
- **Monthly estimate** [Inference]:
  - Mina's 7-day run returned 164 unique posts, with one query capped at 100.
  - That's at least about 25 new posts a day, about $0.12 a day, or about $3.50 a month with `since_id`.
  - The $5 preset leaves little room if `product_frontend` keeps saturating. The refinements in 2.2 should cut job-feed volume.
- **Counting toward the spend cap:** count `meta.result_count` per call, times $0.005, in the `state` table. The usage endpoint lagged (section 3.1). Counting before deduplication overestimates slightly, which is the safe direction.

---

## 7. Fixtures

These are synthetic posts in the real response shape: field names, order and nesting, `includes.users` and `meta`. IDs, usernames, names, bios and text are invented. Posting links point at postings in the existing ATS fixtures where a test needs a merge.

| File | Post ID (suffix) | Case |
|---|---|---|
| `tests/fixtures/x-search-ats-links.json` (page 1, has `next_token`) | …110 | Employee links the n8n Ashby posting in `ashby-n8n.json`. Should merge into that lead. |
| | …109 | Recruiter links the Spotify Lever posting in `lever-spotify.json` with `/apply`. Should merge. |
| | …108 | Manager links a Greenhouse posting on a board outside the config (`exampleplatform`). Should become a new lead without changing the board list. |
| | …107 | Career-page link with `gh_jid=8053797`, the Instacart posting in `greenhouse-instacart.json`. Should merge by job ID. |
| | …106 | Job feed links an Ashby posting with UTM parameters on a board with a dot (`example.com`). Should become a new lead from a board outside the config. |
| | …105 | Founder links a career page with `ashby_jid` matching no lead. Unrouted. |
| `tests/fixtures/x-search-x-only.json` (last page, no `next_token`) | …104 | Founder's hiring post with no link. An X-only lead if Jev judges it a real opening. The author should be the first suggested contact. |
| | …103 | Job-feed image card, no posting link. An X-only candidate that Jev should judge, but the author isn't a useful contact. |
| | …102 | News about hiring, with an image. Noise. |
| | …101 | Job-feed digest linking a Telegram channel and another X post. Noise. |
| `tests/fixtures/x-search-empty.json` | | A query with no results: `{"meta": {"result_count": 0}}`. |

---

## 8. Sources

- X: Search Posts Recent API reference and its OpenAPI (`tweet.fields`, `user.fields` and `expansions` enums, `PostNotePost`): https://docs.x.com/x-api/posts/search-recent-posts.md
- X: Search operators (`url:`): https://docs.x.com/x-api/posts/search/integrate/operators.md
- X: Usage endpoints: https://docs.x.com/x-api/usage/introduction
- X: Usage and Billing (billing only for returned data, daily deduplication): https://docs.x.com/x-api/fundamentals/post-cap
- X: Changelog (retweets no longer returned in keyword search, May 4, 2026): https://docs.x.com/changelog
- Ashby public posting API (`jobUrl`, `applyUrl`, jobs page name): https://developers.ashbyhq.com/docs/public-job-posting-api
- Lever postings API README (`hostedUrl`, `applyUrl`, EU job site `jobs.eu.lever.co`): https://github.com/lever/postings-api
- Greenhouse job board API, checked with unauthenticated GETs on 2026-10-01: `boards-api.greenhouse.io/v1/boards/{vercel,instacart}/jobs`, plus redirects from `boards.greenhouse.io`
- Live calls on 2026-10-01: six `GET /2/tweets/search/recent`, two each of `GET /2/usage/tweets` and `GET /2/usage/credits`
- Hermes: Mina's X scan script and its saved output for the 7-day window ending 2026-09-26 (local, not in this repo)
