"""Run extraction jobs from the command line."""

from __future__ import annotations

from .config import load_engine_config
from .services import ExtractionService
from .store import EngineStore
from shared.db import Database


def main() -> None:
    config = load_engine_config()
    db = Database(
        config.database_url,
        connect_timeout=config.db_connect_timeout,
        max_retries=config.db_max_retries,
        retry_backoff_sec=config.db_retry_backoff_sec,
    )
    store = EngineStore(db)
    store.init_db()
    service = ExtractionService(store)
    job_id = store.create_job(
        "extract_cycle",
        {"slice_limit": config.slice_limit, "slice_minutes": config.slice_minutes},
        status="queued",
    )
    store.update_job(job_id, "running", increment_attempts=True)
    try:
        created = service.run_job(job_id, config.slice_limit, config.slice_minutes)
        store.update_job(job_id, "completed")
    except Exception as exc:
        store.update_job(job_id, "failed", last_error=str(exc))
        raise
    print(f"Job {job_id} created {created} proposals.")


if __name__ == "__main__":
    main()
