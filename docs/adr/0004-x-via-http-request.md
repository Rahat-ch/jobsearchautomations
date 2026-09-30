# Read X with the HTTP Request node and a Bearer token, not n8n's X node

At n8n 2.41.3 the built-in X node's search returns only post data. It drops the author and paging fields and has no `expansions` or `since_id` inputs. Its only credential is a user login that always requests `dm.write`, `like.write` and `follows.write`. Job Scout calls X's recent-search API through the HTTP Request node with a Bearer token instead. That keeps authors and incremental paging, and a Bearer token cannot send DMs, which enforces ADR 0001. Research: `docs/research/job-scout-x.md`.
