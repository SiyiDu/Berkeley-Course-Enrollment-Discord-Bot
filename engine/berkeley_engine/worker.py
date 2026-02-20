"""Background worker for queued engine jobs."""

from __future__ import annotations

import json
import logging
import time

from .config import load_engine_config
from .services import ExtractionService
from .store import EngineStore
from shared.db import Database


def _backoff_delay(attempt: int, base: int = 5, cap: int = 120) -> int:
    return min(cap, base * (2 ** max(0, attempt - 1)))


def run_once(store: EngineStore, service: ExtractionService, *, slice_limit: int, slice_minutes: int) -> bool:
    job = store.claim_job("extract_cycle")
    if not job:
        return False
    job_id = int(job["id"])
    payload_raw = job.get("payload_json")
    if payload_raw:
        try:
            payload = json.loads(payload_raw)
            slice_limit = int(payload.get("slice_limit", slice_limit))
            slice_minutes = int(payload.get("slice_minutes", slice_minutes))
        except Exception:
            pass

    try:
        service.run_job(job_id, slice_limit, slice_minutes)
        store.update_job(job_id, "completed")
    except Exception as exc:
        current = store.get_job(job_id) or {}
        attempts = int(current.get("attempts") or 0)
        if attempts < 3:
            delay = _backoff_delay(attempts)
            store.requeue_job(job_id, delay_seconds=delay, last_error=str(exc))
            logging.warning("Job %s failed; requeued in %ss", job_id, delay)
        else:
            store.update_job(job_id, "failed", last_error=str(exc))
            logging.exception("Job %s failed permanently: %s", job_id, exc)
    return True


def main() -> None:
    config = load_engine_config()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    db = Database(
        config.database_url,
        connect_timeout=config.db_connect_timeout,
        max_retries=config.db_max_retries,
        retry_backoff_sec=config.db_retry_backoff_sec,
    )
    store = EngineStore(db)
    store.init_db()
    service = ExtractionService(store)

    logging.info("Worker started (polling every 5s)")
    while True:
        ran = run_once(store, service, slice_limit=config.slice_limit, slice_minutes=config.slice_minutes)
        if not ran:
            time.sleep(5)


if __name__ == "__main__":
    main()
