# Job Scout on Coolify: deployment research

Research date: 2026-09-29. Sources: n8n docs (docs.n8n.io, fetched as `.md` on 2026-09-29), n8n source at tag `n8n@2.41.3` (commit `7f7a8ac`), Coolify source at tag `v4.3.23` (commit `e2e2d40`, released 2026-09-18, the latest Coolify release on 2026-09-29), Coolify docs source (`coollabsio/coolify-docs` at commit `c572cb7`, 2026-09-17, published at coolify.io/docs), Coolify's template CDN bundle, Traefik docs and source at branch `v3.6`, and Docker Hub tag metadata.

This builds on [job-scout-build.md](job-scout-build.md). Section 2.1 there covers versions and install options, section 2.3 covers webhook URLs behind a proxy, and section 2.5 covers the Schedule Trigger. None of that is repeated here.

**Labels.** **[Doc]** means a primary doc states it, cited inline. **[Source]** means I read it in source code at the tag named above. **[Observed]** means I saw it in a live response on 2026-09-29. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

Nothing here was built or deployed. No Coolify server or n8n instance was touched.

---

## 1. Summary and recommendation

- **Start from Coolify's plain `n8n` one-click template (SQLite plus a task-runner sidecar), then edit its compose before the first deploy.** The template pins n8n `2.10.2`, still sets the deprecated `WEBHOOK_URL`, and defaults the timezone to UTC (section 2.1).
- **Use SQLite, not Postgres.** One user and a few scheduled runs a day is a small workload. n8n Cloud's own Starter and Pro plans run on SQLite. There is an official path to Postgres later (`export:entities` / `import:entities`) (section 2.4).
- **Keep the `task-runners` sidecar.** It is n8n's recommended "external mode". Section 2.1 of the build doc says a single container is enough, but n8n now marks internal mode deprecated and not for production on instances holding secrets. Job Scout will hold an Anthropic key and a Telegram bot token (section 2.1).
- **Pin both images to the same version** (`n8nio/n8n:2.41.3` and `n8nio/runners:2.41.3`). n8n requires the two to match (section 2.6).
- **Turn on the durable scheduler.** It supports SQLite and single-instance mode, and n8n calls its Schedule Trigger support stable (section 2.5). [Opinion]
- **Back up the `n8n-data` volume** with Coolify's scheduled storage backup (Coolify v4.3.0+) to S3, with "stop containers" on, at a time when no scan runs. Also save the encryption key in a password manager (section 2.2).
- **HTTPS:** add an `A` record for a subdomain that points at the server, open ports 80 and 443, and set the n8n component's domain to `https://<subdomain>:5678`. Traefik gets a Let's Encrypt certificate over the HTTP-01 challenge (section 2.3).

**Recommended compose starting point. This is a recommendation, not built or tested.** It is Coolify's `templates/compose/n8n.yaml` at `v4.3.23` with the changes marked in comments:

