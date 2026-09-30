# Job Scout: scoring with TypeSafe's Jev

Research date: 2026-09-29. Sources: TypeSafe docs at docs.typesafe.ai, fetched as `.md` on 2026-09-29 (index, introduction, quick start, System One, how to build, state, primitives, Choice, Score, Noul, confidence, API reference, models, composite scoring, speculative fan-out, Jev 1.13 jaggedness, re-ranking, parallel questions, self-consistency and pre-parsed value extraction cookbooks, SDK pages, legal); the typesafe.ai home page; n8n docs fetched as `.md`; n8n source at tag `n8n@2.41.3` (`nodes-base/nodes/HttpRequest/V3/`, `nodes-base/credentials/`, `core/src/execution-engine/workflow-execute.ts`, `cli/src/modules/community-packages/`); the npm registry; n8n's vetted community node list; the n8n Template submission guidelines (Notion). No account, key, API call to TypeSafe, or workflow was made.

**Labels.** **[Doc]** means a primary doc states it. **[Source]** means I read it in n8n's source at `n8n@2.41.3`. **[Observed]** means I saw it live on 2026-09-29. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

This builds on `job-scout-build.md` section 2.2 (Claude with the Structured Output Parser, cost estimate) and section 2.7 (template gallery).

---

## 1. Summary and recommendation

- **Jev fits the scoring design almost exactly.** TypeSafe's own composite-scoring page uses resume screening as its example: several Score questions in one request, each normalized to 0–1, weights applied in code [Doc: patterns/composite-scoring]. Job Scout's plan (model judges sub-scores, code owns weights and the total) is the same pattern.
- **Jev returns judgments, not text.** It "does not write replies, produce code, or generate explanations of their reasoning" [Doc: concepts/system-one]. "Why it fits" prose and "who to contact and why" still need Claude, or a code template built from the sub-scores.
- **Cost:** $0.042 per million input tokens, output tokens free [Doc: models]. A lead with all questions in one request should cost roughly $0.0002, against the build doc's $0.01–0.015 for Claude [Inference, section 5].
- **Speed:** "Most queries complete in about 100 ms" [Doc: how-to-build]. Rate limits are 1,200 requests per minute and 250,000 tokens per second, but "can change without notice" [Doc: models].
- **n8n integration:** no official or n8n-vetted TypeSafe node exists. Ten third-party community packages appeared on npm between 2026-09-17 and 2026-09-22 [Observed]. Use the core HTTP Request node with a Bearer Auth credential.
- **Template cost of adding Jev:** a third credential (Telegram, Anthropic, TypeSafe). The gallery rules don't forbid this. They forbid hardcoded keys in the HTTP node and require a "self-hosted only" disclaimer for community nodes [Observed: Template submission guidelines]. The HTTP Request node avoids the second rule.
- **Recommendation [Opinion]:** a hybrid.
  - Jev scores every lead that survives the code filters: role family, stack, seniority, domain, location on messy text, and "is this X post a job".
  - Code applies the weights from the config node.
  - Claude runs only on leads that make the daily cap, to write "why it fits", and at pick time for contacts.
  - This shows n8n calling any API from one node, keeps the Anthropic node in the demo, and cuts Claude calls from every scored lead to the capped few.
  - Before committing, compare Jev and Claude sub-scores on the same leads during the Hermes parallel run.

---

## 2. What Jev is and the API contract

- **What it is:** "Jev is TypeSafe's flagship model and the first System One model" [Doc: introduction]. It evaluates typed questions against a state and returns typed answers and probabilities [Doc]. Its input is text only: a string, JSON object, or array [Doc: models].
- **Current model:** `jev-1.13.0`. Aliases `jev-latest` and `jev-preview` both point to it today [Doc: models]. "If you have tuned confidence thresholds against a specific version, pin that version's ID" [Doc: models].
- **Endpoint and auth** [Doc: api]:
  - `POST https://api.typesafe.ai/v1/systemone`
  - `Authorization: Bearer <API_KEY>`
  - `Content-Type: application/json`
  - Keys come from `console.typesafe.ai/keys` [Doc: quickstart].
