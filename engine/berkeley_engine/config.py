"""Configuration for the knowledge engine API and jobs."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}") from exc


@dataclass(frozen=True)
class EngineConfig:
    database_url: str
    db_path: pathlib.Path
    db_connect_timeout: int
    db_max_retries: int
    db_retry_backoff_sec: float
    ingest_token: str
    admin_token: str
    admin_username: str
    admin_password: str
    api_host: str
    api_port: int
    slice_limit: int
    slice_minutes: int
    env: str
    llm_enabled: bool
    allow_unmapped_channels: bool
    trusted_guild_id: str | None
    context_token_secret: str | None
    context_token_ttl_sec: int
    run_jobs_inline: bool
    log_level: str


def load_engine_config() -> EngineConfig:
    db_path = pathlib.Path(os.getenv("DB_PATH", PROJECT_ROOT / "knowledge_engine.db"))
    database_url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not database_url:
        database_url = f"sqlite:///{db_path.as_posix()}"
    ingest_token = os.getenv("BOT_INGEST_TOKEN", "dev-bot-token")
    admin_token = os.getenv("ADMIN_TOKEN", "dev-admin-token")
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")
    api_host = os.getenv("ENGINE_HOST", "127.0.0.1")
    api_port = _env_int("ENGINE_PORT", 8000)
    slice_limit = _env_int("ENGINE_SLICE_LIMIT", 40)
    slice_minutes = _env_int("ENGINE_SLICE_MINUTES", 60)
    env = os.getenv("ENGINE_ENV", "dev")
    llm_enabled = _env_flag("LLM_ENABLED", default=False)
    allow_unmapped_channels = _env_flag("ENGINE_ALLOW_UNMAPPED_CHANNELS", default=False)
    trusted_guild_id = os.getenv("ENGINE_TRUST_GUILD_ID")
    context_token_secret = os.getenv("CONTEXT_TOKEN_SECRET")
    context_token_ttl_sec = _env_int("CONTEXT_TOKEN_TTL_SEC", 3600)
    run_jobs_inline = _env_flag("ENGINE_RUN_JOBS_INLINE", default=env != "prod")
    db_connect_timeout = _env_int("DB_CONNECT_TIMEOUT", 5)
    db_max_retries = _env_int("DB_MAX_RETRIES", 2)
    db_retry_backoff_sec = float(os.getenv("DB_RETRY_BACKOFF_SEC", "0.3"))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    return EngineConfig(
        database_url=database_url,
        db_path=db_path,
        db_connect_timeout=db_connect_timeout,
        db_max_retries=db_max_retries,
        db_retry_backoff_sec=db_retry_backoff_sec,
        ingest_token=ingest_token,
        admin_token=admin_token,
        admin_username=admin_username,
        admin_password=admin_password,
        api_host=api_host,
        api_port=api_port,
        slice_limit=slice_limit,
        slice_minutes=slice_minutes,
        env=env,
        llm_enabled=llm_enabled,
        allow_unmapped_channels=allow_unmapped_channels,
        trusted_guild_id=trusted_guild_id,
        context_token_secret=context_token_secret,
        context_token_ttl_sec=context_token_ttl_sec,
        run_jobs_inline=run_jobs_inline,
        log_level=log_level,
    )
