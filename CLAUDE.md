# jobsearchautomations

Rahat's home base for job-search work: automations, research, resumes, and applications.

The first project here is **Job Scout**, an n8n rebuild of Rahat's Hermes job-scout agent. It doubles as the portfolio piece for Rahat's n8n Senior Developer Advocate application.

## Current phase: research. Do not build.

- Do not create workflows, tables, credentials, or app code until Rahat invokes the spec and ticket skills.
- Research, answer questions, and update docs only.
- Setup steps (API keys, bots, credentials) are also build work. Don't ask for them yet.

## Where things are

- `docs/research/job-scout-build.md`: primary-source research on n8n, the ATS job-board APIs, human-in-the-loop, Data Tables, the template gallery, and the demo video.
- `docs/status.md`: decisions made, open research, and open questions.
- `private/`: git-ignored personal job-search notes (applications, contacts, resume paths). Never commit it.
- `docker-compose.yml`: local n8n (2.41.3, Community Edition, registered license) at http://localhost:5678. Compose project name is pinned to `n8n-job-scout` so the data volume survives folder renames.
- Hermes designs and spec (mockups, not a working app): `~/dev/hermes-job-board/`. Covers `feedback-loop-spec.md`, `seed-data.json` (sample data only), and the `*.dc.html` board and modal mockups.

## Rules

- **This repo is public.** Never commit resume text, a phone number, email, API keys, bot tokens, or chat IDs. Personal data goes in `private/` or in n8n itself.
- **Plain writing.** No rhetorical flourishes ("is the job, not a chore"). State things directly.
- **Never invent facts.** Use only what's in Rahat's resumes, repos, or what Rahat says. For anecdotes or "scars," ask; don't fill them in.
- **Cite research to primary sources:** official docs, source code, first-party APIs.
- **Tailored resumes** live in `~/Desktop/resumes/<company>/` as HTML, rendered to PDF with headless Chrome (`--print-to-pdf --no-pdf-header-footer`). The general base is `~/Desktop/resumes/general/Rahat Chowdhury Resume 2026.html`.
- Use they/them for Rahat in docs.

## Agent skills

### Issue tracker

Specs and tickets are GitHub issues on this repo, managed with `gh`. The repo is public. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
