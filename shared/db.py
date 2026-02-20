"""Database helpers with SQLite/Postgres/MySQL support."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urlparse


class DatabaseError(RuntimeError):
    """Base database error."""


class DatabaseIntegrityError(DatabaseError):
    """Raised on unique/constraint violations."""


class DatabaseOperationalError(DatabaseError):
    """Raised on transient connection/operational issues."""


class UnsupportedDatabaseError(DatabaseError):
    """Raised when the database URL scheme is unsupported."""


@dataclass(frozen=True)
class DatabaseUrl:
    raw: str
    dialect: str


def _sqlite_url_from_path(path: str | Path) -> str:
    if isinstance(path, Path):
        path_str = path.as_posix()
    else:
        path_str = str(path)
    if path_str == ":memory:":
        return "sqlite:///:memory:"
    # Ensure forward slashes for SQLite URLs.
    if len(path_str) >= 2 and path_str[1] == ":":
        path_str = path_str.replace("\\", "/")
    return f"sqlite:///{path_str}"


def normalize_database_url(database_url: str | None, *, sqlite_path: str | Path | None = None) -> DatabaseUrl:
    if database_url:
        raw = database_url.strip()
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://") :]
        if raw.startswith("sqlite://") or raw.startswith("postgresql://") or raw.startswith("mysql://"):
            return DatabaseUrl(raw=raw, dialect=_detect_dialect(raw))
        if "://" not in raw:
            return DatabaseUrl(raw=_sqlite_url_from_path(raw), dialect="sqlite")
        raise UnsupportedDatabaseError(f"Unsupported database URL: {raw}")
    if sqlite_path is not None:
        raw = _sqlite_url_from_path(sqlite_path)
        return DatabaseUrl(raw=raw, dialect="sqlite")
    raise UnsupportedDatabaseError("DATABASE_URL or DB_PATH is required")


def _detect_dialect(url: str) -> str:
    if url.startswith("sqlite://"):
        return "sqlite"
    if url.startswith("postgresql://"):
        return "postgres"
    if url.startswith("mysql://"):
        return "mysql"
    raise UnsupportedDatabaseError(f"Unsupported database URL scheme: {url}")


def _split_sql_script(script: str) -> list[str]:
    cleaned_lines = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    statements = []
    for chunk in cleaned.split(";"):
        stmt = chunk.strip()
        if stmt:
            statements.append(stmt)
    return statements


class Database:
    def __init__(
        self,
        url: str,
        *,
        connect_timeout: int = 5,
        max_retries: int = 2,
        retry_backoff_sec: float = 0.3,
    ) -> None:
        info = normalize_database_url(url)
        self.url = info.raw
        self.dialect = info.dialect
        self.connect_timeout = connect_timeout
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self._paramstyle = "qmark" if self.dialect == "sqlite" else "format"

        if self.dialect == "sqlite":
            self._integrity_errors = (sqlite3.IntegrityError,)
            self._operational_errors = (sqlite3.OperationalError,)
        elif self.dialect == "postgres":
            try:
                import psycopg
            except ImportError as exc:
                raise UnsupportedDatabaseError("psycopg is required for Postgres") from exc
            self._psycopg = psycopg
            self._integrity_errors = (psycopg.IntegrityError,)
            self._operational_errors = (psycopg.OperationalError,)
        elif self.dialect == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise UnsupportedDatabaseError("pymysql is required for MySQL") from exc
            self._pymysql = pymysql
            self._integrity_errors = (pymysql.IntegrityError,)
            self._operational_errors = (pymysql.OperationalError,)
        else:
            raise UnsupportedDatabaseError(f"Unsupported database dialect: {self.dialect}")

    def _rewrite_sql(self, sql: str) -> str:
        if self._paramstyle == "format":
            return sql.replace("?", "%s")
        return sql

    def _connect_sqlite(self) -> sqlite3.Connection:
        parsed = urlparse(self.url)
        path = unquote(parsed.path or "")
        if path.startswith("/") and len(path) >= 3 and path[2] == ":":
            path = path[1:]
        if path in {"", "/"}:
            path = ":memory:"
        conn = sqlite3.connect(path, timeout=self.connect_timeout)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_postgres(self):
        from psycopg.rows import dict_row

        return self._psycopg.connect(
            self.url,
            connect_timeout=self.connect_timeout,
            row_factory=dict_row,
        )

    def _connect_mysql(self):
        parsed = urlparse(self.url)
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 3306
        database = (parsed.path or "").lstrip("/")
        return self._pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            connect_timeout=self.connect_timeout,
            cursorclass=self._pymysql.cursors.DictCursor,
            charset="utf8mb4",
            autocommit=False,
        )

    def _connect(self):
        if self.dialect == "sqlite":
            return self._connect_sqlite()
        if self.dialect == "postgres":
            return self._connect_postgres()
        if self.dialect == "mysql":
            return self._connect_mysql()
        raise UnsupportedDatabaseError(f"Unsupported database dialect: {self.dialect}")

    @contextmanager
    def _conn(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _run_with_retry(self, fn):
        attempt = 0
        while True:
            try:
                return fn()
            except self._operational_errors as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise DatabaseOperationalError(str(exc)) from exc
                time.sleep(self.retry_backoff_sec * attempt)
            except self._integrity_errors as exc:
                raise DatabaseIntegrityError(str(exc)) from exc

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        params = params or ()

        def op() -> int:
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(self._rewrite_sql(sql), params)
                return int(cur.rowcount)

        return self._run_with_retry(op)

    def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> Any | None:
        params = params or ()

        def op():
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(self._rewrite_sql(sql), params)
                return cur.fetchone()

        return self._run_with_retry(op)

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[Any]:
        params = params or ()

        def op():
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(self._rewrite_sql(sql), params)
                return list(cur.fetchall())

        return self._run_with_retry(op)

    def insert_returning_id(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        id_column: str = "id",
    ) -> int:
        params = params or ()

        def op() -> int:
            with self._conn() as conn:
                cur = conn.cursor()
                if self.dialect == "postgres":
                    sql_with_return = f"{self._rewrite_sql(sql)} RETURNING {id_column}"
                    cur.execute(sql_with_return, params)
                    row = cur.fetchone()
                    if isinstance(row, dict):
                        return int(row.get(id_column) or 0)
                    return int(getattr(row, id_column, 0) or 0)
                cur.execute(self._rewrite_sql(sql), params)
                return int(getattr(cur, "lastrowid", 0) or 0)

        return self._run_with_retry(op)

    def execute_script(self, script: str) -> None:
        def op() -> None:
            with self._conn() as conn:
                if self.dialect == "sqlite":
                    conn.executescript(script)
                    return
                cur = conn.cursor()
                for stmt in _split_sql_script(script):
                    cur.execute(self._rewrite_sql(stmt))

        self._run_with_retry(op)

    def list_tables(self) -> list[str]:
        if self.dialect == "sqlite":
            rows = self.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            return [row["name"] for row in rows]
        if self.dialect == "postgres":
            rows = self.fetchall(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            return [row["table_name"] for row in rows]
        if self.dialect == "mysql":
            rows = self.fetchall(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
            )
            return [row["table_name"] for row in rows]
        return []
