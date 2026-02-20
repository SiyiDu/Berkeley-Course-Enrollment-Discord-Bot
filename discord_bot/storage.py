"""Persistent storage helpers for the Berkeley bot."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from shared.db import Database

from .config import PathConfig


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonStore:
    def __init__(self, paths: PathConfig):
        self._paths = paths
        for path in (paths.course_index, paths.enrollments, paths.users):
            if not path.exists():
                path.write_text("{}", encoding="utf-8")

    @staticmethod
    def _load_json(path: pathlib.Path) -> dict:
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            # If the file is corrupted, reset it to an empty dict to avoid crashes.
            return {}

    @staticmethod
    def _save_json(path: pathlib.Path, data: dict) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp_path.replace(path)

    # -------------------- Course Index --------------------
    def index_upsert(self, slug: str, container_id: int, thread_id: int) -> None:
        data = self._load_json(self._paths.course_index)
        data[slug] = {
            "container_id": int(container_id),
            "thread_id": int(thread_id),
        }
        self._save_json(self._paths.course_index, data)

    def index_get(self, slug: str) -> Optional[Dict[str, int]]:
        data = self._load_json(self._paths.course_index)
        raw = data.get(slug)
        if raw is None:
            return None
        return {
            "container_id": int(raw["container_id"]),
            "thread_id": int(raw["thread_id"]),
        }

    # -------------------- Enrollments --------------------
    def add_enrollment(self, user_id: int, slug: str) -> None:
        data = self._load_json(self._paths.enrollments)
        entries = data.setdefault(str(user_id), [])
        if slug not in entries:
            entries.append(slug)
        self._save_json(self._paths.enrollments, data)

    def remove_enrollment(self, user_id: int, slug: str) -> None:
        data = self._load_json(self._paths.enrollments)
        entries = data.get(str(user_id), [])
        if slug in entries:
            entries.remove(slug)
        if not entries and str(user_id) in data:
            data.pop(str(user_id), None)
        self._save_json(self._paths.enrollments, data)

    def list_enrollments(self, user_id: int) -> List[str]:
        data = self._load_json(self._paths.enrollments)
        return list(data.get(str(user_id), []))

    # -------------------- Users --------------------
    def user_get(self, uid: int) -> Optional[Dict[str, str]]:
        data = self._load_json(self._paths.users)
        raw = data.get(str(uid))
        return dict(raw) if raw else None

    def user_upsert(self, uid: int, sid: str, email: str, name: str) -> None:
        data = self._load_json(self._paths.users)
        data[str(uid)] = {
            "student_id": sid,
            "email": email,
            "name": name,
        }
        self._save_json(self._paths.users, data)

    def user_delete(self, uid: int) -> None:
        data = self._load_json(self._paths.users)
        data.pop(str(uid), None)
        self._save_json(self._paths.users, data)


class DbStore:
    def __init__(self, db: Database):
        self._db = db
        self._migrations_dir = pathlib.Path(__file__).resolve().parent / "migrations"
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_schema_migrations (
              id TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            );
            """
        )
        applied = {row["id"] for row in self._db.fetchall("SELECT id FROM bot_schema_migrations")}
        migration_root = self._migrations_dir / self._db.dialect
        migration_dir = migration_root if migration_root.exists() else self._migrations_dir
        for path in sorted(migration_dir.glob("*.sql")):
            if path.stem in applied:
                continue
            self._db.execute_script(path.read_text(encoding="utf-8"))
            self._record_migration(path.stem)

    def _record_migration(self, migration_id: str) -> None:
        if self._db.dialect == "mysql":
            self._db.execute(
                "INSERT IGNORE INTO bot_schema_migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, _utcnow()),
            )
        else:
            self._db.execute(
                """
                INSERT INTO bot_schema_migrations (id, applied_at)
                VALUES (?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (migration_id, _utcnow()),
            )

    # -------------------- Course Index --------------------
    def index_upsert(self, slug: str, container_id: int, thread_id: int) -> None:
        now = _utcnow()
        if self._db.dialect == "mysql":
            self._db.execute(
                """
                INSERT INTO bot_course_index (slug, container_id, thread_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  container_id = VALUES(container_id),
                  thread_id = VALUES(thread_id),
                  updated_at = VALUES(updated_at)
                """,
                (slug, str(container_id), str(thread_id), now),
            )
        else:
            self._db.execute(
                """
                INSERT INTO bot_course_index (slug, container_id, thread_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (slug) DO UPDATE SET
                  container_id = excluded.container_id,
                  thread_id = excluded.thread_id,
                  updated_at = excluded.updated_at
                """,
                (slug, str(container_id), str(thread_id), now),
            )

    def index_get(self, slug: str) -> Optional[Dict[str, int]]:
        row = self._db.fetchone(
            "SELECT container_id, thread_id FROM bot_course_index WHERE slug = ?",
            (slug,),
        )
        if not row:
            return None
        return {
            "container_id": int(row["container_id"]),
            "thread_id": int(row["thread_id"]),
        }

    # -------------------- Enrollments --------------------
    def add_enrollment(self, user_id: int, slug: str) -> None:
        now = _utcnow()
        if self._db.dialect == "mysql":
            self._db.execute(
                "INSERT IGNORE INTO bot_enrollments (user_id, slug, created_at) VALUES (?, ?, ?)",
                (str(user_id), slug, now),
            )
        else:
            self._db.execute(
                """
                INSERT INTO bot_enrollments (user_id, slug, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id, slug) DO NOTHING
                """,
                (str(user_id), slug, now),
            )

    def remove_enrollment(self, user_id: int, slug: str) -> None:
        self._db.execute(
            "DELETE FROM bot_enrollments WHERE user_id = ? AND slug = ?",
            (str(user_id), slug),
        )

    def list_enrollments(self, user_id: int) -> List[str]:
        rows = self._db.fetchall(
            "SELECT slug FROM bot_enrollments WHERE user_id = ? ORDER BY created_at ASC",
            (str(user_id),),
        )
        return [row["slug"] for row in rows]

    # -------------------- Users --------------------
    def user_get(self, uid: int) -> Optional[Dict[str, str]]:
        row = self._db.fetchone(
            "SELECT student_id, email, name FROM bot_users WHERE user_id = ?",
            (str(uid),),
        )
        if not row:
            return None
        return {
            "student_id": row["student_id"],
            "email": row["email"],
            "name": row["name"],
        }

    def user_upsert(self, uid: int, sid: str, email: str, name: str) -> None:
        now = _utcnow()
        if self._db.dialect == "mysql":
            self._db.execute(
                """
                INSERT INTO bot_users (user_id, student_id, email, name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  student_id = VALUES(student_id),
                  email = VALUES(email),
                  name = VALUES(name),
                  updated_at = VALUES(updated_at)
                """,
                (str(uid), sid, email, name, now),
            )
        else:
            self._db.execute(
                """
                INSERT INTO bot_users (user_id, student_id, email, name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                  student_id = excluded.student_id,
                  email = excluded.email,
                  name = excluded.name,
                  updated_at = excluded.updated_at
                """,
                (str(uid), sid, email, name, now),
            )

    def user_delete(self, uid: int) -> None:
        self._db.execute("DELETE FROM bot_users WHERE user_id = ?", (str(uid),))


class DataStore:
    def __init__(
        self,
        paths: PathConfig,
        *,
        database_url: str | None = None,
        db_connect_timeout: int = 5,
        db_max_retries: int = 2,
        db_retry_backoff_sec: float = 0.3,
    ) -> None:
        if database_url:
            db = Database(
                database_url,
                connect_timeout=db_connect_timeout,
                max_retries=db_max_retries,
                retry_backoff_sec=db_retry_backoff_sec,
            )
            self._backend = DbStore(db)
        else:
            self._backend = JsonStore(paths)

    # -------------------- Course Index --------------------
    def index_upsert(self, slug: str, container_id: int, thread_id: int) -> None:
        self._backend.index_upsert(slug, container_id, thread_id)

    def index_get(self, slug: str) -> Optional[Dict[str, int]]:
        return self._backend.index_get(slug)

    # -------------------- Enrollments --------------------
    def add_enrollment(self, user_id: int, slug: str) -> None:
        self._backend.add_enrollment(user_id, slug)

    def remove_enrollment(self, user_id: int, slug: str) -> None:
        self._backend.remove_enrollment(user_id, slug)

    def list_enrollments(self, user_id: int) -> List[str]:
        return self._backend.list_enrollments(user_id)

    def list_enrollments_for_term(self, user_id: int, term: str) -> List[str]:
        prefix = term.lower() + "-"
        return [slug for slug in self.list_enrollments(user_id) if slug.lower().startswith(prefix)]

    def courses_by_term_and_dept(self, user_id: int, term: str, dept_slug: str) -> List[str]:
        matches = []
        for slug in self.list_enrollments(user_id):
            if slug.lower().startswith(term.lower()) and f"-{dept_slug.lower()}-" in slug.lower():
                matches.append(slug)
        return matches

    # -------------------- Users --------------------
    def user_get(self, uid: int) -> Optional[Dict[str, str]]:
        return self._backend.user_get(uid)

    def user_upsert(self, uid: int, sid: str, email: str, name: str) -> None:
        self._backend.user_upsert(uid, sid, email, name)

    def user_delete(self, uid: int) -> None:
        self._backend.user_delete(uid)


def indexed_course_and_thread(store: DataStore, slug: str) -> Optional[Tuple[int, int]]:
    meta = store.index_get(slug)
    if not meta:
        return None
    return int(meta["container_id"]), int(meta["thread_id"])
