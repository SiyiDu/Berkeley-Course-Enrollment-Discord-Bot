"""Acceptance demo for memory system."""

from __future__ import annotations

import os
from pathlib import Path

from engine.berkeley_engine.config import load_engine_config
from engine.berkeley_engine.services import AskRequest, AskService
from engine.berkeley_engine.store import EngineStore
from shared.db import Database

from .db import MemoryDB
from .flush import flush
from .ingest import ingest_message
from .search import search
from .utils import normalize_course_code
from .config import load_memory_config


def _print(label: str, ok: bool) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}")


def main() -> None:
    os.environ["MEMORY_CHUNK_SIZE"] = "2"
    os.environ["MEMORY_CHUNK_OVERLAP"] = "1"
    mem_config = load_memory_config()
    if not mem_config.enabled or mem_config.backend != "filesystem":
        print("Memory backend disabled; demo skipped.")
        return

    guild_id = "demo"
    channel_id = "chan-1"
    payloads = [
        {
            "platform": "discord",
            "workspace_id": guild_id,
            "channel_id": channel_id,
            "message_id": "demo-1",
            "author_id": "u1",
            "content": "Resource: https://example.com/virt101",
            "timestamp": "2026-01-25T10:00:00+00:00",
            "course_code": "VIRT101",
            "term": "2026-spring",
            "professor_name": "Mira Hale",
        },
        {
            "platform": "discord",
            "workspace_id": guild_id,
            "channel_id": channel_id,
            "message_id": "demo-2",
            "author_id": "u2",
            "content": "Check the virt101 notes site for labs",
            "timestamp": "2026-01-25T10:05:00+00:00",
            "course_code": "VIRT101",
            "term": "2026-spring",
            "professor_name": "Mira Hale",
        },
    ]

    for payload in payloads:
        ingest_message(payload)

    memory_db = MemoryDB(guild_id)
    scope = memory_db.get_channel_map(guild_id, channel_id) or {}
    scope_id = scope.get("scope_id", "global")
    course_code = normalize_course_code(payloads[0]["course_code"])
    memory_root = Path("memory") / "workspace" / f"guild_{guild_id}" / "courses" / course_code / "2026-spring"

    daily_file = memory_root / "daily" / "2026-01-25.md"
    chunk_files = list((memory_root / "chunks" / "2026-01-25").glob("chunk_*.md"))

    _print("daily write", daily_file.exists())
    _print("chunk creation", bool(chunk_files))

    bm25_results = search(guild_id, "course", scope_id, "example.com")
    _print("BM25 hit", len(bm25_results) > 0)

    vector_results = search(guild_id, "course", scope_id, "virt101 notes")
    _print("vector hit", len(vector_results) > 0)

    try:
        created = flush(guild_id, "course", scope_id)
        _print("flush output created", created > 0)
    except Exception:
        _print("flush output created", False)
        created = 0

    config = load_engine_config()
    db = Database(
        config.database_url,
        connect_timeout=config.db_connect_timeout,
        max_retries=config.db_max_retries,
        retry_backoff_sec=config.db_retry_backoff_sec,
    )
    store = EngineStore(db)
    store.init_db()
    proposals = store.list_proposals(status="proposed")
    _print("proposals created", len(proposals) > 0)

    if proposals:
        store.approve_proposal(proposals[0]["id"], None, approved_by="demo")

    ask = AskService(store, config)
    reply = ask.handle(
        AskRequest(
            query="virt101 resource",
            mode="knowledge",
            viewer_role="student",
            scope={"type": "course", "course_code": "VIRT101", "term": "2026-spring"},
            context={},
        )
    )
    _print("ask returns cards", len(reply.get("cards", [])) > 0)


if __name__ == "__main__":
    main()
