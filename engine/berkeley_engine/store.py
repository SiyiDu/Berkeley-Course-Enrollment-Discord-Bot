"""Database persistence for the knowledge engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from shared.db import Database, DatabaseIntegrityError


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChannelMapEntry:
    id: int
    guild_id: str
    channel_id: str
    course_offering_id: int
    scope_type: str
    scope_id: str
    professor_id_optional: int | None
    enabled: int


class EngineStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._migrations_dir = Path(__file__).resolve().parent / "migrations"

    def init_db(self) -> None:
        self._apply_migrations()

    def ping(self) -> bool:
        try:
            self._fetchone("SELECT 1")
            return True
        except Exception:
            return False

    def _apply_migrations(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              id TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            );
            """
        )

        applied = {row["id"] for row in self.db.fetchall("SELECT id FROM schema_migrations")}
        migration_root = self._migrations_dir / self.db.dialect
        migration_dir = migration_root if migration_root.exists() else self._migrations_dir
        migration_files = sorted(migration_dir.glob("*.sql"))
        if not applied and migration_files and self._existing_tables():
            baseline = migration_files[0].stem
            self._record_migration(baseline)
            applied.add(baseline)

        for path in migration_files:
            migration_id = path.stem
            if migration_id in applied:
                continue
            self.db.execute_script(path.read_text(encoding="utf-8"))
            self._record_migration(migration_id)

    def _existing_tables(self) -> bool:
        tables = [name for name in self.db.list_tables() if name != "schema_migrations"]
        return len(tables) > 0

    def _record_migration(self, migration_id: str) -> None:
        applied_at = _utcnow()
        if self.db.dialect == "mysql":
            self.db.execute(
                "INSERT IGNORE INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, applied_at),
            )
        else:
            self.db.execute(
                """
                INSERT INTO schema_migrations (id, applied_at)
                VALUES (?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (migration_id, applied_at),
            )

    def _execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        return_lastrowid: bool = False,
    ) -> int | None:
        if return_lastrowid:
            return self.db.insert_returning_id(sql, params or ())
        self.db.execute(sql, params or ())
        return None

    def _fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[Any]:
        return self.db.fetchall(sql, params or ())

    def _fetchone(self, sql: str, params: Sequence[Any] | None = None) -> Any | None:
        return self.db.fetchone(sql, params or ())

    def insert_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._execute(
            "INSERT INTO audit_logs (event_type, payload_json, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload), _utcnow()),
        )

    def create_client(
        self,
        client_id: str,
        client_token: str,
        name: str | None,
        allowed_platforms: list[str] | None,
        allowed_workspaces: list[str] | None,
    ) -> None:
        self._execute(
            """
            INSERT INTO clients (
              client_id, client_token, name, allowed_platforms_json, allowed_workspaces_json, revoked, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                client_token,
                name,
                json.dumps(allowed_platforms or []),
                json.dumps(allowed_workspaces or []),
                0,
                _utcnow(),
                _utcnow(),
            ),
        )

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT client_id, client_token, name, allowed_platforms_json, allowed_workspaces_json, revoked, created_at, updated_at
            FROM clients
            WHERE client_id = ?
            """,
            (client_id,),
        )
        if not row:
            return None
        return {
            "client_id": row["client_id"],
            "client_token": row["client_token"],
            "name": row["name"],
            "allowed_platforms": json.loads(row["allowed_platforms_json"] or "[]"),
            "allowed_workspaces": json.loads(row["allowed_workspaces_json"] or "[]"),
            "revoked": bool(row["revoked"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_clients(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT client_id, name, allowed_platforms_json, allowed_workspaces_json, revoked, created_at, updated_at
            FROM clients
            ORDER BY created_at DESC
            """
        )
        clients = []
        for row in rows:
            clients.append(
                {
                    "client_id": row["client_id"],
                    "name": row["name"],
                    "allowed_platforms": json.loads(row["allowed_platforms_json"] or "[]"),
                    "allowed_workspaces": json.loads(row["allowed_workspaces_json"] or "[]"),
                    "revoked": bool(row["revoked"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return clients

    def update_client_token(self, client_id: str, client_token: str) -> bool:
        row = self._fetchone("SELECT client_id FROM clients WHERE client_id = ?", (client_id,))
        if not row:
            return False
        self._execute(
            "UPDATE clients SET client_token = ?, updated_at = ? WHERE client_id = ?",
            (client_token, _utcnow(), client_id),
        )
        return True

    def revoke_client(self, client_id: str) -> bool:
        row = self._fetchone("SELECT client_id FROM clients WHERE client_id = ?", (client_id,))
        if not row:
            return False
        self._execute(
            "UPDATE clients SET revoked = 1, updated_at = ? WHERE client_id = ?",
            (_utcnow(), client_id),
        )
        return True

    def create_job(self, kind: str, payload: dict[str, Any] | None, status: str = "pending") -> int:
        job_id = self._execute(
            """
            INSERT INTO jobs (kind, payload_json, status, attempts, run_at, last_error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                json.dumps(payload) if payload is not None else None,
                status,
                0,
                _utcnow(),
                None,
                _utcnow(),
            ),
            return_lastrowid=True,
        )
        return int(job_id or 0)

    def update_job(
        self,
        job_id: int,
        status: str,
        last_error: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        if increment_attempts:
            self._execute(
                "UPDATE jobs SET status = ?, last_error = ?, attempts = attempts + 1 WHERE id = ?",
                (status, last_error, job_id),
            )
            return
        self._execute(
            "UPDATE jobs SET status = ?, last_error = ? WHERE id = ?",
            (status, last_error, job_id),
        )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT id, kind, status, run_at, attempts, last_error FROM jobs WHERE id = ?",
            (job_id,),
        )
        return dict(row) if row else None

    def claim_job(self, kind: str | None = None) -> dict[str, Any] | None:
        clauses = ["status = 'queued'"]
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = " AND ".join(clauses)
        row = self._fetchone(
            f"""
            SELECT id, kind, status, run_at, attempts, last_error, payload_json
            FROM jobs
            WHERE {where}
            ORDER BY run_at ASC
            LIMIT 1
            """,
            params,
        )
        if not row:
            return None
        updated = self.db.execute(
            "UPDATE jobs SET status = ?, attempts = attempts + 1 WHERE id = ? AND status = ?",
            ("running", row["id"], "queued"),
        )
        if updated == 0:
            return None
        return dict(row)

    def requeue_job(self, job_id: int, delay_seconds: int, last_error: str | None = None) -> None:
        run_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
        self._execute(
            "UPDATE jobs SET status = ?, run_at = ?, last_error = ? WHERE id = ?",
            ("queued", run_at, last_error, job_id),
        )

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, status, run_at, attempts, last_error
            FROM jobs
            ORDER BY run_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def find_active_job(self, kind: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, status, run_at, attempts, last_error
            FROM jobs
            WHERE kind = ? AND status IN ('queued', 'running')
            ORDER BY run_at DESC
            LIMIT 1
            """,
            (kind,),
        )
        return dict(row) if row else None

    def is_channel_enabled(self, guild_id: str, channel_id: str) -> bool:
        row = self._fetchone(
            "SELECT enabled FROM channel_map WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        return bool(row and row["enabled"])

    def get_channel_map(self, guild_id: str, channel_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, guild_id, channel_id, course_offering_id, scope_type, scope_id, professor_id_optional, enabled
            FROM channel_map
            WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id),
        )
        return dict(row) if row else None

    def insert_message(self, payload: dict[str, Any]) -> bool:
        try:
            self._execute(
                """
                INSERT INTO messages (message_id, guild_id, channel_id, author_id, content, ts, raw_json_optional)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["message_id"],
                    payload["guild_id"],
                    payload["channel_id"],
                    payload["author_id"],
                    payload["content"],
                    payload["timestamp"],
                    json.dumps(payload.get("raw_json_optional"))
                    if payload.get("raw_json_optional") is not None
                    else None,
                ),
            )
            return True
        except DatabaseIntegrityError:
            return False

    def list_enabled_channels(self) -> list[ChannelMapEntry]:
        rows = self._fetchall(
            "SELECT id, guild_id, channel_id, course_offering_id, scope_type, scope_id, professor_id_optional, enabled FROM channel_map WHERE enabled = 1"
        )
        return [
            ChannelMapEntry(
                id=row["id"],
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                course_offering_id=row["course_offering_id"],
                scope_type=row["scope_type"] or "course",
                scope_id=row["scope_id"] or str(row["course_offering_id"]),
                professor_id_optional=row["professor_id_optional"],
                enabled=row["enabled"],
            )
            for row in rows
        ]

    def list_recent_messages(
        self, channel_id: str, limit: int, minutes: int
    ) -> list[Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        rows = self._fetchall(
            """
            SELECT message_id, author_id, content, ts
            FROM messages
            WHERE channel_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (channel_id, limit),
        )
        filtered: list[sqlite3.Row] = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["ts"])
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                filtered.append(row)
        return filtered

    def upsert_professor(self, name: str, dept_optional: str | None) -> int:
        row = self._fetchone("SELECT id FROM professors WHERE name = ?", (name,))
        if row:
            self._execute("UPDATE professors SET dept_optional = ? WHERE id = ?", (dept_optional, row["id"]))
            return int(row["id"])
        professor_id = self._execute(
            "INSERT INTO professors (name, dept_optional) VALUES (?, ?)",
            (name, dept_optional),
            return_lastrowid=True,
        )
        return int(professor_id or 0)

    def upsert_course(self, code: str, title_optional: str | None) -> int:
        code = code.upper()
        row = self._fetchone("SELECT id FROM courses WHERE code = ?", (code,))
        if row:
            self._execute("UPDATE courses SET title_optional = ? WHERE id = ?", (title_optional, row["id"]))
            return int(row["id"])
        course_id = self._execute(
            "INSERT INTO courses (code, title_optional) VALUES (?, ?)",
            (code, title_optional),
            return_lastrowid=True,
        )
        return int(course_id or 0)

    def upsert_course_offering(
        self,
        course_id: int,
        term: str,
        section_optional: str | None,
        professor_id_optional: int | None,
    ) -> int:
        term = term.lower()
        row = self._fetchone(
            """
            SELECT id FROM course_offerings
            WHERE course_id = ? AND term = ? AND section_optional IS ?
            """,
            (course_id, term, section_optional),
        )
        if row:
            if professor_id_optional is not None:
                self._execute(
                    "UPDATE course_offerings SET professor_id_optional = ? WHERE id = ?",
                    (professor_id_optional, row["id"]),
                )
            return int(row["id"])
        offering_id = self._execute(
            """
            INSERT INTO course_offerings (course_id, term, section_optional, professor_id_optional)
            VALUES (?, ?, ?, ?)
            """,
            (course_id, term, section_optional, professor_id_optional),
            return_lastrowid=True,
        )
        return int(offering_id or 0)

    def upsert_channel_map(
        self,
        guild_id: str,
        channel_id: str,
        course_offering_id: int,
        enabled: bool,
        scope_type: str | None = None,
        scope_id: str | None = None,
        professor_id_optional: int | None = None,
    ) -> int:
        if scope_type is None:
            scope_type = "course"
        if scope_id is None:
            scope_id = str(course_offering_id)
        row = self._fetchone(
            "SELECT id FROM channel_map WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        if row:
            self._execute(
                "UPDATE channel_map SET guild_id = ?, course_offering_id = ?, enabled = ?, scope_type = ?, scope_id = ?, professor_id_optional = ? WHERE id = ?",
                (guild_id, course_offering_id, int(enabled), scope_type, scope_id, professor_id_optional, row["id"]),
            )
            return int(row["id"])
        channel_map_id = self._execute(
            """
            INSERT INTO channel_map (guild_id, channel_id, course_offering_id, enabled, scope_type, scope_id, professor_id_optional)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, course_offering_id, int(enabled), scope_type, scope_id, professor_id_optional),
            return_lastrowid=True,
        )
        return int(channel_map_id or 0)

    def insert_proposal(self, proposal: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO proposals (
              id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json,
              status, confidence, evidence_json, linked_card_ids_json, created_at, updated_at, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["id"],
                proposal["type"],
                proposal.get("course_offering_id"),
                proposal.get("subject_type"),
                proposal.get("subject_id"),
                proposal["title"],
                proposal["summary"],
                json.dumps(proposal.get("tags", [])),
                proposal.get("status", "proposed"),
                proposal.get("confidence", 0.0),
                json.dumps(proposal.get("evidence", [])),
                json.dumps(proposal.get("linked_card_ids", [])),
                proposal.get("created_at", _utcnow()),
                proposal.get("updated_at", _utcnow()),
                proposal.get("created_by"),
            ),
        )

    def list_proposals(
        self, status: str | None = None, proposal_type: str | None = None
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if proposal_type:
            clauses.append("type = ?")
            params.append(proposal_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetchall(
            f"""
            SELECT id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json,
                   status, confidence, evidence_json, linked_card_ids_json, created_at, updated_at
            FROM proposals
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [self._row_to_card(row) for row in rows]

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json,
                   status, confidence, evidence_json, linked_card_ids_json, created_at, updated_at
            FROM proposals
            WHERE id = ?
            """,
            (proposal_id,),
        )
        if not row:
            return None
        return self._row_to_card(row)

    def approve_proposal(self, proposal_id: str, edits: dict[str, Any] | None, approved_by: str | None) -> str | None:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return None
        payload = {**proposal}
        if edits:
            payload.update({k: v for k, v in edits.items() if v is not None})
        card_id = payload["id"]
        now = _utcnow()
        self._execute(
            """
            INSERT INTO cards (
              id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json, status,
              confidence, evidence_json, linked_card_ids_json, created_at, updated_at, approved_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                payload["type"],
                payload.get("course_offering_id"),
                payload.get("subject_type"),
                payload.get("subject_id"),
                payload["title"],
                payload["summary"],
                json.dumps(payload.get("tags", [])),
                "approved",
                payload.get("confidence", 0.0),
                json.dumps(payload.get("evidence", [])),
                json.dumps(payload.get("linked_card_ids", [])),
                now,
                now,
                approved_by,
            ),
        )
        self._execute("UPDATE proposals SET status = ?, updated_at = ? WHERE id = ?", ("approved", now, proposal_id))
        return card_id

    def reject_proposal(self, proposal_id: str) -> bool:
        row = self._fetchone("SELECT id FROM proposals WHERE id = ?", (proposal_id,))
        if not row:
            return False
        self._execute("UPDATE proposals SET status = ?, updated_at = ? WHERE id = ?", ("rejected", _utcnow(), proposal_id))
        return True

    def merge_proposal(self, proposal_id: str, card_id: str | None) -> bool:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return False
        status = "merge_suggested"
        if card_id:
            card = self.get_card(card_id)
            if not card:
                return False
            merged_evidence = _merge_evidence(card.get("evidence", []), proposal.get("evidence", []))
            self._execute(
                "UPDATE cards SET evidence_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(merged_evidence), _utcnow(), card_id),
            )
            status = "merged"
        self._execute(
            "UPDATE proposals SET status = ?, linked_card_ids_json = ?, updated_at = ? WHERE id = ?",
            (status, json.dumps([card_id] if card_id else []), _utcnow(), proposal_id),
        )
        return True

    def search_cards(
        self,
        card_types: Iterable[str],
        subject_type: str | None,
        subject_id: str | None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["status = 'approved'"]
        params: list[Any] = []
        types_list = list(card_types)
        type_clause = ",".join(["?"] * len(types_list))
        params.extend(types_list)
        clauses.append(f"type IN ({type_clause})")
        if subject_type:
            clauses.append("subject_type = ?")
            params.append(subject_type)
        if subject_id:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if query:
            clauses.append("(title LIKE ? OR summary LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        where = " AND ".join(clauses)
        rows = self._fetchall(
            f"""
            SELECT id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json,
                   status, confidence, evidence_json, linked_card_ids_json, created_at, updated_at
            FROM cards
            WHERE {where}
            ORDER BY confidence DESC, updated_at DESC
            LIMIT 5
            """,
            params,
        )
        return [self._row_to_card(row) for row in rows]

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, type, course_offering_id, subject_type, subject_id, title, summary, tags_json,
                   status, confidence, evidence_json, linked_card_ids_json, created_at, updated_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        )
        if not row:
            return None
        return self._row_to_card(row)

    def list_courses(self) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT id, code, title_optional FROM courses ORDER BY code")
        return [dict(row) for row in rows]

    def list_professors(self) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT id, name, dept_optional FROM professors ORDER BY name")
        return [dict(row) for row in rows]

    def list_course_offerings(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT co.id, co.term, co.section_optional, c.code as course_code, p.name as professor_name
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            LEFT JOIN professors p ON co.professor_id_optional = p.id
            ORDER BY co.term DESC, c.code
            """
        )
        return [dict(row) for row in rows]

    def get_offering(self, offering_id: int) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT co.id, co.term, co.section_optional, c.code as course_code,
                   p.id as professor_id, p.name as professor_name
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            LEFT JOIN professors p ON co.professor_id_optional = p.id
            WHERE co.id = ?
            """,
            (offering_id,),
        )
        return dict(row) if row else None

    def resolve_offerings(
        self, course_code: str, term: str | None, section: str | None
    ) -> list[dict[str, Any]]:
        params: list[Any] = [course_code.upper()]
        clauses = ["c.code = ?"]
        if term:
            clauses.append("co.term = ?")
            params.append(term.lower())
        if section:
            clauses.append("co.section_optional = ?")
            params.append(section)
        where = " AND ".join(clauses)
        rows = self._fetchall(
            f"""
            SELECT co.id, co.term, co.section_optional, c.code as course_code,
                   p.id as professor_id, p.name as professor_name
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            LEFT JOIN professors p ON co.professor_id_optional = p.id
            WHERE {where}
            ORDER BY co.term DESC
            """,
            params,
        )
        return [dict(row) for row in rows]

    def get_professor(self, professor_id: int) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT id, name, dept_optional FROM professors WHERE id = ?",
            (professor_id,),
        )
        return dict(row) if row else None

    def find_professors_by_name(self, name_like: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT id, name, dept_optional FROM professors WHERE name LIKE ?",
            (f"%{name_like}%",),
        )
        return [dict(row) for row in rows]

    def find_offerings_by_course_code(self, code: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT co.id, co.term, co.section_optional, c.code as course_code
            FROM course_offerings co
            JOIN courses c ON co.course_id = c.id
            WHERE c.code = ?
            ORDER BY co.term DESC
            """,
            (code.upper(),),
        )
        return [dict(row) for row in rows]

    def resolve_course_code(self, code: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT id, code, title_optional FROM courses WHERE code LIKE ?", (code,))
        return [dict(row) for row in rows]

    def resolve_professor(self, name_like: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT id, name, dept_optional FROM professors WHERE name LIKE ?",
            (f"%{name_like}%",),
        )
        return [dict(row) for row in rows]

    def list_messages_in_window(
        self,
        guild_id: str,
        channel_id: str,
        start_ts: str,
        end_ts: str,
        limit: int = 300,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT message_id, author_id, content, ts
            FROM messages
            WHERE guild_id = ? AND channel_id = ? AND ts >= ? AND ts <= ?
            ORDER BY ts ASC
            LIMIT ? OFFSET ?
            """,
            (guild_id, channel_id, start_ts, end_ts, limit, offset),
        )
        return [dict(row) for row in rows]

    def count_messages_in_window(
        self,
        guild_id: str,
        channel_id: str,
        start_ts: str,
        end_ts: str,
    ) -> int:
        row = self._fetchone(
            "SELECT COUNT(1) as count FROM messages WHERE guild_id = ? AND channel_id = ? AND ts >= ? AND ts <= ?",
            (guild_id, channel_id, start_ts, end_ts),
        )
        return int(row["count"]) if row else 0

    def fetch_messages_by_ids(self, message_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = list(message_ids)
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        rows = self._fetchall(
            f"SELECT message_id, author_id, ts FROM messages WHERE message_id IN ({placeholders})",
            ids,
        )
        return [dict(row) for row in rows]

    def _row_to_card(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "course_offering_id": row["course_offering_id"],
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "title": row["title"],
            "summary": row["summary"],
            "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
            "status": row["status"],
            "confidence": row["confidence"] if row["confidence"] is not None else 0.0,
            "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else [],
            "linked_card_ids": json.loads(row["linked_card_ids_json"]) if row["linked_card_ids_json"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _merge_evidence(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids = {item.get("message_id") for item in existing if item.get("message_id")}
    merged = list(existing)
    for item in incoming:
        message_id = item.get("message_id")
        if message_id and message_id in seen_ids:
            continue
        merged.append(item)
        if message_id:
            seen_ids.add(message_id)
    return merged