- **Request body** [Doc: api]:
  - `state` (string, object or array, required)
  - `model` (required)
  - `questions`: a map from an ID you choose to a question. "The key is not sent to the underlying model", so each question must carry its full meaning [Doc: api; primitives].
- **Question fields:** every question has `type` (`noul`, `choice` or `score`) and `instructions` (string, object or array) [Doc: api].
  - **Noul:** `criteria` is optional, with `{true, false}` descriptions.
  - **Choice:** `criteria` is a map from option to description or `null`, with at most 255 options.
  - **Score:** `criteria` is an ordered array of levels. It "should have at least two levels; the API accepts up to 10."
- **Structured instructions:** an object can hold the question in one field and data in others, referenced by backticked name. State paths use the same syntax, e.g. `posting.location_text` [Doc: api; primitives].
- **Response** [Doc: api]:
  - Top level: `model` (the versioned ID that answered), `answers` keyed by your IDs, and `usage.input_tokens` / `usage.output_tokens`.
  - **Noul answer:** `noul` from 0 to 1. It has no confidence field.
  - **Choice answer:** `choice`, `probabilities` (summing to 1), `confidence`.
  - **Score answer:** `score` (probability-weighted and can fall between levels), `legend`, `probabilities` keyed by level index as a string, `confidence`.
- **Batching:** "Every *question* is evaluated in parallel and in isolation against the same *state*" [Doc: introduction]. The parallel-questions cookbook measured 13 questions in one call at $0.000497 and 0.27 s, against 13 separate calls at $0.006090 and 2.71 s, with the same answers [Doc: cookbooks/parallel_questions].
- **Limits per request:** no maximum number of questions is documented. The limits are context: "64k tokens per request; 32k tokens for `state` plus the longest question" [Doc: models].
- **Errors:** 401, 422 (validation), 429 (rate limit) and 529 (overloaded). The docs say to retry 429 and 529 with exponential backoff [Doc: api]. SDKs honor `retry-after` "when the response carries one" [Doc: models].
- **SDKs:** Python `typesafe-sdk` (default timeout 10 s, env var `TYPESAFE_API_KEY`) and JavaScript `@typesafe-ai/sdk` (Node 20+) [Doc: sdk pages; python constants]. In n8n the plain HTTP API is enough.
- **Data:** "Jev is not trained on customer requests or responses." Zero data retention is for enterprise customers [Doc: models; legal].

## 3. Which primitive fits each part of Job Scout

The docs' rule of thumb: Choice for one of a defined set, Score for a position on described levels, Noul for a yes/no condition [Doc: primitives]. The jaggedness page adds limits: keep arithmetic, counting and date comparison in code, and filter the state to what the question needs [Doc: model-jaggedness/jev-1.13].

| Job Scout piece | Who judges | Primitive | Note |
|---|---|---|---|
| Role family (25) | Jev | **Choice** over families (targets from config, plus off-target families and `other`) | Code maps the chosen family to points. The spec's off-target families: backend-only, data engineering, pure PM [Hermes spec]. |
| Stack fit (20) | Jev | **Score**, 4–5 levels of overlap with `profile.stack` | Add a Noul "does the posting name a stack?" so "no stack stated" isn't read as "no overlap". The Choice page recommends a no-match option when the list may not cover every input [Doc: choice]; a separate Noul is the same idea for a Score [Inference]. |
| Ownership/seniority (15) | Jev judges the posting's level, code judges fit | **Score** over described levels (associate → org lead) | [Inference] If Jev rates the posting, not the fit, changing the target level in config needs no new inference. |
| Domain fit (10) | Jev | **Score** of overlap with `profile.domains` | |
| Location (15) | Code first, Jev for messy text | **Choice** (`remote_us`, `remote_us_restricted`, `remote_outside_us`, `hybrid`, `onsite`, `unclear`) | Code checks the structured fields first (Ashby `workplaceType`, `secondaryLocations`). Jev reads the text when they disagree, e.g. Ramp's "Remote (US)" appearing only in secondary locations. The hybrid metro check stays in code. |
| Freshness (10) | Code | none | Jev "reads dates as text, not as ordered quantities" [Doc: jaggedness]. |
| Pay floor pass/fail | Code, with Jev only to pick a span | **Choice** over regex-found salary spans, plus `none` | This is the pre-parsed value extraction pattern: "A regex finds the candidate values, TypeSafe picks the one the question asks for" [Doc: cookbook]. Don't ask a Noul "is pay below $180K?"; "Jev is not a calculator" [Doc: jaggedness]. |
| Referral (5) | Code/manual | none | The proof of concept has no referral data [Inference]. |
| X post is a real job | Jev | **Noul** | Also a Choice or Nouls for location on the same post, in the same request. |

