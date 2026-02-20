# Engine (Knowledge Engine API)

The engine owns the database, ingestion, extraction, admin review, and `/api/ask`.

## Install

```bash
pip install -r engine/requirements.txt
```

## Run

```bash
python -m engine.berkeley_engine.api
```

The OpenAPI docs are at `http://127.0.0.1:8000/docs`.

The OpenAPI contract is exported to `engine/openapi.json` and treated as backward compatible.

Production guidance:
- Set `DATABASE_URL` to a managed Postgres/MySQL instance.
- Run `engine.berkeley_engine.worker` separately for job isolation.
- Disable memory (`MEMORY_BACKEND=disabled`) unless you mount persistent storage.

Regenerate:

```bash
python -m engine.berkeley_engine.export_openapi
```

## CLI

Reset DB (SQLite only):

```bash
python -m engine.berkeley_engine.reset_db
```

Seed demo data:

```bash
python -m engine.berkeley_engine.seed --guild-id 123 --channel-id 456 --course-code CS61B --term fa25 --section 001 --professor "Josh Hug"
```

Seed professor demo fixtures (experience + resource cards):

```bash
python -m engine.berkeley_engine.demo_fixtures
```

Run extraction (one-off CLI):

```bash
python -m engine.berkeley_engine.jobs
```

Run the background worker (recommended in production; set `ENGINE_RUN_JOBS_INLINE=false`):

```bash
python -m engine.berkeley_engine.worker
```

## Health & Admin

- `GET /api/health` returns `{status, db_ok, version, env}`.
- `GET /api/ready` checks database readiness.
- `GET /api/admin/jobs` lists extraction jobs.
- Admin endpoints require `ADMIN_TOKEN`; ingest requires client credentials (legacy `BOT_INGEST_TOKEN` still accepted).
- `POST /api/admin/login` accepts `{username,password}` and returns `{token}` (defaults: `admin/admin`).

## Integration

Ingest supports client credentials and a legacy token:

- Preferred: `X-CLIENT-ID` + `X-CLIENT-TOKEN`
- Legacy (deprecated): `X-BOT-TOKEN`

Create a client:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/clients ^
  -H "Content-Type: application/json" ^
  -H "X-ADMIN-TOKEN: dev-admin-token" ^
  -d "{\"client_id\":\"discord_bot\",\"client_token\":\"dev-client-token\",\"name\":\"Discord bot\",\"allowed_platforms\":[\"discord\"]}"
```

Ingest:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/message ^
  -H "Content-Type: application/json" ^
  -H "X-CLIENT-ID: discord_bot" ^
  -H "X-CLIENT-TOKEN: dev-client-token" ^
  -d "{\"platform\":\"discord\",\"workspace_id\":\"guild_1\",\"channel_id\":\"chan_1\",\"course_code\":\"CS61B\",\"term\":\"2026-spring\",\"section\":\"001\",\"professor_name\":\"Josh Hug\",\"message_id\":\"m1\",\"author_id\":\"u1\",\"content\":\"Example\",\"timestamp\":\"2025-01-01T00:00:00+00:00\"}"
```

Ask with explicit scope:

```bash
curl -X POST http://127.0.0.1:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"bucket sort 为什么快\",\"scope\":{\"type\":\"course\",\"course_code\":\"CS61B\",\"term\":\"2026-spring\"},\"mode\":\"auto\",\"viewer_role\":\"student\"}"
```

Common error codes:

- `401` invalid or missing credentials
- `403` platform/workspace not allowed
- `422` missing required ingest fields

## Client SDKs

Minimal clients are included for convenience:

- Python: `engine/engine_client.py`
- TypeScript: `engine/engine_client.ts`

## Scope & Disambiguation Contract

`/api/ask` accepts an optional `scope` object with resolution priority:

1) `offering_id` (canonical)
2) `course_code` + `term` (+ `section`)
3) `professor_id` or `professor_name`
4) `type=auto` (best-effort)