```yaml
services:
  n8n:
    image: n8nio/n8n:2.41.3                      # was 2.10.2
    environment:
      - SERVICE_URL_N8N_5678
      - N8N_EDITOR_BASE_URL=${SERVICE_URL_N8N}
      - N8N_WEBHOOK_URL=${SERVICE_URL_N8N}/      # was WEBHOOK_URL (deprecated in 2.35.0)
      - N8N_HOST=${SERVICE_FQDN_N8N}
      - N8N_PROTOCOL=https
      - N8N_PROXY_HOPS=1
      - N8N_ENCRYPTION_KEY=${SERVICE_PASSWORD_ENCRYPTION}  # added; fresh volume only (see 2.2)
      - GENERIC_TIMEZONE=America/Chicago         # was UTC
      - TZ=America/Chicago                       # was UTC
      - DB_SQLITE_POOL_SIZE=2
      - N8N_RUNNERS_MODE=external                # N8N_RUNNERS_ENABLED removed (deprecated in 2.0)
      - N8N_RUNNERS_BROKER_LISTEN_ADDRESS=0.0.0.0
      - N8N_RUNNERS_BROKER_PORT=5679
      - N8N_RUNNERS_AUTH_TOKEN=${SERVICE_PASSWORD_N8N}
      - N8N_NATIVE_PYTHON_RUNNER=true
      - N8N_RUNNERS_MAX_CONCURRENCY=5
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=true
      - N8N_GIT_NODE_DISABLE_BARE_REPOS=true
      - N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
      - N8N_SKIP_AUTH_ON_OAUTH_CALLBACK=false
      - N8N_SCHEDULER_ENABLED=true               # added
      - N8N_USE_WORKFLOW_PUBLICATION_SERVICE=true  # added; already the default since 2.40.0
    volumes:
      - n8n-data:/home/node/.n8n
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:5678/healthz"]
      interval: 5s
      timeout: 20s
      retries: 10

  task-runners:
    image: n8nio/runners:2.41.3                  # must match the n8n tag
    environment:
      - N8N_RUNNERS_TASK_BROKER_URI=http://n8n:5679
      - N8N_RUNNERS_AUTH_TOKEN=${SERVICE_PASSWORD_N8N}
      - N8N_RUNNERS_AUTO_SHUTDOWN_TIMEOUT=15
      - N8N_RUNNERS_MAX_CONCURRENCY=5
    depends_on:
      - n8n
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:5680/healthz"]
      interval: 5s
      timeout: 20s
      retries: 10
```

---

## 2. Findings

### 2.1 Coolify's n8n templates

**Which exist.** There are three, at `templates/compose/` in Coolify `v4.3.23`, byte-identical on `main` on 2026-09-29 [Source]. Coolify's n8n docs page describes the same three [Doc: coolify.io/docs/services/n8n].

| Template file | Containers | n8n image |
|---|---|---|
| `n8n.yaml` | n8n (SQLite), task-runners | `n8nio/n8n:2.10.2`, `n8nio/runners:2.10.2` |
| `n8n-with-postgresql.yaml` | n8n, task-runners, `postgres:16-alpine` | `2.10.2` |
| `n8n-with-postgres-and-worker.yaml` | n8n main, n8n-worker (queue mode), `postgres:16-alpine`, `redis:6-alpine`, task-runners | `2.10.4` |

- Coolify loads templates at runtime from `https://cdn.coollabs.io/coolify/service-templates-latest.json`, not from the repo (`config/constants.php`) [Source]. That bundle shows the same image tags, with `template_last_updated_at` 2026-03-30 [Observed].
- "A one-click template is copied at resource creation. Coolify does not merge future template changes into the saved Service" [Doc: services/configuration/docker-compose].

**Env vars the templates set.** Taken from `n8n.yaml`. The Postgres variants add the `DB_*` vars. [Source]
- URLs:
  - `SERVICE_URL_N8N_5678` is a Coolify "magic" variable. It generates a domain for the `n8n` component and routes it to container port 5678.
  - `N8N_EDITOR_BASE_URL=${SERVICE_URL_N8N}`
  - `WEBHOOK_URL=${SERVICE_URL_N8N}`
  - `N8N_HOST=${SERVICE_FQDN_N8N}`
  - `N8N_PROTOCOL=https`
- Proxy: `N8N_PROXY_HOPS=${N8N_PROXY_HOPS:-1}`. This is set correctly.
- Timezone: `GENERIC_TIMEZONE` and `TZ` both default to `UTC`.
- SQLite: `DB_SQLITE_POOL_SIZE=${DB_SQLITE_POOL_SIZE:-2}`.
- Task runners:
  - `N8N_RUNNERS_ENABLED=true`
  - `N8N_RUNNERS_MODE=external`
  - broker listen address `0.0.0.0`, port `5679`
  - `N8N_RUNNERS_AUTH_TOKEN=${SERVICE_PASSWORD_N8N}`
  - `N8N_NATIVE_PYTHON_RUNNER=true`
  - `N8N_RUNNERS_MAX_CONCURRENCY=5`