**Draft questions (untested, not run against Jev).** They follow the documented JSON shape. The state would be `{"profile": {...}, "posting": {"title", "company", "location_text", "secondary_locations", "workplace_type", "description"}}`, with the description trimmed of benefits and EEO boilerplate, because accuracy "falls as the state grows with content unrelated to the decision" [Doc: jaggedness].

```json
{
  "stack_fit": {
    "type": "score",
    "instructions": "How much of the technical stack that `posting.description` requires for this role overlaps with the technologies in `profile.stack`?",
    "criteria": [
      "None of the required languages, frameworks or platforms appear in the candidate's stack",
      "Only a secondary tool overlaps; the main language and framework are different",
      "Some core technologies overlap, but the main language or framework is not in the candidate's stack",
      "Most of the core languages and frameworks are in the candidate's stack",
      "The required stack is essentially the candidate's stack"
    ]
  },
  "names_stack": {
    "type": "noul",
    "instructions": "Does `posting.description` name specific languages, frameworks or platforms used in this role?"
  },
  "location_type": {
    "type": "choice",
    "instructions": "Where can the person hired for this role work, based on `posting.location_text`, `posting.secondary_locations`, `posting.workplace_type` and `posting.description`?",
    "criteria": {
      "remote_us": {"what": "Fully remote, open to people anywhere in the United States", "examples": ["Remote (US)", "Remote - United States"]},
      "remote_us_restricted": {"what": "Remote in the US, but only in some states, time zones or regions", "examples": ["Remote, US Eastern time zone only"]},
      "remote_outside_us": {"what": "Remote, but only outside the United States", "examples": ["Remote - EMEA"]},
      "hybrid": {"what": "Some days each week or month in a specific office"},
      "onsite": {"what": "Works from a specific office full time"},
      "unclear": {"what": "The posting does not say where the person can work"}
    }
  },
  "is_job_posting": {
    "type": "noul",
    "instructions": "Does `post.text` announce a specific open job that a reader could apply for?",
    "criteria": {
      "true": "Describes an open role at a named company, with a role title or a link to apply",
      "false": "Job-search advice, someone looking for work, commentary on hiring, a generic 'we're hiring' with no role, or a course or paid offer"
    }
  }
}
```

