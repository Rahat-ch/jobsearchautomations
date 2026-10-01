# Job Scout: Find people spike

Spike date: 2026-10-01, for issue #14 (Find people and Search LinkedIn). I built a throwaway workflow on the local n8n 2.41.3 (Manual Trigger → Code with three leads → Anthropic "Message a Model" with Web Search → Code to parse), ran it four times with four prompt versions, and deleted it. Three real leads from `jobscout_leads` (read only): a DevRel role at a devtools company, an FDE/Solutions role and a senior PM role at a larger company. Posting text came from the public Ashby and Greenhouse job-board APIs.

**Labels.** **[Source]** means I read it in n8n's source at 2.41.3 (in the running container). **[Doc]** means a primary doc states it. **[Observed]** means I saw it in these runs. **[Inference]** and **[Opinion]** are my own reasoning or judgment.

**Personal data.** This file has no names, titles or profile links of the people found. Results are described in aggregate. The raw outputs are in Rahat's git-ignored `private/` notes.

Builds on `job-scout-outreach.md` section 4b (Claude web search in n8n) and section 6 (the pick flow).

---

## 1. Summary

- **It works, with care.** Across 12 calls and 30 suggestions, Claude never invented a person or a URL: every source and profile link it returned appeared in that call's own search results [Observed]. Every person I checked (29 of 30; one had only a surname initial) was real and had worked at the company. The failures are staleness and weak relevance, not fabrication.
- **Staleness is the main risk.** 3 of 30 suggestions (2 people) named someone in a role they no longer hold: one had left the company years ago and was found through undated speaker and blog bios; one had moved to another team at the same company. The final prompt (v4) adds rules against both and had no stale picks, but the reply must still show sources so Rahat can check.
- **Hiring managers are hard to find.** None of the three postings names a reports-to role, and no run found a real, current hiring manager for any lead. Recruiters are found reliably and, with function words in the query, for the right function (GTM, Solutions, Product). Team members turn up when a LinkedIn title or a company page matches the role.
- **Results vary run to run.** The same lead gave different people in each version; only a few people recurred. The first tap's result is what gets saved, so this is acceptable, but it means no single run is complete [Observed].
- **Cost and speed:** about $0.20 per tap with the final prompt (3 searches, Sonnet 5.5) and about 15 s per call on average [Observed]. The webhook must answer at once and send the Telegram reply when Claude is done.
- **Two node settings matter:** raise Maximum Number of Tokens from the default 1024 to 4096 (outputs reached 1,338 tokens, thinking included), and turn Simplify Output off to get `usage` and `stop_reason` [Observed; Source].
- **Parse defensively:** keep a contact only if one of its sources appears in the response's `web_search_tool_result` blocks or citations, and keep a profile link only if it matches the profile-URL pattern and was seen in results. Section 5 has the code shape.

---

## 2. Node settings that worked

Anthropic node `@n8n/n8n-nodes-langchain.anthropic`, typeVersion 1, credential "Job Scout Anthropic":

