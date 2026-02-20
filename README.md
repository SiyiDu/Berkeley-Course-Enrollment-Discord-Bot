# Berkeley Knowledge Engine

This repo is split into three independently runnable modules:

- `engine/`: Knowledge Engine API (source of truth)
- `discord_bot/`: Discord bot client that only talks to the engine over HTTP
- `web/`: Static web UI (`/ask` + `/admin`)

## Quickstart (End-to-End)

Copy `.env.example` to `.env` and fill in secrets (never commit `.env`).

1) Start the engine (SQLite fallback for local dev; use `DATABASE_URL` for Postgres/MySQL in production):

```bash
pip install -r engine/requirements.txt
python -m engine.berkeley_engine.api
```

2) Seed demo data:

```bash
python -m engine.berkeley_engine.seed --guild-id 123 --channel-id 456 --course-code CS61B --term fa25 --section 001 --professor "Josh Hug"
```

3) Run the Discord bot (use DB-backed storage in production):

```bash
pip install -r discord_bot/requirements.txt
curl -X POST http://127.0.0.1:8000/api/admin/clients ^
  -H "Content-Type: application/json" ^
  -H "X-ADMIN-TOKEN: dev-admin-token" ^
  -d "{\"client_id\":\"discord_bot\",\"client_token\":\"dev-client-token\",\"name\":\"Discord bot\",\"allowed_platforms\":[\"discord\"]}"
python -m discord_bot.main
```

4) Open the web UI (static):

```bash
python -m http.server 5173 --directory web
```

Then visit `http://127.0.0.1:5173/ask` and `http://127.0.0.1:5173/admin`.

Background jobs run in a separate worker (recommended in production):

```bash
python -m engine.berkeley_engine.worker
```

## Verify the Flow

1) Send a message in a whitelisted Discord channel (or use `/api/ingest/message`).
2) Run extraction: `python -m engine.berkeley_engine.jobs`
3) Approve a proposal via `/admin` or `POST /api/admin/proposals/{id}/approve`
4) Ask via `/ask` or `POST /api/ask`

## Module Docs

See per-module instructions:

- `engine/README.md`
- `discord_bot/README.md`
- `web/README.md`

## Containers

Build/run locally with Docker Compose:

```bash
docker compose up --build
```
