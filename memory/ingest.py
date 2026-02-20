"""Ingest messages into filesystem memory and derived index."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_memory_config
from .db import MemoryDB
from .embed import embed
from .fs import append_daily, ensure_scope_dirs, scope_root, write_chunk
from .utils import slugify
from .utils import normalize_course_code, sha256_text, utcnow_iso


def _day_from_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date().isoformat()


def _format_line(message: dict[str, Any]) -> str:
    ts = message.get("timestamp") or message.get("ts")
    author = message.get("author_id")
    content = message.get("content")
    message_id = message.get("message_id")
    return f"[{ts}] ({message_id}) {author}: {content}"


def _catalog_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    catalog = payload.get("catalog") or {}
    return {
        "course_code": payload.get("course_code") or catalog.get("course_code"),
        "term": payload.get("term") or catalog.get("term"),
        "section": payload.get("section") or catalog.get("section"),
        "professor_name": payload.get("professor_name") or catalog.get("professor_name"),
        "professor_id": payload.get("professor_id") or catalog.get("professor_id"),
        "offering_id": payload.get("offering_id") or catalog.get("offering_id"),
    }


def _resolve_scope(db: MemoryDB, guild_id: str, channel_id: str, catalog: dict[str, Any]) -> dict[str, Any]:
    existing = db.get_channel_map(guild_id, channel_id)
    if existing:
        return existing

    scope_type = "global"
    scope_id = "global"
    offering_id = None
    professor_id = None

    course_code = catalog.get("course_code")
    term = catalog.get("term")
    section = catalog.get("section")
    professor_name = catalog.get("professor_name")

    if professor_name:
        memory_root = f"professors/{slugify(professor_name)}"
        professor_id = db.upsert_professor(professor_name, memory_root)

    if course_code:
        course_code = normalize_course_code(course_code)
        memory_root = f"courses/{course_code}/{term}" if term else f"courses/{course_code}"
        offering_id = db.upsert_offering(course_code, term, section, professor_id, memory_root)
        scope_type = "course"
        scope_id = str(offering_id)

    elif professor_id:
        scope_type = "professor"
        scope_id = str(professor_id)

    db.upsert_channel_map(
        guild_id=guild_id,
        channel_id=channel_id,
        scope_type=scope_type,
        scope_id=scope_id,
        offering_id=offering_id,
        professor_id=professor_id,
        enabled=True,
    )

    return db.get_channel_map(guild_id, channel_id) or {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "offering_id": offering_id,
        "professor_id": professor_id,
        "enabled": 1,
    }


def _create_chunk(db: MemoryDB, config, root, day: str, scope_map: dict[str, Any], batch: list[dict[str, Any]]) -> None:
    start = batch[0]
    end = batch[-1]
    chunk_id = uuid4().hex
    authors = sorted({msg['author_id'] for msg in batch})
    lines = [f"[{msg['ts']}] ({msg['message_id']}) {msg['author_id']}: {msg['content']}" for msg in batch]
    text = "\n".join(lines)
    content_hash = sha256_text(text)

    header = {
        "chunk_id": chunk_id,
        "guild_id": scope_map.get("guild_id"),
        "channel_id": scope_map.get("channel_id"),
        "scope_type": scope_map.get("scope_type"),
        "scope_id": scope_map.get("scope_id"),
        "offering_id": str(scope_map.get("offering_id") or ""),
        "professor_id": str(scope_map.get("professor_id") or ""),
        "start_message_id": str(start["message_id"]),
        "end_message_id": str(end["message_id"]),
        "start_ts": str(start["ts"]),
        "end_ts": str(end["ts"]),
        "authors": ",".join(authors),
    }

    chunk_path = write_chunk(root, day, chunk_id, header, lines)

    db.insert_chunk(
        {
            "chunk_id": chunk_id,
            "guild_id": scope_map.get("guild_id"),
            "channel_id": scope_map.get("channel_id"),
            "scope_type": scope_map.get("scope_type"),
            "scope_id": scope_map.get("scope_id"),
            "offering_id": scope_map.get("offering_id"),
            "professor_id": scope_map.get("professor_id"),
            "day": day,
            "start_message_id": str(start["message_id"]),
            "end_message_id": str(end["message_id"]),
            "start_ts": str(start["ts"]),
            "end_ts": str(end["ts"]),
            "authors": authors,
            "text": text,
            "source_path": str(chunk_path.relative_to(config.root)),
            "content_hash": content_hash,
            "created_at": utcnow_iso(),
        }
    )

    vector = embed(text, config.embed_dim)
    db.upsert_embedding(chunk_id, content_hash, json.dumps(vector), "hash-embed-v1")


def ingest_message(payload: dict[str, Any]) -> None:
    config = load_memory_config()
    if not config.enabled or config.backend != "filesystem":
        return
    guild_id = str(payload.get("workspace_id") or payload.get("guild_id"))
    channel_id = str(payload.get("channel_id"))
    catalog = _catalog_from_payload(payload)

    db = MemoryDB(guild_id)
    scope_map = _resolve_scope(db, guild_id, channel_id, catalog)
    scope_type = scope_map.get("scope_type", "global")
    scope_id = str(scope_map.get("scope_id", "global"))

    metadata = {
        "course_code": catalog.get("course_code"),
        "term": catalog.get("term"),
        "professor_name": catalog.get("professor_name"),
    }
    root = scope_root(guild_id, scope_type, scope_id, metadata)
    ensure_scope_dirs(root)

    day = _day_from_ts(payload.get("timestamp") or utcnow_iso())
    append_daily(root, day, [_format_line(payload)])

    db.insert_pending_message(
        guild_id=guild_id,
        channel_id=channel_id,
        scope_type=scope_type,
        scope_id=scope_id,
        message_id=str(payload.get("message_id")),
        author_id=str(payload.get("author_id")),
        ts=payload.get("timestamp") or utcnow_iso(),
        content=payload.get("content") or "",
    )

    pending_count = db.count_pending_messages(guild_id, channel_id)
    if pending_count < config.chunk_size:
        return

    batch = db.list_pending_messages(guild_id, channel_id, config.chunk_size)
    if not batch:
        return

    scope_map["guild_id"] = guild_id
    scope_map["channel_id"] = channel_id
    _create_chunk(db, config, root, day, scope_map, batch)

    overlap = config.chunk_overlap
    keep_ids = {msg["id"] for msg in batch[-overlap:]} if overlap > 0 else set()
    delete_ids = [msg["id"] for msg in batch if msg["id"] not in keep_ids]
    db.delete_pending_messages(delete_ids)


def force_chunking(guild_id: str, limit_per_channel: int = 200) -> dict[str, int]:
    config = load_memory_config()
    if not config.enabled or config.backend != "filesystem":
        return {}
    db = MemoryDB(guild_id)
    summary = {}
    for channel_id in db.list_pending_channels(guild_id):
        batch = db.list_pending_messages(guild_id, channel_id, limit_per_channel)
        if not batch:
            continue
        scope_map = db.get_channel_map(guild_id, channel_id) or {
            "scope_type": "global",
            "scope_id": "global",
            "offering_id": None,
            "professor_id": None,
        }
        scope_type = scope_map.get("scope_type", "global")
        scope_id = str(scope_map.get("scope_id", "global"))
        metadata = {}
        if scope_type == "course":
            offering_id = scope_map.get("offering_id")
            if offering_id:
                offering = db.get_offering(int(offering_id))
                if offering:
                    metadata["course_code"] = offering.get("course_code")
                    metadata["term"] = offering.get("term")
        if scope_type == "professor":
            professor_id = scope_map.get("professor_id")
            if professor_id:
                prof = db.get_professor(int(professor_id))
                if prof:
                    metadata["professor_name"] = prof.get("name")
        root = scope_root(guild_id, scope_type, scope_id, metadata)
        ensure_scope_dirs(root)
        day = _day_from_ts(batch[0].get("ts") or utcnow_iso())
        scope_map["guild_id"] = guild_id
        scope_map["channel_id"] = channel_id
        _create_chunk(db, config, root, day, scope_map, batch)
        db.delete_pending_messages([msg["id"] for msg in batch])
        summary[channel_id] = len(batch)
    return summary