| Setting | Value | Why |
|---|---|---|
| Resource / Operation | Text / Message a Model | The only operation with web search [Source] |
| Model | `claude-sonnet-5-5` (By ID or list) | Same model as the fit line |
| Messages | one user message (the lead block below) | |
| Simplify Output | **off** | Raw output keeps `usage`, `stop_reason` and `content`. Simplified keeps only `content` [Source] |
| Options → System Message | the prompt in section 3 | |
| Options → Web Search | on | Sends `{type: "web_search_20250305", name: "web_search", max_uses, allowed_domains, blocked_domains}` [Source] |
| Options → Web Search Max Uses | an expression reading the config's search limit (3) | Every run used exactly 3 [Observed] |
| Options → Web Search Blocked Domains | `zoominfo.com, rocketreach.co, contactout.com, signalhire.com, lead411.com, apollo.io` | Keeps contact-data brokers (emails, phones) out of results and citations. Can't be combined with Allowed Domains [Source] |
| Options → Maximum Number of Tokens | **4096** | Default 1024 is too low: output tokens include thinking and reached 1,338 [Observed] |
| Temperature, Top P, Top K | leave unset | The node sends them only when set [Source]; Sonnet 5.5 rejects non-default sampling values [Doc: Anthropic's Claude API reference, model table] |

Facts from the node's source (`dist/nodes/vendors/Anthropic/actions/text/message.operation.js` at 2.41.3):

- It sends the basic `web_search_20250305` tool, not the newer `web_search_20260209` with dynamic filtering. Using the newer version would need the HTTP Request node [Source; Doc].
- No `thinking` parameter is sent, so Sonnet 5.5 runs adaptive thinking. Responses had `thinking` blocks between searches, empty by default [Observed].
- On `stop_reason: "pause_turn"` it appends the assistant content and resends, up to 3 times. It returns only the **last** response, so search results from before a pause are not in the output, and `usage` covers only the last request [Source]. No run paused [Observed], but the parser must handle it (section 5).
- Server-tool errors come back as HTTP 200 with a `web_search_tool_result` whose `content` is an error object, not a list [Doc]. The parser checks `Array.isArray`.

Response shape with Simplify off: `content` is a list of blocks: `server_tool_use` (query in `input.query`), `web_search_tool_result` (`content` is a list of `{url, title, page_age, encrypted_content}`), `thinking`, and `text`. The JSON answer is in the `text` block(s) after the last search result [Observed].

---

## 3. The prompt (final, v4)

User message (n8n expression; `reports_to` is the first posting sentence that matches `report(s|ing)? (directly )?(in)?to`, or empty):

```
Company: {{ company }}
Role: {{ title }}
Team: {{ team || 'not stated' }}
Location: {{ location }} ({{ workplace_type }})
Posting: {{ posting_url }}
Reports-to line from the posting: {{ reports_to || 'not stated' }}

Posting text (trimmed):
{{ description, first 3,000 characters }}
```

System message:

```
You find people at a company whom a job seeker could reach out to, by hand, about one job opening. You never contact anyone and never write messages to them.

Find up to 4 people who work at the company now, in this order of priority:
1. hiring_manager: the person this role most likely reports to. If the posting names the reports-to role, find whoever holds that role. Otherwise the head or manager of the team the role sits in.
2. team_member: someone on the same team doing similar work.
3. recruiter: a recruiter or talent partner at the company, ideally one who hires for this function.
4. other: anyone else at the company clearly tied to this role's team or work.

How to search (web_search, at most 3 searches, one at a time; read each result list before choosing the next query):
1. site:linkedin.com/in "<company>" plus the team or function words and head OR director OR manager OR lead. This often finds the hiring manager and team members at once.
2. Fill the most important empty slot. For a missing hiring manager, search the open web for the quoted company name plus the reports-to title. For a missing team member, search the role's title words; for developer-facing roles, the company's own blog authors, community or creator pages and GitHub often name team members.
3. site:linkedin.com/in "<company>" plus recruiter OR talent and the function (for example GTM, sales, product, engineering, marketing).
- If the company name is a short or common word, add a product or domain word so results are about this company.
- Job ads, job boards and reposted listings are not evidence of a person. Skip them.

How to judge a result:
- Proof that someone works at the company now is one of: a LinkedIn profile result titled "Name - Company" or "Name - Title at Company"; a page on the company's own website; or a dated source from the last 12 months. An undated or older third-party bio (speaker profile, dev.to, podcast or conference page) is not enough on its own.
- If the LinkedIn title names a different company, the person has left: leave them out. Leave someone out if the evidence says "former", "ex-" or "previously".
- If the company is advertising the hiring manager's own role (for example a "Head of Developer Relations" job ad), the seat may be empty. Don't name an earlier holder.
- Include a person only if a result you saw in this conversation shows their name together with the company. Put that result's URL in sources.

Output rules:
- Never invent or guess a name, title or URL. Never build a URL from a name. Copy each URL exactly as it appeared in a search result.
- title: the person's title as the source states it, with no commentary. If the source shows only the company, use "".
- links.linkedin: only a linkedin.com/in/ profile URL that appeared in your results for that exact person. The same for links.github (github.com/<user>) and links.x (x.com/<handle> or twitter.com/<handle>). Omit any link you did not see.
- Never include email addresses, phone numbers or home locations.
- An empty list is better than a guess. Fewer than 4 people is fine.
- why: one sentence, at most 25 words, tying this person to this specific role. Say plainly if the link to this team is a guess.

Reply with only a JSON object, with no prose before or after it and no code fences:
{"contacts":[{"name":"","title":"","role":"hiring_manager|team_member|recruiter|other","why":"","links":{"linkedin":"","github":"","x":""},"sources":[""]}],"notes":""}
Omit any link key you have no URL for. notes: one short sentence on what you could not find, or "".
```

For #14, add the contact count from config ("up to {{ findPeopleContactCount }} people") and, for a lead from a hiring post, the X author as the first candidate (spec #1, Action links). Neither was tested here.

### How the prompt evolved

| Version | Change | Effect [Observed] |
|---|---|---|
| v1 | Priority list, evidence rules, JSON only | Claude ran all 3 searches at once, in parallel, so it couldn't refine. 7 people, all real; 1 stale title; mostly adjacent teams; no hiring manager |
| v2 | Search one at a time; `site:linkedin.com/in` queries; how to read LinkedIn result titles; title copied from source | 8 people; strong for the two larger companies (a same-title team member, function-matched recruiters); poor for the devtools company, whose short name matched unrelated DevRel profiles. 1 stale hiring-manager pick repeated; 2 talent-team picks with conflicting evidence |
| v3 | One search per slot; hiring manager searched on the open web; blocked broker domains | 6 people. Open-web hiring-manager searches returned mostly job ads, and for the devtools company named a person who left years ago (undated speaker and blog bios). Found a recruiter who had shared this exact posting |
| v4 | LinkedIn first for manager and team at once; proof-of-current-employment rule; "if the manager's own role is advertised, the seat may be empty" | See section 4 |

Two behaviors held across versions:
- **Claude flagged its own doubts** in `why` and `notes` when told to ("the link to this team is a guess", "the source is undated"). Keep that instruction: it is what makes a stale or weak pick safe to show.
- **Sonnet 5.5 sometimes searches in parallel** even when told to search one at a time (one of nine sequential-prompt calls). Parallel is cheaper and faster but can't adapt.

---

## 4. Results by lead (aggregate, no names)

"Real" means an independent web search (not LinkedIn itself) confirmed the person and the company. "Current" means the title and company look current.

Final prompt (v4), one call per lead:

| Lead | Suggested | Real and at the company now | Slots filled | Notes |
|---|---|---|---|---|
| DevRel role, devtools company | 3 | 3 of 3 | recruiter (talent lead for GTM roles), 2 adjacent (product marketing, partnerships) | Hiring manager: Claude noticed the company is advertising the Head of DevRel role and named no one, as told. No DevRel teammate: the LinkedIn-first query missed the company's own creator page, which v1 and v3 used to find one |
| FDE/Solutions role, fintech | 3 | 3 of 3 | 2 recruiters on the GTM team, 1 sales leader | No hiring manager or same-title teammate found. v2 found a same-title teammate with a LinkedIn query on the exact title |
| Senior PM, larger company | 3 | 2 of 3 checked; 1 not checked (surname shown only as an initial) | team member (shared this exact posting), product recruiter, VP of Product | One title field broke the rule and held commentary ("title not stated in source"). The VP's title differs between LinkedIn and other sources |

V4 had no stale or wrong-company suggestions. It still found no hiring manager for any lead.

Across all four runs (30 suggestions over 12 calls):

- **Fabrication:** 0 invented people, 0 invented URLs. Every source and LinkedIn link was in the call's own search results [Observed].
- **Stale:** 3 suggestions, 2 people. One person left the company years ago (only undated third-party bios placed them there; Claude flagged the doubt but still named them); one had moved to another team at the same company and was offered twice as the likely hiring manager. V4's evidence rules target both.
- **Conflicting evidence:** 2 people (3 suggestions) whose LinkedIn result title said this company while an org-chart aggregator said another. One VP's title also differs between LinkedIn and other sources. These can't be settled without opening LinkedIn; the reply should show the source so Rahat checks by hand.
- **Claude's own "has left" calls aren't reliable either.** One run's `notes` said a recruiter had left; the next run included her, and she is current [Observed].
- **Relevance:** recruiters were the most reliable slot. With function words in the query (GTM, Solutions, Product), Claude found recruiters for the right function at both larger companies. Team members were good when a LinkedIn title matched the role. The hiring manager was the weakest slot.
- **Links:** LinkedIn profile links came back for nearly every person found through LinkedIn results. No GitHub or X link was found for anyone; GitHub would need its own search (or the `public_members` API from `job-scout-outreach.md` 4c) for devtools companies.
- **Page age is not a staleness signal for LinkedIn.** `page_age` on profile results ranged from days to over 11 years for people who are current [Observed]. Don't filter on it.

---

## 5. Parsing

Code node after the Anthropic node, one item per lead. The steps that worked:

1. **Collect seen URLs.** Walk `content`. From each `web_search_tool_result` whose `content` is an array, take every `url` (keep `page_age` and `title` too). From each `text` block, take every `citations[].url`.
2. **Find the answer text.** Join the `text` blocks after the last `web_search_tool_result`. Strip code fences. Parse from the first `{` to the last `}`. All 12 calls parsed on the first try [Observed].
3. **Normalize URLs before comparing:** `http` to `https`, drop query and fragment and trailing slashes, map country LinkedIn hosts (`es.linkedin.com`, `de.linkedin.com`) to `www.linkedin.com`, map `twitter.com` to `x.com`, lowercase. LinkedIn results often come back on a country host with a language suffix (`/in/<slug>/en`) [Observed].
4. **Keep a contact only if** it has a name and at least one source in the seen set. Cap at the configured count.
5. **Keep a profile link only if** it was seen and matches `linkedin.com/in/<slug>` (optionally `/<lang>`), `github.com/<user>` or `x.com/<handle>`. Store it rebuilt from the slug (`https://www.linkedin.com/in/<slug>`).
6. **If the response has no search results at all** (a `pause_turn` resend would cause this, since the node returns only the last response), don't drop everything silently: save nothing, reply "couldn't verify contacts, tap again", and leave the lead unsearched.
7. Never pass email or phone fields through, even if Claude returns them.

Schema the parser emits, one row per contact for the `contacts` table:

```
lead_key, name, title, role (hiring_manager|team_member|recruiter|other), why,
linkedin_url, github_url, x_url, source_urls (newline-joined), found_at
```

---

## 6. Cost and latency

Sonnet 5.5 at $2 / $10 per million input / output tokens [Doc: Anthropic's Claude API reference, model table], web search at $10 per 1,000 searches [Doc: Anthropic web search tool docs, via `job-scout-outreach.md`]. Search results count as input tokens [Doc].

| Run | Input tokens per call | Output tokens per call | Cost per call | Node time ÷ 3 calls |
|---|---|---|---|---|
| v1 (parallel searches) | 29K–33K | 950–1,270 | $0.10–0.11 | 9.8 s |
| v2 | 43K–57K | 710–1,340 | $0.13–0.15 | 15.4 s |
| v3 | 56K–93K | 810–1,190 | $0.15–0.23 | 13.6 s |
| v4 (final) | 76K–84K | 1,150–1,360 | $0.20–0.21 | 15.7 s |

- **Total spend for the spike:** 12 calls, 36 searches, about $1.89 [Observed: `usage` from each response, priced as above].
- **Per tap with the final prompt: about $0.20,** of which $0.03 is search fees and most of the rest is search results counted as input. The node ran the three leads one after another; per-call times weren't recorded separately, so the averages above are node time divided by three.

- **Parallel searching (v1) was cheapest and fastest:** about 31K input tokens and 10 s per call. Sequential searching re-reads earlier results on each turn, so input grew to 43K–93K tokens [Observed].
- **Thinking is part of output.** Output was 700–1,340 tokens per call, most of it thinking; the visible JSON is a few hundred tokens [Observed; Inference].
- **Second taps cost nothing** if the saved result is resent (spec), so the spend is once per picked lead.

---

## 7. Search LinkedIn link

Format (unofficial; LinkedIn documents no people-search URL, see `job-scout-outreach.md` section 3):

```
https://www.linkedin.com/search/results/people/?keywords=<encodeURIComponent(company + " " + terms)>
```

- Terms by role family, as tested: DevRel/DevEx → `developer relations`; FDE/Solutions → `solutions`; DevEx/Product PM → `product`; Product/Frontend Engineering → `engineering`. For example `?keywords=n8n%20developer%20relations`.
- Keep keywords short. LinkedIn's keyword search matches names, headlines and current companies, so company plus one function word gives a usable list [Inference].
- A filter to the company itself (`currentCompany=["<id>"]`) needs LinkedIn's numeric company ID, which Job Scout doesn't have. Skip it.
- The page needs a LinkedIn login. Whether the link opens the LinkedIn app or the in-app browser on Rahat's phone is still on the #15 smoke-test list. I didn't open the URL; nothing in this spike touched LinkedIn itself.

---

## 8. Failure modes

| Failure | Seen | Guard |
|---|---|---|
| Person left the company; old bio still says otherwise | 1 of 30 | v4 evidence rule; show sources; `why` names the doubt |
| Title or team out of date (moved inside the company) | 2 of 30 | Same; Rahat checks the profile before reaching out |
| LinkedIn title and an aggregator disagree | 3 of 30 | Show the source; can't be checked without opening LinkedIn |
| Short company name matches unrelated people (`site:` query for a 3-letter name) | 1 lead in v2 | Prompt: add a product or domain word |
| Hiring manager not found; the manager's own role is advertised | all 3 leads | Prompt: don't name an earlier holder; reply says "hiring manager not found" from `notes` |
| Only job ads in results | several searches | Prompt: job ads are not evidence |
| Search returns no results | 1 search | Nothing to do; the remaining searches fill other slots |
| Searches run in parallel despite the prompt | 1 of 9 calls |
| Title field holds commentary despite the rule | 2 of 30 | Acceptable; fewer refinements |
| `pause_turn` hides earlier search results | not seen | Parser step 6 |
| Output cut off at 1,024 tokens | would happen at the default | Max tokens 4096 |
| Contact-broker pages (emails, phones) as sources | not seen in Claude's results, but they rank high for a person's name in general web search | Blocked Domains |

---

## 9. Recommendations for #14

1. **Use the v4 prompt and the node settings in section 2**, with Max Uses and the contact count from config.
2. **Respond to the webhook first**, then run Claude. A call takes about 15 s; the Telegram reply follows.
3. **Get the posting text at tap time.** `jobscout_leads` has no description column [Observed]. Either refetch the one posting (Greenhouse has a per-job endpoint; Ashby and Lever return the board), or store a trimmed description or the reports-to line during the scan. Refetching avoids storing posting text for every lead [Opinion]. If the posting is gone (Closed), run with title and company only.
4. **Mark the search as done even when it finds no one.** "Later taps resend the saved contacts" needs a marker for the empty case, such as `people_found_at` on the lead, or the second tap searches again [Inference].
5. **Verify URLs in the parser** (section 5). It cost nothing here and is the guard that makes "never invent URLs" checkable.
6. **Show doubt in the reply.** Each contact line: name, title, role label, the `why` sentence, the LinkedIn link, and one source link. Then the `notes` line when it says what wasn't found.
7. **"Anyone Rahat already knows" can't come from web search.** Claude can't see Rahat's network. Leave it out of the prompt; if wanted later, match the company against a private list in n8n (like the `referrals` table) [Opinion].
8. **GitHub and X links didn't appear** with 3 searches. If they matter for devtools companies, add the GitHub `public_members` call from `job-scout-outreach.md` 4c as a separate, free step rather than spending a search [Opinion].
9. **Don't filter on `page_age`** for LinkedIn results (section 4).
