"""Reset the knowledge engine SQLite database."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import load_engine_config
from .store import EngineStore
from shared.db import Database


def main() -> None:
    config = load_engine_config()
    parsed = urlparse(config.database_url)
    if not config.database_url.startswith("sqlite://"):
        raise RuntimeError("reset_db only supports sqlite URLs.")
    path = unquote(parsed.path or "")
    if path.startswith("/") and len(path) >= 3 and path[2] == ":":
        path = path[1:]
    if path and path != ":memory:":
        db_path = config.db_path if config.db_path.exists() or not path else Path(path)
        if db_path.exists():
            db_path.unlink()
    db = Database(
        config.database_url,
        connect_timeout=config.db_connect_timeout,
        max_retries=config.db_max_retries,
        retry_backoff_sec=config.db_retry_backoff_sec,
    )
    store = EngineStore(db)
    store.init_db()
    print("Reset database complete.")


if __name__ == "__main__":
    main()
