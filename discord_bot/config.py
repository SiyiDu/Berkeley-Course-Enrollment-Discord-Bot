"""Runtime configuration for the Berkeley enrollment bot."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _env_flag(name: str, *, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PathConfig:
    course_index: pathlib.Path
    enrollments: pathlib.Path
    users: pathlib.Path


@dataclass(frozen=True)
class BotConfig:
    token: str
    guild_id: int
    student_role_name: str
    berkeley_suffix: str
    private_containers: bool
    engine_base_url: str
    client_id: str
    client_token: str
    course_category_id: int | None
    default_professor_name: str | None
    paths: PathConfig
    bot_database_url: str | None
    storage_backend: str
    db_connect_timeout: int
    db_max_retries: int
    db_retry_backoff_sec: float


def load_config() -> BotConfig:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in .env")

    guild_id = int(os.getenv("GUILD_ID", "1432284673865682959"))
    student_role_name = os.getenv("STUDENT_ROLE_NAME", "student")
    berkeley_suffix = os.getenv("BERKELEY_SUFFIX", "@berkeley.edu")
    private_containers = _env_flag("PRIVATE_CONTAINERS", default=True)
    engine_base_url = os.getenv("ENGINE_BASE_URL", "http://127.0.0.1:8000")
    client_id = os.getenv("CLIENT_ID", "discord_bot")
    client_token = os.getenv("CLIENT_TOKEN") or os.getenv("BOT_INGEST_TOKEN", "dev-bot-token")
    course_category_raw = os.getenv("COURSE_CATEGORY_ID")
    course_category_id = int(course_category_raw) if course_category_raw else None
    default_professor_name = os.getenv("DEFAULT_PROFESSOR_NAME")
    bot_database_url = os.getenv("BOT_DATABASE_URL") or os.getenv("DATABASE_URL")
    storage_backend = os.getenv("BOT_STORAGE_BACKEND")
    if not storage_backend:
        storage_backend = "db" if bot_database_url else "json"
    storage_backend = storage_backend.lower()
    db_connect_timeout = int(os.getenv("BOT_DB_CONNECT_TIMEOUT", "5"))
    db_max_retries = int(os.getenv("BOT_DB_MAX_RETRIES", "2"))
    db_retry_backoff_sec = float(os.getenv("BOT_DB_RETRY_BACKOFF_SEC", "0.3"))

    paths = PathConfig(
        course_index=PROJECT_ROOT / "course_index.json",
        enrollments=PROJECT_ROOT / "enrollments.json",
        users=PROJECT_ROOT / "users.json",
    )

    return BotConfig(
        token=token,
        guild_id=guild_id,
        student_role_name=student_role_name,
        berkeley_suffix=berkeley_suffix,
        private_containers=private_containers,
        engine_base_url=engine_base_url,
        client_id=client_id,
        client_token=client_token,
        course_category_id=course_category_id,
        default_professor_name=default_professor_name,
        paths=paths,
        bot_database_url=bot_database_url,
        storage_backend=storage_backend,
        db_connect_timeout=db_connect_timeout,
        db_max_retries=db_max_retries,
        db_retry_backoff_sec=db_retry_backoff_sec,
    )
