# jobsearchautomations

Rahat's home base for job-search work: automations, research, resumes, and applications.

The first project here is **Job Scout**, an n8n rebuild of Rahat's Hermes job-scout agent. It doubles as the portfolio piece for Rahat's n8n Senior Developer Advocate application.

## Current phase: build

Job Scout is built ticket by ticket from the spec ([issue #1](https://github.com/Rahat-ch/jobsearchautomations/issues/1)). Tickets are the open GitHub issues; `ready-for-agent` is agent work, `ready-for-human` is Rahat's setup or smoke tests.
- One branch per ticket. Merge, push and close only when Rahat says so.
- Leave the Job Scout workflow unpublished until Rahat publishes it; publishing starts the real daily schedule.
- Agent tickets edit one shared n8n workflow, so run them one at a time and never while Rahat is running a smoke test.

## Where things are

- `CONTEXT.md` (the glossary) and `docs/adr/`: read before naming anything or changing a decided design.
- `docs/status.md`: the decision log, including "Decisions for the spec" and "Lead lifecycle".
- `docs/research/`: primary-source research behind every external fact.
- `workflows/job-scout.json`: the repo copy of the n8n workflow. Regenerate it with `tools/export_workflow.py`, which scrubs the chat ID and refuses to write personal data.
- `tests/`: `python3 tests/run_tests.py` runs the workflow through MCP `test_workflow` with Telegram pinned and `jobscout_test_` tables. See `tests/README.md`.
- `tools/n8n_mcp.py`: calls any instance-MCP tool, including n8n's workflow-builder tools (`get_node_types`, `validate_workflow`, `update_workflow`).
- `.env` (git-ignored): secrets, the chat ID, dev keys (`N8N_API_KEY`, `N8N_MCP_TOKEN`) and the n8n settings compose reads. Load values in scripts; never print them.
- `docker-compose.yml`: n8n pinned to 2.41.3 plus a `cloudflared` named tunnel to the `jobscout` subdomain (`JOBSCOUT_HOST` in `.env`). The data volume `n8n-job-scout_n8n_data` holds the database, Data Tables and encryption key; backups go to `~/Backups/n8n-job-scout/`.
- Claude Code connects to instance MCP at the public host's `/mcp-server/http`, not localhost: n8n issues MCP OAuth tokens for its public URL.
- `private/`: git-ignored personal job-search notes (applications, contacts, resume paths).
- Hermes designs and spec (mockups, not a working app): `~/dev/hermes-job-board/`.

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
