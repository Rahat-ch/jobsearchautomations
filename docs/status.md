# Job Scout: status

Last updated: 2026-09-29. Phase: **research**. The spec and tickets come next, when Rahat invokes those skills.

## What Job Scout is

It rebuilds the backend of Hermes (Rahat's job-scout agent) on n8n:
- scan job boards on a schedule
- filter to real US-remote roles
- score each role against Rahat's resume with Claude
- dedupe across runs
- let Rahat triage
- learn from passes

The Hermes board design becomes the UI on top of it.

## Decisions made

| Area | Decision | Notes |
|---|---|---|
| Engine | n8n, self-hosted | Community Edition is free. Costs are only LLM API calls, estimated at about $0.01–0.015 per scored posting. |
| Hosting | Rahat's Coolify server | Always on, with public HTTPS so buttons and forms work from a phone. A local Docker instance exists for development. |
| UI | A board built from the Hermes design | Columns: New, Applied, Interviewing, Offer, Passed. Includes the pass-reason modal and the "Feedback to Hermes" panel. |
| Notifications | Telegram | Daily ping. The Telegram node supports "Send and wait for response". |
| Job boards | Ashby, Greenhouse, Lever | Scanned on a schedule. |
| Starting companies | n8n, PostHog, Ramp (Ashby); Instacart (Greenhouse); Palantir, Spotify (Lever) | Checked 2026-09-29: board names resolve and return jobs. |
| Comp floor | $180K base | |
| LLM | Claude, via n8n's Anthropic Chat Model node and Structured Output Parser | Research suggests the model returns sub-scores and code computes the total. Not decided yet. |
| Storage | n8n Data Tables | Holds leads, passes, and rules/config. Resume text is stored in n8n, not in the repo. |
| Extra | Instance-level MCP | Lets agents query the pipeline, for an "agents use this too" moment. Not researched yet. |

## Key findings (details in `research/job-scout-build.md`)

- **n8n 3.0 ships in October 2026.** It removes AI Agent v1, so build on current node versions.
- **Ashby's `isRemote` can't be trusted.** It was true on 140 of 155 Ramp jobs. Use `workplaceType` plus `secondaryLocations`. Hybrid roles with "Remote (US)" only in the secondary locations need extra checking.
- **Greenhouse had no structured pay data** in the Vercel sample, so pay must be parsed from the description. Lever's live `workplaceType` values (`onsite`) differ from its docs (`on-site`).
- **Slack in-app approvals and form links need public HTTPS.** Localhost won't work without a tunnel.
- **Missed scheduled runs are skipped by default.** The durable scheduler (`N8N_SCHEDULER_ENABLED` plus `N8N_USE_WORKFLOW_PUBLICATION_SERVICE`) can catch them up.
- **Template gallery:** new creators get one template in review at a time, sticky notes are mandatory, and personal identifiers must be removed.
- **n8n's own Senior Developer Advocate, US posting is on Ashby** (board `n8n`). That makes a natural first result in the demo.

## Open research (not done yet)

1. **Coolify deployment:** the n8n service template, persistent volume, public HTTPS, SQLite vs Postgres, and whether to turn on the durable scheduler.
2. **Serving the board:** can n8n webhooks serve the HTML page and a JSON API cleanly? Also auth and CORS. The alternative is a separate static site on Coolify.
3. **Telegram:** bot setup, how to capture the chat ID, message formatting limits, and how the pass form works on a phone.
4. **Instance-level MCP:** what it exposes and how an agent would query Job Scout.

## Open questions for Rahat

- **Hermes scope:** what does Mina do today beyond the feedback-loop spec (e.g. referral finding, outreach drafts)? This decides what n8n replaces.
- **Scoring:** fixed weights in code, or a total from the LLM?
- **Pass-reason codes:** which list is canonical? The seed data uses `role_too_backend` and `location_mismatch`, which aren't in the spec's table.
- **DFW hybrid:** does it count, and which metros (Dallas, Frisco, Plano, Irving, Fort Worth, Austin?)?
- **Resume:** which one is the scoring baseline, and are title keywords and exclusions per role family?
- **Video:** real postings or sample data?
- **Templates:** one n8n template or several?
