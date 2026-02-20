# Berkeley Knowledge Engine — Design Document

## 1) Overview
The Berkeley Knowledge Engine is a backend-first system that ingests Discord messages, distills them into auditable knowledge cards, and serves evidence-backed answers through a stable API. Web and Discord are thin clients; the engine is the single source of truth for processing, approvals, and retrieval.

Core pipeline:
1) **Ingest** messages (auth + whitelist) → store raw messages.
2) **Extract** proposals (rule-based + LLM-ready) → proposals table.
3) **Review** proposals → approved cards.
4) **Ask** API answers using only approved cards and evidence.

## 2) Components
- **engine/**: FastAPI + Postgres/MySQL (SQLite fallback), ingest, extraction, admin, ask.
- **discord_bot/**: Discord UI client; stores state in DB (recommended) and talks to engine over HTTP.
- **web/**: Static UI for `/ask` and `/admin`.
- **memory/**: Filesystem-first memory system (optional; can be disabled for stateless deployments).

## 3) API & Auth (Engine)
- Admin endpoints require `ADMIN_TOKEN`.
- Ingest accepts `X-CLIENT-ID` + `X-CLIENT-TOKEN` (legacy `X-BOT-TOKEN` supported).
- `/api/admin/login` returns admin token using username/password (`admin/admin` by default).

## 4) Data Model (Engine)
- `messages` stores raw Discord messages.
- `proposals` and `cards` track knowledge artifacts and approvals.
- `channel_map` maps Discord channels to course offerings.

### Channel Map (Extended)
- `scope_type`: `course | professor | global`
- `scope_id`: canonical scope id (offering_id / professor_id / `global`)

## 5) Course- and Professor-Scoped Memory System (Clawdbot-style)
**Goal:** Durable memory is filesystem-first. SQLite is only a derived index, rebuildable at any time. In stateless/cloud deployments, memory can be disabled.

### Canonical File Layout
```
memory/
  workspace/
    guild_<GUILD_ID>/
      courses/
        <COURSE_CODE>/
          <TERM>/
            MEMORY.md
            daily/
              YYYY-MM-DD.md
            chunks/
              YYYY-MM-DD/
                chunk_<start>_<end>.md
      professors/
        <PROFESSOR_ID or SLUG>/
          MEMORY.md
          daily/
            YYYY-MM-DD.md
          chunks/
      global/
        MEMORY.md
        daily/
```
Rules:
- Courses never share folders.
- Professors never store under course folders.
- Daily files are append-only.
- `MEMORY.md` is curated/rewritten.

### Derived Index (per guild)
SQLite location:
```
memory/data/guild_<GUILD_ID>.sqlite
```
Tables:
- `offerings(offering_id, course_code, term, section, professor_id, memory_root)`
- `professors(professor_id, name, aliases_json, memory_root)`
- `channel_map(guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, enabled)`
- `chunks(chunk_id, guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, day, start_message_id, end_message_id, start_ts, end_ts, authors_json, text, source_path, content_hash, created_at)`
- `chunks_fts(chunk_id, text)` (FTS5)
- `embeddings(chunk_id, content_hash, vector_json, model, created_at)`
- `memory_entries(entry_id, scope_type, scope_id, entry_type, title, body, source_chunk_ids_json, content_hash, created_at)`

### Ingest → Memory Write
On successful ingest:
1) Resolve scope (course/professor/global) using channel_map.
2) Append to `daily/YYYY-MM-DD.md` in the correct scope folder.
3) Buffer messages per channel.
4) Build chunks when buffer >= chunk_size.
5) Write chunk file and upsert into `chunks` and `chunks_fts`.
6) Embed chunk text and cache by content hash.

Ingest never fails due to embedding or indexing.

### Hybrid Retrieval (BM25 + Vector)
Two parallel paths:
- **BM25** (FTS5) → `textScore = 1 / (1 + max(0, bm25_rank))`
- **Vector** (cosine similarity)

Merged score:
```
finalScore = 0.7 * vectorScore + 0.3 * textScore
```
Scope filtering is mandatory (course/professor/global).

### Flush Mechanism
`memory.flush` produces durable facts in JSON-like schema and writes:
- `MEMORY.md` updates
- `memory_entries` rows
- proposals in engine DB (not auto-approved)

Flush is idempotent via content hash.

### Professor Knowledge Base Rules
Professor memory is just a different scope:
- Channels mapped to professor scope
- Course flush can also emit professor-scoped facts

## 6) CLIs
- `python -m memory.reindex --guild <id>`
- `python -m memory.search --guild <id> --scope course --scope-id <id> --query "..."`
- `python -m memory.flush --guild <id> --scope course --scope-id <id>`
- `python -m memory.demo_acceptance`

## 7) Definition of Done
- Every course has isolated memory folders.
- Professor knowledge is queryable independently.
- SQLite is fully rebuildable from disk.
- Ask answers cite approved cards derived from memory.
- Memory survives restarts/reindexing/flush.

## 8) Existing Features Recap
- Unified `/api/ask` with explicit scope + disambiguation.
- Admin review UI with login + extraction trigger.
- Discord bot auto-ingest + ask commands.
- Web `/ask` supports professor + course scoped queries.