- Hardening: `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`, `N8N_GIT_NODE_DISABLE_BARE_REPOS=true`, `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true`, `N8N_SKIP_AUTH_ON_OAUTH_CALLBACK=false`.
- Encryption key: `N8N_ENCRYPTION_KEY` is set only in the worker template (`${SERVICE_PASSWORD_ENCRYPTION}`). The SQLite and Postgres templates leave it unset, so n8n generates one into the volume.

**Magic variables** [Doc: services/configuration/docker-compose; Source: `bootstrap/helpers/parsers.php`]
- `SERVICE_URL_<SVC>` is a URL with scheme. `SERVICE_FQDN_<SVC>` is the host with no scheme.
- Declaring `SERVICE_URL_N8N_5678` makes Coolify create both base pairs without the port (`SERVICE_URL_N8N`, `SERVICE_FQDN_N8N`) and the port-suffixed pairs.
- `SERVICE_PASSWORD_<ID>` is a 32-character random value. `SERVICE_PASSWORD_64_<ID>` is 64 characters. Generated values "persist between deployments".
- Coolify manages the URL and FQDN variables from the component's **Domains** field.

**Outdated or wrong for n8n 2.41**
- The image is `2.10.2`. That is 31 minor versions behind 2.41.3 [Source; Observed].
- `WEBHOOK_URL` is "Deprecated from n8n 2.35.0; alias of `N8N_WEBHOOK_URL`. Still works, but n8n logs a deprecation warning" [Doc: endpoints env vars].
- `N8N_RUNNERS_ENABLED` is "Deprecated from n8n 2.0" [Doc: task-runners env vars]. It is harmless but can be removed.
- The two Postgres templates set `N8N_HOST=${SERVICE_URL_N8N}`. That puts a URL with a scheme where n8n expects a host name ("Host name n8n runs on" [Doc: deployment env vars]) [Source]. **[Inference]** It is likely masked because `N8N_EDITOR_BASE_URL` and `WEBHOOK_URL` are set. Fix it to `SERVICE_FQDN_N8N` if you use those templates.
- The worker template sets `OFFLOAD_MANUAL_EXECUTIONS_TO_WORKERS=true`, which n8n 3.0 removes [Doc: v3.0 breaking changes]. This doesn't matter for Job Scout.
- The `UTC` timezone default means Schedule Triggers fire on UTC unless each workflow overrides it (build doc 2.5).
- Coolify's n8n docs page still shows a Dockerfile example using `WEBHOOK_URL` and `n8nio/n8n:latest` [Doc: services/n8n].

**Task runners: keep the sidecar**
- "Always use task runners in production ... Without them, or with internal mode, anyone who can edit a workflow could potentially read your database, encryption key, stored credentials, and environment variables" [Doc: set-up-task-runners].
- `N8N_RUNNERS_MODE` defaults to `internal`, which is "**Deprecated**: internal mode will be removed in a future version" [Doc: task-runners env vars]. n8n logs a deprecation warning when the variable isn't set [Doc: set-up-task-runners].
- **[Inference]** The plain `docker run` in build doc 2.1, and the repo's local `docker-compose.yml`, run in internal mode. That is acceptable locally with test data. On Coolify, keep the template's external sidecar. Job Scout's Code nodes need a runner either way.

### 2.2 Persistent volumes and backups

**What's mounted**
- SQLite template: only `n8n-data:/home/node/.n8n` [Source]. That folder holds:
  - the `config` file with the encryption key
  - the SQLite database `database.sqlite`
  - filesystem-mode binary data
  
  Source: "With the default SQLite database, the `.n8n` folder holds everything needed to recover the instance" [Doc: backup-and-restore; Doc: choose-n8ns-database].
- **Data Tables live in the same database,** as real tables named `data_table_user_<id>` [Source: `packages/cli/src/modules/data-table/utils/sql-utils.ts`]. Backing up the database backs them up.

