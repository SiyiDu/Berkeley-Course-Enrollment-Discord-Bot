# Discord Bot

The Discord bot is a client for the engine and can store its state in a database (recommended) or local JSON files for dev.
Use DB-backed storage in production to avoid local persistence.

Migrations for bot tables live in `discord_bot/migrations/<dialect>`.

## Install

```bash
pip install -r discord_bot/requirements.txt
```

## Run

```bash
python -m discord_bot.main
```

## Environment

```
BOT_TOKEN=your_discord_bot_token
ENGINE_BASE_URL=http://127.0.0.1:8000
CLIENT_ID=discord_bot
CLIENT_TOKEN=dev-client-token
BOT_INGEST_TOKEN=dev-bot-token
GUILD_ID=1234567890
STUDENT_ROLE_NAME=student
BERKELEY_SUFFIX=@berkeley.edu
PRIVATE_CONTAINERS=true
BOT_STORAGE_BACKEND=db
BOT_DATABASE_URL=postgresql://user:pass@host:5432/berkeley
```

For local-only dev, set `BOT_STORAGE_BACKEND=json` to use JSON files.

Note: message ingest and @bot mentions require Message Content Intent in the Discord developer portal.

Create a client token in the engine before running (or use legacy `BOT_INGEST_TOKEN`):

```bash
curl -X POST http://127.0.0.1:8000/api/admin/clients ^
  -H "Content-Type: application/json" ^
  -H "X-ADMIN-TOKEN: dev-admin-token" ^
  -d "{\"client_id\":\"discord_bot\",\"client_token\":\"dev-client-token\",\"name\":\"Discord bot\",\"allowed_platforms\":[\"discord\"]}"
```

## Ask Usage

Slash command:

```
/ask target:"CS61B" term:"2026-spring" question:"bucket sort 为什么快？"
```

Text prefix (mention):

```
CS61B 2026-spring | bucket sort 为什么快？
```
