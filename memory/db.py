"""SQLite index for memory system (derived, rebuildable)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import load_memory_config
from .utils import utcnow_iso


class MemoryDB:
    def __init__(self, guild_id: str) -> None:
        config = load_memory_config()
        self.guild_id = str(guild_id)
        self.path = config.data_root / f"guild_{self.guild_id}.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offerings (
                  offering_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  course_code TEXT NOT NULL,
                  term TEXT,
                  section TEXT,
                  professor_id INTEGER,
                  memory_root TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS professors (
                  professor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  aliases_json TEXT,
                  memory_root TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_map (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  guild_id TEXT NOT NULL,
                  channel_id TEXT NOT NULL,
                  scope_type TEXT NOT NULL,
                  scope_id TEXT NOT NULL,
                  offering_id INTEGER,
                  professor_id INTEGER,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  UNIQUE(guild_id, channel_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                  chunk_id TEXT PRIMARY KEY,
                  guild_id TEXT NOT NULL,
                  channel_id TEXT NOT NULL,
                  scope_type TEXT NOT NULL,
                  scope_id TEXT NOT NULL,
                  offering_id INTEGER,
                  professor_id INTEGER,
                  day TEXT NOT NULL,
                  start_message_id TEXT NOT NULL,
                  end_message_id TEXT NOT NULL,
                  start_ts TEXT NOT NULL,
                  end_ts TEXT NOT NULL,
                  authors_json TEXT,
                  text TEXT NOT NULL,
                  source_path TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                  chunk_id,
                  text,
                  content=''
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                  chunk_id TEXT PRIMARY KEY,
                  content_hash TEXT NOT NULL,
                  vector_json TEXT NOT NULL,
                  model TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                  entry_id TEXT PRIMARY KEY,
                  scope_type TEXT NOT NULL,
                  scope_id TEXT NOT NULL,
                  entry_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL,
                  source_chunk_ids_json TEXT,
                  content_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  guild_id TEXT NOT NULL,
                  channel_id TEXT NOT NULL,
                  scope_type TEXT NOT NULL,
                  scope_id TEXT NOT NULL,
                  message_id TEXT NOT NULL,
                  author_id TEXT NOT NULL,
                  ts TEXT NOT NULL,
                  content TEXT NOT NULL
                );
                """
            )

    def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone()

    def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(params))
            return list(cur.fetchall())

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._connect() as conn:
            conn.execute(sql, tuple(params))

    def _execute_return_id(self, sql: str, params: Iterable[Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(params))
            return int(cur.lastrowid)

    def upsert_professor(self, name: str, memory_root: str, aliases: list[str] | None = None) -> int:
        row = self._fetchone("SELECT professor_id FROM professors WHERE name = ?", (name,))
        if row:
            self._execute(
                "UPDATE professors SET memory_root = ?, aliases_json = ? WHERE professor_id = ?",
                (memory_root, json.dumps(aliases or []), row["professor_id"]),
            )
            return int(row["professor_id"])
        return self._execute_return_id(
            "INSERT INTO professors (name, aliases_json, memory_root) VALUES (?, ?, ?)",
            (name, json.dumps(aliases or []), memory_root),
        )

    def get_professor(self, professor_id: int) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT professor_id, name, aliases_json, memory_root FROM professors WHERE professor_id = ?",
            (professor_id,),
        )
        if not row:
            return None
        return {
            "professor_id": row["professor_id"],
            "name": row["name"],
            "aliases": json.loads(row["aliases_json"] or "[]"),
            "memory_root": row["memory_root"],
        }

    def get_professor_by_name(self, name: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT professor_id, name, aliases_json, memory_root FROM professors WHERE name = ?",
            (name,),
        )
        if not row:
            return None
        return {
            "professor_id": row["professor_id"],
            "name": row["name"],
            "aliases": json.loads(row["aliases_json"] or "[]"),
            "memory_root": row["memory_root"],
        }

    def upsert_offering(
        self,
        course_code: str,
        term: str | None,
        section: str | None,
        professor_id: int | None,
        memory_root: str,
    ) -> int:
        row = self._fetchone(
            """
            SELECT offering_id FROM offerings
            WHERE course_code = ? AND term IS ? AND section IS ?
            """,
            (course_code, term, section),
        )
        if row:
            self._execute(
                "UPDATE offerings SET professor_id = ?, memory_root = ? WHERE offering_id = ?",
                (professor_id, memory_root, row["offering_id"]),
            )
            return int(row["offering_id"])
        return self._execute_return_id(
            """
            INSERT INTO offerings (course_code, term, section, professor_id, memory_root)
            VALUES (?, ?, ?, ?, ?)
            """,
            (course_code, term, section, professor_id, memory_root),
        )

    def get_offering(self, offering_id: int) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT offering_id, course_code, term, section, professor_id, memory_root FROM offerings WHERE offering_id = ?",
            (offering_id,),
        )
        return dict(row) if row else None

    def get_channel_map(self, guild_id: str, channel_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, enabled
            FROM channel_map
            WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id),
        )
        return dict(row) if row else None

    def upsert_channel_map(
        self,
        guild_id: str,
        channel_id: str,
        scope_type: str,
        scope_id: str,
        offering_id: int | None,
        professor_id: int | None,
        enabled: bool = True,
    ) -> None:
        existing = self.get_channel_map(guild_id, channel_id)
        if existing:
            self._execute(
                """
                UPDATE channel_map
                SET scope_type = ?, scope_id = ?, offering_id = ?, professor_id = ?, enabled = ?
                WHERE guild_id = ? AND channel_id = ?
                """,
                (scope_type, scope_id, offering_id, professor_id, int(enabled), guild_id, channel_id),
            )
        else:
            self._execute(
                """
                INSERT INTO channel_map (guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, int(enabled)),
            )

    def list_pending_channels(self, guild_id: str) -> list[str]:
        rows = self._fetchall(
            "SELECT DISTINCT channel_id FROM pending_messages WHERE guild_id = ?",
            (guild_id,),
        )
        return [row["channel_id"] for row in rows]

    def insert_pending_message(
        self,
        guild_id: str,
        channel_id: str,
        scope_type: str,
        scope_id: str,
        message_id: str,
        author_id: str,
        ts: str,
        content: str,
    ) -> None:
        self._execute(
            """
            INSERT INTO pending_messages (guild_id, channel_id, scope_type, scope_id, message_id, author_id, ts, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, scope_type, scope_id, message_id, author_id, ts, content),
        )

    def list_pending_messages(self, guild_id: str, channel_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, message_id, author_id, ts, content
            FROM pending_messages
            WHERE guild_id = ? AND channel_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (guild_id, channel_id, limit),
        )
        return [dict(row) for row in rows]

    def count_pending_messages(self, guild_id: str, channel_id: str) -> int:
        row = self._fetchone(
            "SELECT COUNT(1) as count FROM pending_messages WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        return int(row["count"]) if row else 0

    def delete_pending_messages(self, ids: Iterable[int]) -> None:
        ids_list = list(ids)
        if not ids_list:
            return
        placeholders = ",".join(["?"] * len(ids_list))
        self._execute(
            f"DELETE FROM pending_messages WHERE id IN ({placeholders})",
            ids_list,
        )

    def insert_chunk(self, payload: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO chunks (
              chunk_id, guild_id, channel_id, scope_type, scope_id, offering_id, professor_id, day,
              start_message_id, end_message_id, start_ts, end_ts, authors_json, text, source_path, content_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["chunk_id"],
                payload["guild_id"],
                payload["channel_id"],
                payload["scope_type"],
                payload["scope_id"],
                payload.get("offering_id"),
                payload.get("professor_id"),
                payload["day"],
                payload["start_message_id"],
                payload["end_message_id"],
                payload["start_ts"],
                payload["end_ts"],
                json.dumps(payload.get("authors", [])),
                payload["text"],
                payload["source_path"],
                payload["content_hash"],
                payload.get("created_at") or utcnow_iso(),
            ),
        )
        self._execute(
            "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
            (payload["chunk_id"], payload["text"]),
        )

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        )
        return dict(row) if row else None

    def list_chunks(
        self,
        guild_id: str,
        scope_type: str,
        scope_id: str,
        limit: int,
        day: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [guild_id, scope_type, scope_id]
        day_clause = ""
        if day:
            day_clause = "AND day = ?"
            params.append(day)
        params.append(limit)
        rows = self._fetchall(
            f"""
            SELECT * FROM chunks
            WHERE guild_id = ? AND scope_type = ? AND scope_id = ? {day_clause}
            ORDER BY start_ts DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in rows]

    def search_bm25(
        self,
        guild_id: str,
        scope_type: str,
        scope_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT c.chunk_id, bm25(chunks_fts) as rank
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ? AND c.guild_id = ? AND c.scope_type = ? AND c.scope_id = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (query, guild_id, scope_type, scope_id, limit),
        )
        return [dict(row) for row in rows]

    def list_embeddings(self, guild_id: str, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT e.chunk_id, e.content_hash, e.vector_json, e.model
            FROM embeddings e
            JOIN chunks c ON c.chunk_id = e.chunk_id
            WHERE c.guild_id = ? AND c.scope_type = ? AND c.scope_id = ?
            """,
            (guild_id, scope_type, scope_id),
        )
        return [dict(row) for row in rows]

    def get_embedding(self, chunk_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT chunk_id, content_hash, vector_json, model FROM embeddings WHERE chunk_id = ?",
            (chunk_id,),
        )
        return dict(row) if row else None

    def upsert_embedding(self, chunk_id: str, content_hash: str, vector_json: str, model: str) -> None:
        existing = self.get_embedding(chunk_id)
        if existing and existing["content_hash"] == content_hash:
            return
        if existing:
            self._execute(
                "UPDATE embeddings SET content_hash = ?, vector_json = ?, model = ?, created_at = ? WHERE chunk_id = ?",
                (content_hash, vector_json, model, utcnow_iso(), chunk_id),
            )
        else:
            self._execute(
                """
                INSERT INTO embeddings (chunk_id, content_hash, vector_json, model, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk_id, content_hash, vector_json, model, utcnow_iso()),
            )

    def upsert_memory_entry(self, payload: dict[str, Any]) -> bool:
        existing = self._fetchone("SELECT entry_id FROM memory_entries WHERE content_hash = ?", (payload["content_hash"],))
        if existing:
            return False
        self._execute(
            """
            INSERT INTO memory_entries (
              entry_id, scope_type, scope_id, entry_type, title, body, source_chunk_ids_json, content_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["entry_id"],
                payload["scope_type"],
                payload["scope_id"],
                payload["entry_type"],
                payload["title"],
                payload["body"],
                json.dumps(payload.get("source_chunk_ids", [])),
                payload["content_hash"],
                payload.get("created_at") or utcnow_iso(),
            ),
        )
        return True