**How Coolify names volumes**
- The deployed name is `<service-uuid>_<slug-of-volume-name>`, for example `<uuid>_n8n-data` [Source: `serviceParser` in `bootstrap/helpers/parsers.php`]. The docs agree: "Coolify prefixes managed volume names ... Review **Show Deployable Compose** or **Persistent Storages** for the actual name" [Doc: services/configuration/persistent-storage].
- Volumes survive redeploys, restarts and **Stop**: "Stops and removes the component containers. Persistent volumes and the Service resource remain" [Doc: services/operations/overview].
- Deleting the Service offers "Permanently delete all volumes associated with this resource" [Doc: services/operations/danger-zone].
- **Editing the compose:** renaming the volume key or the compose service name changes the deployed name. "The container can start with an empty volume ... while the previous data remains elsewhere on the server" [Doc: persistent-storage]. **[Inference]** Keep the service name `n8n` and the volume name `n8n-data` unchanged across edits.

**Coolify backups**
- **Engine-aware database backups** (pg_dump, local or S3, with retention) cover PostgreSQL, MySQL, MariaDB, MongoDB and ClickHouse. That includes a Postgres container inside a Service, which Coolify reads through `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` [Doc: databases/backups]. SQLite isn't covered.
- **Scheduled storage (volume) backups** were added in Coolify v4.3.0 (2026-08-12, PR #10946). They write `.tar.gz` archives, locally and optionally to S3, with retention [Source: release notes v4.3.0].
  - Service support is present in the source: `app/Livewire/Project/Service/VolumeBackup/*` and the route `.../storage-backups`. Its first commit is an ancestor of v4.3.0 [Source].
  - The docs page still says the workflow "is available for application storage mounts" [Doc: storage-mounts/backups]. That page lags the source.
  - Option "Stop containers while creating the archive" gives a consistent copy, at the cost of a short outage [Doc: storage-mounts/backups]. n8n says: "With the default SQLite database, stop n8n before copying the `.n8n` folder" [Doc: backup-and-restore].
  - "Coolify does not restore storage archives from this page". Restoring is manual [Doc: storage-mounts/backups].
- **[Opinion]** Schedule a daily volume backup to S3 (for example Cloudflare R2) with stop-containers on, at an hour with no scan. Test one restore before relying on it.

**Encryption key**
- n8n generates the key on first launch and stores it in `~/.n8n/config`. `N8N_ENCRYPTION_KEY` is used only "if the key isn't yet in the settings file" [Doc: set-a-custom-encryption-key].
- If the env var and the file disagree, n8n refuses to start with "Mismatching encryption keys" [Source: `packages/core/src/instance-settings/instance-settings.ts`].
- **[Inference]** On a fresh Coolify volume, setting `N8N_ENCRYPTION_KEY=${SERVICE_PASSWORD_ENCRYPTION}` makes the key visible in Coolify's Environment Variables and stored in Coolify's database. Copy it to a password manager too. On an existing volume, read the key from `/home/node/.n8n/config` first and set exactly that value.
- n8n 3.0 turns on "Key rotation enabled by default" [Doc: v3.0 breaking changes]. Rotation keeps data keys in the database, protected by `N8N_ENCRYPTION_KEY`, and is "a one-way change" [Doc: rotate-encryption-keys]. The master key still has to be backed up.

### 2.3 Public HTTPS

- **Proxy:** Traefik is Coolify's default. Caddy is optional and "currently less documented" [Doc: networking/proxy/overview]. Coolify's Traefik is `traefik:v3.6`, with a `letsencrypt` resolver using the **HTTP-01 challenge** on the `http` entrypoint [Source: `bootstrap/helpers/proxy.php`].
- **DNS:** an `A` record (for example `jobscout`) pointing to the server's public IPv4 address. Add `AAAA` only if IPv6 works end to end [Doc: networking/dns].
  - "Ports `80` and `443` must reach the Coolify proxy" for certificate issuance [Doc: networking/domains].
  - For a server behind NAT with no open ports, Coolify documents Cloudflare Tunnels instead [Doc: integrations/networking/cloudflare/tunnels].
- **Domain field:** enter the full URL, and add the internal port when the process doesn't listen on 80: "use `https://app.example.com:3000` when the component listens on port `3000`. Visitors still use normal HTTPS" [Doc: services/configuration/general]. For n8n that means `https://jobscout.<domain>:5678`. `SERVICE_URL_N8N` and `SERVICE_FQDN_N8N` then pick up the new host, with no port [Source].
- **n8n's side:**
  - `N8N_WEBHOOK_URL` and `N8N_PROXY_HOPS=1` [Doc: reverse proxy; build doc 2.3].
  - `N8N_SECURE_COOKIE` defaults to `true`, which "ensures that cookies are only sent over HTTPS" [Doc; Source: `auth.config.ts`]. **[Inference]** An `http://…sslip.io` test domain that Coolify auto-generates will block login unless you switch to HTTPS or set it to false. Go straight to the real domain.
  - The editor's push channel is `N8N_PUSH_BACKEND`, default `websocket` [Doc: deployment env vars]. **[Inference]** Traefik proxies WebSocket upgrades without extra configuration, and I found no n8n doc listing a Traefik-specific problem.
- **Instance MCP (`/mcp-server/http`):** proxies must not strip the `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` headers [Doc: connect-to-n8n-mcp-server]. **[Inference]** Traefik forwards all headers by default, so no change is needed.
- **Gzip:** Coolify adds a Traefik `compress` middleware by default, with a per-component "Enable Gzip Compression" toggle [Source: `fqdnLabelsForTraefik`; Doc: services/configuration/general].
  - Traefik's compress handler implements `Flush` [Source: traefik `pkg/middlewares/compress/compression_handler.go` @ v3.6], and its default `excludedContentTypes` is empty [Doc: Traefik compress].
  - **[Unverified]** Whether SSE responses (MCP streaming) behave well through it. If streaming stalls, turn gzip off for the n8n component first.
- **[Inference]** If Cloudflare's orange-cloud proxy sits in front of Traefik, that adds a second hop. `N8N_PROXY_HOPS` would then be `2`. Use DNS-only (grey cloud) to keep it at 1.

### 2.4 SQLite vs Postgres

**What n8n says**
- SQLite is the default for self-hosted. n8n Cloud uses "**SQLite**: Starter, Pro, and legacy Enterprise plans" and Postgres only on "Enterprise Scaling" [Doc: choose-n8ns-database].
- Supported Postgres versions are 16, 17 and 18 [same page]. The Coolify templates' `postgres:16-alpine` is the oldest supported major.
- **SQLite mode:**
  - n8n 2.0 removed the legacy SQLite driver. "The pooling driver uses WAL mode, a single write connection, and a pool of read connections" [Doc: v2.0 breaking changes].
  - At 2.41.3, `DB_SQLITE_POOL_SIZE` defaults to `3` and must be ≥1, and WAL is always enabled [Source: `database.config.ts`, `db-connection-options.ts`].
  - The env-var docs page still says the default is `0` and uses rollback mode. That page is stale [Doc: database env vars]. The template's `2` is fine.
- **Data Tables** default to a 200 MiB limit per instance. `N8N_DATA_TABLES_MAX_SIZE_BYTES` raises it on self-hosted [Doc: data-tables; Source: `data-table.config.ts`]. The limit is the same on either backend.
- **Migration path:**
  - `n8n export:entities --outputDir=...` then `n8n import:entities --inputDir=... --truncateTables true`. It supports going "from one database type, such as SQLite, and import them into another database type, such as Postgres". The target DB "is expected to be empty" [Doc: use-the-command-line].
  - Executions are excluded unless you pass `--includeExecutionHistoryDataTables=true` [same].
  - **[Unverified]** Whether `export:entities` includes Data Table rows. Check in the source before relying on it.

**Trade-offs [Inference]**
- **SQLite:** one fewer container and less RAM. Backup is a file-level volume archive, which needs a brief stop to be consistent.
- **Postgres:** Coolify's pg_dump backups with no stop, and the data can be queried from outside n8n. The cost is an extra container, and the `.n8n` volume still needs backing up for the key.
- **Recommendation [Opinion]:** SQLite. Move to Postgres only if Job Scout's data needs to be read by something other than n8n.

### 2.5 Durable scheduler

- **What it does:** it stores each upcoming Schedule Trigger run in the database before it's due, so "a restart doesn't drop it". A run missed during downtime fires late if it's within its grace period (`N8N_SCHEDULER_MISFIRE_GRACE`, 60 s default). Beyond that, the node's **If Execution Is Missed** policy decides [Doc: durable-scheduler].
  - The policy options are: don't run (the default), run the most recent missed run, or run the most recent per rule.
  - The node option exists on Schedule Trigger nodes added from 2.36.0.
- **Flags:**
  - `N8N_SCHEDULER_ENABLED` defaults to `false` [Doc; Source: `scheduler.config.ts`].
  - The docs say to also set `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=true`. Without it, Schedule Triggers stay in memory [Doc].
  - In source, the publication service has **defaulted to `true` since n8n 2.40.0** (commit `0a6709f`, "Enable the workflow publication service by default") [Source: `workflows.config.ts`]. Setting it explicitly is harmless and matches the docs.
- **SQLite and single instance:**
  - Supported. The scheduler has SQLite migrations [Source: `packages/@n8n/db/src/migrations/sqlite/*Scheduler*`].
  - The env docs note "On SQLite, passes never overlap" [Doc: scheduler env vars].
  - Single-main mode needs no leader.
- **Maturity:** generally available from 2.36.0, and Preview from 2.32.0 [Doc]. "Poll trigger support isn't 100% stable yet ... This doesn't affect Schedule Trigger support, which is stable" [Doc: scheduler env vars]. Leave `N8N_SCHEDULER_POLL_TRIGGERS_ENABLED` off.
- **How often n8n restarts on Coolify:**
  - "Updating Coolify ... does not update the applications, databases, services" [Doc: instance-management/update]. Coolify does not auto-pull service images, and the restart policy is `unless-stopped` [Source: `constants.php`].
  - **[Inference]** Restarts come from Rahat's own deploys and env changes (which need a restart), server reboots, or crashes. With a pinned tag there are no surprise updates.
- **Worth it? [Opinion]** Yes, as a cheap safety net. Set **If Execution Is Missed = Run the Most Recent Missed Execution** on the daily scan, so an upgrade or reboot at scan time doesn't cost a day. It also gives the demo something to point at.

### 2.6 Version pinning and upgrades

- **Tag:** `n8nio/n8n:2.41.3` and `n8nio/runners:2.41.3`. Both exist on Docker Hub, and on 2026-09-29 `stable` and `latest` pointed to the same digests [Observed].
  - "The `n8nio/runners` image version must match that of the `n8nio/n8n` image" [Doc: set-up-task-runners].
  - Avoid `latest`. Coolify: "A mutable tag such as `latest` can change without showing which version will run, so pin production images" [Doc: services/configuration/docker-compose].
- **Upgrading on Coolify** [Doc: services/operations/update-service]:
  1. Run a volume backup.
  2. Open **Edit Compose File** and change both tags.
  3. Save, review the Deployable Compose, then deploy.
  
  **Pull Latest Images & Restart** only re-pulls the tags already saved. Template updates are never merged in, so compare by hand.
- n8n advises updating "at least once a month" and reading the release notes [Doc: update-n8n].
- **n8n 3.0 (October 2026)** [Doc: v3.0 breaking changes]:
  - Docker-only. Coolify already runs Docker, so there's no change there.
  - `N8N_RUNNERS_TASK_TIMEOUT` default drops from 300 s to 60 s. Set it explicitly if a Code node runs longer.
  - Key rotation turns on by default, and that change is one-way. Back up first.
  - `~/.n8n/binaryData` is renamed to `~/.n8n/storage`. **[Inference]** No action is needed, because the template mounts all of `.n8n`.
  - The Cron and Interval nodes and AI Agent v1 are removed.
  - **Settings > Migration Report** lists what affects the instance.
  - A database "only migrates forward". Rolling back after an upgrade means restoring the backup.
- **[Opinion]** Stay on 2.41.x through the demo recording. Take 3.0 at its first patch release, after a backup and a check of the Migration Report.

### 2.7 Resources

- n8n publishes no minimum RAM for n8n alone.
  - Its Hetzner guide says "For most usage levels, the CPX11 type is enough", and asks for 4 GB RAM / 2 vCPU only for n8n Assistant's Docker-in-Docker sandbox [Doc: llms-full, "Deploy to Hetzner"].
  - n8n's single-instance benchmark ran on a 4 GB c5a.large [Doc: measure-performance].
- The main memory drivers are large data, the Code node, and manual runs [Doc: fix-memory-issues].
- Coolify itself needs at least 2 CPU cores, 2 GB RAM and 10 GB disk, and "increase memory as your workload grows" [Doc: start-with-self-hosted].
- The one-line setup and Compose stack add a code sandbox that needs at least 4 GB RAM and 2 vCPU (build doc 2.1). Job Scout doesn't need it, and the Coolify templates don't include it [Source].
- **[Inference]** n8n plus the runner sidecar handling a few runs a day should fit alongside other apps on a typical 2–4 GB Coolify server. Check actual use in Coolify's metrics after the first week.

---

## 3. Open questions for Rahat

1. **Coolify version** on the server. Service volume backups need v4.3.0 or later.
2. **Server specs and other workloads**: RAM, vCPU, disk, and what else runs there.
3. **Domain**: which subdomain for Job Scout, and is DNS on Cloudflare (proxied or DNS-only)?
4. **Network**: is the server on a public IP with ports 80 and 443 open, or behind NAT (which would need a Cloudflare Tunnel)?
5. **Proxy**: does the server use Traefik (the default) or Caddy?
6. **Off-server backups**: is there an S3-compatible bucket (R2, B2, S3) to use, or should backups stay local?
7. **Local dev instance**: move its workflows to Coolify via export and import, or rebuild? Credentials would need the local encryption key or re-entry.
8. **Scan time**: what hour should the daily scan run in America/Chicago, so backups can be scheduled away from it?

---

## 4. Sources

**Coolify** (source at tag `v4.3.23`, commit `e2e2d4010bcd590084b66d6f748f3eec8e2bbee9`; docs source at `coollabsio/coolify-docs@c572cb7`)
- Templates:
  - https://github.com/coollabsio/coolify/blob/v4.3.23/templates/compose/n8n.yaml
  - https://github.com/coollabsio/coolify/blob/v4.3.23/templates/compose/n8n-with-postgresql.yaml
  - https://github.com/coollabsio/coolify/blob/v4.3.23/templates/compose/n8n-with-postgres-and-worker.yaml
- Template CDN bundle: https://cdn.coollabs.io/coolify/service-templates-latest.json
- Template source config: https://github.com/coollabsio/coolify/blob/v4.3.23/config/constants.php
- Service parser (magic vars, volume names): https://github.com/coollabsio/coolify/blob/v4.3.23/bootstrap/helpers/parsers.php
- Traefik config (ACME HTTP challenge): https://github.com/coollabsio/coolify/blob/v4.3.23/bootstrap/helpers/proxy.php
- Traefik labels (gzip): https://github.com/coollabsio/coolify/blob/v4.3.23/bootstrap/helpers/docker.php
- Restart mode: https://github.com/coollabsio/coolify/blob/v4.3.23/bootstrap/helpers/constants.php
- Service volume backups: https://github.com/coollabsio/coolify/tree/v4.3.23/app/Livewire/Project/Service/VolumeBackup
- v4.3.0 release notes: https://github.com/coollabsio/coolify/releases/tag/v4.3.0
- Docs:
  - n8n service: https://coolify.io/docs/services/n8n
  - Service Docker Compose (magic vars): https://coolify.io/docs/services/configuration/docker-compose
  - Service env vars: https://coolify.io/docs/services/configuration/environment-variables
  - Service persistent storage: https://coolify.io/docs/services/configuration/persistent-storage
  - Service general: https://coolify.io/docs/services/configuration/general
  - Service operations: https://coolify.io/docs/services/operations/overview
  - Update a Service: https://coolify.io/docs/services/operations/update-service
  - Danger zone: https://coolify.io/docs/services/operations/danger-zone
  - Storage backups: https://coolify.io/docs/core/persistent-storage/storage-mounts/backups
  - Database backups: https://coolify.io/docs/databases/backups
  - Domains: https://coolify.io/docs/core/networking/domains
  - DNS: https://coolify.io/docs/core/networking/dns
  - Proxy overview: https://coolify.io/docs/core/networking/proxy/overview
  - Cloudflare Tunnels: https://coolify.io/docs/integrations/networking/cloudflare/tunnels/all-resource
  - Update Coolify: https://coolify.io/docs/core/instance-management/update
  - Requirements: https://coolify.io/docs/start-with-self-hosted

**n8n** (docs fetched 2026-09-29; source at `n8n@2.41.3`, commit `7f7a8ac25b87db6c30e2b3651bb8c5d3b21cdb85`)
- Choose n8n's database: https://docs.n8n.io/deploy/host-n8n/configure-n8n/choose-n8ns-database.md
- Database env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/database.md
- Deployment env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/deployment.md
- Endpoints env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md
- Task runner env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/task-runners.md
- Set up task runners: https://docs.n8n.io/deploy/host-n8n/configure-n8n/set-up-task-runners.md
- Reverse proxy webhook URLs: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/configure-webhook-urls-with-reverse-proxy.md
- Custom encryption key: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/set-a-custom-encryption-key.md
- Rotate encryption keys: https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/rotate-encryption-keys.md
- Set up SSL: https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/set-up-ssl.md
- Durable scheduler: https://docs.n8n.io/deploy/host-n8n/configure-n8n/durable-scheduler.md
- Scheduler env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/scheduler.md
- Command line (export and import entities): https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line.md
- Back up and restore: https://docs.n8n.io/deploy/host-n8n/keep-n8n-running/backup-and-restore.md
- Update n8n: https://docs.n8n.io/deploy/host-n8n/keep-n8n-running/update-n8n.md
- Data tables: https://docs.n8n.io/build/work-with-data/data-tables.md
- Instance MCP server: https://docs.n8n.io/connect/connect-to-n8n-mcp-server.md
- Measure performance: https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/measure-performance.md
- Fix memory issues: https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/fix-memory-issues.md
- v3.0 breaking changes: https://docs.n8n.io/changelog/v30-breaking-changes.md
- v2.0 breaking changes: https://docs.n8n.io/changelog/v20-breaking-changes.md
- Full docs export (Hetzner guide): https://docs.n8n.io/llms-full.txt
- Source files:
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/config/src/configs/workflows.config.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/config/src/configs/scheduler.config.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/config/src/configs/database.config.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/config/src/configs/auth.config.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/config/src/configs/data-table.config.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/@n8n/db/src/connection/db-connection-options.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/cli/src/modules/data-table/utils/sql-utils.ts
  - https://github.com/n8n-io/n8n/blob/n8n@2.41.3/packages/core/src/instance-settings/instance-settings.ts
  - https://github.com/n8n-io/n8n/tree/n8n@2.41.3/packages/@n8n/db/src/migrations/sqlite
  - Publication service default commit: https://github.com/n8n-io/n8n/commit/0a6709fac9
- Docker Hub tags: https://hub.docker.com/v2/repositories/n8nio/n8n/tags/2.41.3, https://hub.docker.com/v2/repositories/n8nio/runners/tags/2.41.3

**Traefik**
- Compress middleware: https://github.com/traefik/traefik/blob/v3.6/docs/content/reference/routing-configuration/http/middlewares/compress.md
- Compress handler: https://github.com/traefik/traefik/blob/v3.6/pkg/middlewares/compress/compression_handler.go