Response guarantees:

- Always returns `resolved_scope` when scope is determined.
- Returns `disambiguation: { needed: true, candidates: [...] }` when ambiguous.
- Clients must not guess; they should prompt the user to select a candidate and retry using `offering_id` or `professor_id`.

## Replay Demo

Run the end-to-end demo (engine must be running):

```bash
python -m engine.berkeley_engine.replay_demo
```

## Web UI Demo Checks

Seed fixtures and run lightweight API checks for the web professor flow (engine must be running):

```bash
python -m engine.berkeley_engine.demo_web_tests
```

## Acceptance Steps (Minimal)

1) Seed + whitelist:

```bash
python -m engine.berkeley_engine.seed --guild-id demo --channel-id demo-channel --course-code CS61B --term 2026-spring --section 001 --professor "Josh Hug"
```

2) Ingest a message (should return `stored=true`):

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/message ^
  -H "Content-Type: application/json" ^
  -H "X-BOT-TOKEN: dev-bot-token" ^
  -d "{\"platform\":\"discord\",\"workspace_id\":\"demo\",\"channel_id\":\"demo-channel\",\"message_id\":\"m1\",\"author_id\":\"u1\",\"content\":\"autograder tips\",\"timestamp\":\"2026-01-01T00:00:00+00:00\"}"
```

3) Extract proposals:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/jobs/extract ^
  -H "X-ADMIN-TOKEN: dev-admin-token"
```

4) Approve a proposal (use ID from `/api/admin/proposals`), then ask:

```bash
curl -X POST http://127.0.0.1:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"autograder tips\",\"scope\":{\"type\":\"course\",\"course_code\":\"CS61B\",\"term\":\"2026-spring\"}}"
```

Expected: `cards` non-empty and answer cites cards.

5) Ambiguous scope:

Create two offerings for the same course/term and ask with only `course_code` → expect `disambiguation.needed=true`.

## Migrations

Migrations live in `engine/berkeley_engine/migrations/<dialect>`. The engine applies them on startup and records applied IDs in `schema_migrations`.

## Data Model Guarantees

- Cards always include: `id`, `type`, `title`, `summary`, `tags`, `status`, `subject_type`, `subject_id`.
- Scope is represented as `subject_type` + `subject_id` (returned as `scope` in `/api/ask`).
- Evidence entries include `message_id`, `excerpt`, and `metadata`.
- Evidence excerpts are sanitized to remove Discord mentions/IDs.
- Experience cards do not expose raw excerpts to students (only aggregated strength metrics).

## Environment

```
DATABASE_URL=postgresql://user:pass@host:5432/berkeley
# or mysql://user:pass@host:3306/berkeley
DB_PATH=knowledge_engine.db
DB_CONNECT_TIMEOUT=5
DB_MAX_RETRIES=2
DB_RETRY_BACKOFF_SEC=0.3
BOT_INGEST_TOKEN=dev-bot-token
ADMIN_TOKEN=dev-admin-token
ENGINE_HOST=127.0.0.1
ENGINE_PORT=8000
ENGINE_SLICE_LIMIT=40
ENGINE_SLICE_MINUTES=60
ENGINE_ENV=dev
LLM_ENABLED=false
ENGINE_RUN_JOBS_INLINE=true
LOG_LEVEL=INFO
```


## Memory (Filesystem First)

Durable memory is stored on disk under `memory/workspace/guild_<id>/...` and indexed into `memory/data/guild_<id>.sqlite`.
Set `MEMORY_BACKEND=disabled` in production if you do not mount persistent storage.

CLIs:

```bash
python -m memory.reindex --guild <id>
python -m memory.search --guild <id> --scope course --scope-id <id> --query "..."
python -m memory.flush --guild <id> --scope course --scope-id <id>
```

Acceptance demo:

```bash
python -m memory.demo_acceptance
```