- The level and option objects with `what` / `examples` follow the documented structured-criteria form [Doc: score#structured-level-descriptions; how-to-build].
- `is_job_posting` runs in a separate request, with the X post as state [Inference].
- **[Inference]** Whether backticked paths work inside `criteria` (not only `instructions`) isn't documented. The drafts keep paths in `instructions`.
- The docs warn that Jev reads literally: "When you look at a wrong answer and find yourself explaining what you really meant, that explanation is the missing half of the instruction" [Doc: jaggedness]. Expect to revise these wordings after testing.

## 4. Composite scoring mapped to the config node

- The documented pattern: score each dimension independently, divide each score by its top level number (`len(criteria) - 1`) to get 0–1, and combine with weights in code [Doc: score; composite-scoring]. "When priorities shift, change a coefficient in your code rather than rewriting a prompt" [Doc: introduction].
- Mapping to Job Scout [Inference]:
  - The config node holds the weights (25/20/15/15/10/10/5), the profile summary, the target families with points per family, the target seniority, and the thresholds.
  - A Code node computes `points = weight × normalized sub-score` for each Jev sub-score, adds the code-computed location, freshness and referral points, and sums to 100.
  - Pay is a gate, not points, per the Hermes defaults.
- **Use the probabilities too, not just `score`.** "Different distributions can produce the same score" [Doc: score]. For thresholds the docs suggest acting, reviewing or not acting by confidence range [Doc: confidence]. Job Scout could tag a lead "needs review" in Telegram when a heavy sub-score has low confidence, instead of silently ranking it [Opinion].
- **Store the raw answers** (score, confidence, probabilities, model ID) in the leads Data Table. Reweighting then needs no new calls, and the parallel run can compare Jev with Claude [Inference].
- "Please do not use score outputs ... to compute the exact magnitude of a number between two levels" [Doc: jaggedness]. Using the score as a weighted position is fine; reading 2.4 as "2.4 years" is not.

## 5. Calling Jev from n8n

- **No TypeSafe node in n8n.** None appears in the docs sitemap, and `n8n.io/integrations/typesafe/` returns 404 [Observed]. n8n's vetted list (`https://api.n8n.io/api/community-nodes`, the URL `community-node-types-utils.ts` uses [Source]) has 1,732 entries and none match TypeSafe, Jev or SystemOne [Observed].
- **npm has ten unofficial packages** (e.g. `n8n-nodes-typesafe`, `@taifoon/n8n-nodes-typesafe`, `n8n-nodes-typesafe-ai`), all created 2026-09-17 to 2026-09-22. None is published by TypeSafe [Observed: npm registry]. **[Opinion]** Don't depend on them for a template.
- **Credential:** use the HTTP Request node's generic **Bearer Auth** credential. It sends the `Authorization` header, and its token field is a password field [Source: `HttpBearerAuth.credentials.ts`; Doc: HTTP Request credentials]. Header Auth with Name `Authorization` and Value `Bearer <key>` is equivalent [Doc].
- **Request:** POST, JSON body using an expression that builds `{state, model, questions}` from the lead and the config node. It runs once per input item, which means one request per lead with all questions [Doc: HTTP Request node; Inference]. Build the body in a Code node first, so the question definitions sit in one readable place.
- **Rate limiting:** set the HTTP Request option **Batching**. Items per Batch defaults to 50 and Batch Interval to 1000 ms [Source: `V3/Description.ts`]. Job Scout's daily volume is far below 1,200 requests per minute, so Loop Over Items isn't needed. n8n's docs say you "often don't need" it [Doc: Loop Over Items; Inference].
- **Errors:**
  - Turn on the node setting **Retry On Fail**. The engine clamps Max Tries to 2–5 (default 3) and Wait Between Tries to 0–5000 ms (default 1000) [Source: `workflow-execute.ts` `getRetryParams`].
  - On a 429 the node only rewrites the message to suggest batching. I found no `retry-after` handling in `HttpRequestV3.node.ts` [Source].
  - **[Inference]** A retry reruns the node for all items in that run, so a failure late in a batch re-pays for earlier items. The cost is trivial here.
  - Set **On Error → Continue (using error output)** [Doc: work-with-nodes]. Send failed leads to a branch that marks them `unscored` instead of failing the run. A 422 is a bad question definition, so don't retry it [Doc: api].
- **Mapping answers (sketch, untested):**

```js
// Code node, "Run Once for Each Item"
const cfg = $('Job Scout config').first().json;
const a = $json.answers;
const norm = (id, levels) => a[id].score / (levels - 1);
const pts = {
  role_family: cfg.familyPoints[a.role_family.choice] ?? 0,
  stack: cfg.weights.stack * (a.names_stack.noul > 0.5 ? norm('stack_fit', 5) : cfg.stackUnknownShare),
  domain: cfg.weights.domain * norm('domain_fit', 4),
};
return { json: { ...$json, pts, lowConfidence: a.stack_fit.confidence < cfg.reviewBelow } };
```

## 6. Pricing, rate limits, latency, cost comparison

- **Price:** "$42 / $0.042" per Btok / Mtok. "Charged per input token. Output tokens are free" [Doc: models]. The home page shows "$42 Per Billion input tokens" [Observed].
- **Free tier or credits:** not documented. The home page FAQ lists "Are these prices temporary or subsidized?", but the answer isn't in the static HTML [Unverified].
- **Rate limits:** "250,000 tokens per second / 1,200 requests per minute". The docs add: "Rate limits are adjusting dynamically ... can change without notice" [Doc: models].
- **Latency:**
  - "about 100 ms" for most queries [Doc: how-to-build].
  - The self-consistency cookbook measured a 111 ms mean for a 14-question call, against 1.1–13.9 s for the LLMs tested [Doc: cookbooks/consistency_noul_cookbook].
  - The parallel-questions cookbook measured 0.27 s for 13 questions over a 54,000-character article [Doc].
- **Per-lead cost [Inference]:**
  - Tokens: a profile summary (~300 tokens), a trimmed posting (~1.5–3k) and about 7 questions (~1.5k) come to about 3.5–5k input tokens.
  - At $0.042/Mtok that is about $0.00015–0.0002 per lead, roughly 50–100 times less than the build doc's $0.01–0.015 per lead for Claude Sonnet 5.5.
  - The smallest documented examples still report about 300 input tokens, so each request likely carries a fixed overhead [Doc: api examples; Inference].
- **Total cost [Inference]:** Claude isn't removed, only moved. With a daily cap of about 10, Claude writes about 10 short explanations a day, instead of scoring every lead that passes the filters.

## 7. What Jev does not do, and the split with Claude

- Jev is "not trained to generate text ... If you really need to generate text... there are other models for that" [Doc: jaggedness]. It is also "not a drop-in replacement" for a chat model [Doc: coding-agents].
- **Suits Jev [Inference]:**
  - The four judgment sub-scores
  - Location on messy text
  - Is this X post a real job
  - Picking the base-pay span from regex candidates
  - Later: classifying pass-reason free text into the spec's reason codes (a Choice)
- **Suits Claude:**
  - "Why it fits" text for Telegram
  - "Who to contact and why" at pick time
  - Anything that reads the full resume or writes to Rahat
- **Code alone:** a "why it fits" line assembled from the top sub-scores (e.g. "Role family: developer relations · Stack: most core tech overlaps · Remote US") is enough for the daily ping. Claude is then needed only at pick time [Opinion].
- Jev could later screen contact candidates found by other means (e.g. a Noul "does this person work on the team that hires for this role?"). Finding them is still someone else's job [Inference].

## 8. Template implications

- **Three credentials:** Telegram, Anthropic and TypeSafe (Bearer Auth). Section 2.7's rules don't limit third-party credentials. They say "Don't use hardcoded API keys in the HTTP node" [build doc 2.7]. The guidelines repeat this: "don't store credentials directly in the HTTP node" [Observed: Template submission guidelines].
- **Community nodes:** "If your template uses a community node, add: A disclaimer that it's self-hosted only. A workflow image at the top (since previews don't render)" [Observed: Template submission guidelines]. The HTTP Request node avoids this.
- **Friction [Opinion]:** each extra signup lowers the chance a forker runs the template. Options:
  1. Jev required.
  2. A config switch, `scorer: "jev" | "claude"`, with both branches in the workflow. This is heavier and makes the template harder to review.
  3. A Claude-only template, with Jev in the demo and a second template later. New creators can have only one template in review at a time [Observed: Creator hub; build doc 2.7].
- **Exported JSON** carries credential names and IDs, not secrets [build doc 2.6]. The sticky note must say where to get a TypeSafe key and how to pick a model version.
- **Version pinning [Opinion]:** use `jev-1.13.0` in the template so thresholds tuned for the demo don't move when `jev-latest` changes [Doc: models].

## 9. Recommendation for the demo [Opinion]

- **Go hybrid.** Rahat has used Jev before (the Jev Switchboard project, per Rahat), which makes it a credible choice to show on camera.
- **What the hybrid shows off:**
  - n8n calling any API from the HTTP Request node, with a credential.
  - Code owning the policy, with the weights in the config node.
  - The Anthropic node doing the writing.
  - "Right model for each job" is a clear one-line story for a DevRel video.
- **Risks:**
  - A young API: `jev-1.13`, rate limits that are still adjusting, and no official n8n node.
  - A third key for forkers.
  - Answer quality on Rahat's leads is untested.
  - A Jev-heavy demo shifts attention from n8n's own AI nodes. Keeping Claude visible limits that.
- **Test before committing:** during the Hermes parallel run, send the same 20–30 leads through both scorers. Compare the sub-scores with Hermes' and with Rahat's own triage, then decide. The docs say to "Start with conservative thresholds, test with your own data, and adjust" [Doc: confidence].

---

## Open questions for Rahat

1. Hybrid (Jev scores, Claude writes for capped leads), or Claude-only with Jev as a later variant?
2. Is a third credential in the public template acceptable, or should the template ship Claude-only?
3. Target role families for the Choice question, and points per family.
4. Target seniority level(s), for the seniority-distance calculation in code.
5. Does Rahat already have TypeSafe access or a relationship with TypeSafe that the video or template description should disclose? (No setup now.)
6. Referral points in the proof of concept: always 0, or a manual flag?
7. Where the daily ping's "why it fits" comes from: code-built from sub-scores, or Claude for each notified lead?

## Sources

- TypeSafe docs index: https://docs.typesafe.ai/llms.txt
- Introduction: https://docs.typesafe.ai/introduction.md · Quick start: https://docs.typesafe.ai/introduction/quickstart.md · Jev with coding agents: https://docs.typesafe.ai/introduction/coding-agents.md
- System One: https://docs.typesafe.ai/concepts/system-one.md · How to build: https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md · State: https://docs.typesafe.ai/concepts/state.md
- Primitives: https://docs.typesafe.ai/primitives.md · Choice: https://docs.typesafe.ai/primitives/choice.md · Score: https://docs.typesafe.ai/primitives/score.md · Noul: https://docs.typesafe.ai/primitives/noul.md · Advanced structure: https://docs.typesafe.ai/primitives/advanced.md
- Confidence: https://docs.typesafe.ai/confidence.md · API reference: https://docs.typesafe.ai/api.md · Models (price, limits, context): https://docs.typesafe.ai/models.md · Legal: https://docs.typesafe.ai/legal.md
- Composite scoring: https://docs.typesafe.ai/patterns/composite-scoring.md · Speculative fan-out: https://docs.typesafe.ai/patterns/fan-out.md
- Jev 1.13 jaggedness: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- Cookbooks: https://docs.typesafe.ai/cookbooks/rerank_typesafe.md · https://docs.typesafe.ai/cookbooks/parallel_questions.md · https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook.md · https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook.md
- SDKs: https://docs.typesafe.ai/sdk/python.md · https://docs.typesafe.ai/sdk/javascript.md · https://docs.typesafe.ai/sdk/python/api/constants.md
- TypeSafe home page (price banner, FAQ titles): https://typesafe.ai
- n8n HTTP Request node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest.md
- n8n HTTP Request credentials (Header Auth, Bearer Auth): https://docs.n8n.io/integrations/builtin/credentials/httprequest.md
- n8n Loop Over Items: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.splitinbatches.md · Node settings: https://docs.n8n.io/build/understand-workflows/workflow-components/work-with-nodes.md
- n8n verified community nodes: https://docs.n8n.io/integrations/community-nodes/installation-and-management/install-verified-community-nodes.md · vetted list: https://api.n8n.io/api/community-nodes
- n8n source `n8n@2.41.3`: `packages/nodes-base/nodes/HttpRequest/V3/{Description.ts,HttpRequestV3.node.ts}`, `packages/nodes-base/credentials/HttpBearerAuth.credentials.ts`, `packages/core/src/execution-engine/workflow-execute.ts`, `packages/cli/src/modules/community-packages/community-node-types-utils.ts`
- npm registry search: https://registry.npmjs.org/-/v1/search?text=n8n-nodes-typesafe
- n8n Creator hub: https://n8n.notion.site/n8n-Creator-hub-7bd2cbe0fce0449198ecb23ff4a2f76f · Template submission guidelines: https://n8n.notion.site/Template-submission-guidelines-9959894476734da3b402c90b124b1f77
- Hermes spec (local): `~/dev/hermes-job-board/feedback-loop-spec.md` (pass-reason codes, fit tooltip)
