"""Insert demo data for professor + course testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .config import load_engine_config
from .store import EngineStore
from .utils import sanitize_excerpt
from shared.db import Database


@dataclass
class DemoMessage:
    message_id: str
    author_id: str
    content: str
    timestamp: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _insert_message(store: EngineStore, channel_id: str, message: DemoMessage) -> None:
    store.insert_message(
        {
            "message_id": message.message_id,
            "guild_id": "demo",
            "channel_id": channel_id,
            "author_id": message.author_id,
            "content": message.content,
            "timestamp": message.timestamp,
            "raw_json_optional": {
                "platform": "demo",
                "workspace_id": "demo",
            },
        }
    )


def _evidence(message: DemoMessage) -> list[dict[str, str | dict[str, str]]]:
    return [
        {
            "message_id": message.message_id,
            "excerpt": sanitize_excerpt(message.content),
            "metadata": {"author_id": message.author_id, "timestamp": message.timestamp},
        }
    ]


def _has_title(store: EngineStore, title: str) -> bool:
    row = store._fetchone(
        """
        SELECT id FROM cards WHERE title = ?
        UNION
        SELECT id FROM proposals WHERE title = ?
        LIMIT 1
        """,
        (title, title),
    )
    return row is not None


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

    professor_id = store.upsert_professor("Josh Hug", "CS")
    course_id = store.upsert_course("CS61B", "Data Structures")
    offering_id = store.upsert_course_offering(course_id, "2026-spring", "001", professor_id)
    store.upsert_channel_map("demo", "demo-channel", offering_id, True)

    professor_msgs = [
        DemoMessage(
            message_id=_new_id("prof"),
            author_id="student-1",
            content="Josh explains concepts clearly, but the workload is heavy.",
            timestamp=_now(),
        ),
        DemoMessage(
            message_id=_new_id("prof"),
            author_id="student-2",
            content="Pace is fast, but lectures are well structured.",
            timestamp=_now(),
        ),
    ]
    resource_msg = DemoMessage(
        message_id=_new_id("res"),
        author_id="student-3",
        content="Resource: https://cs61b.org has the full schedule and notes.",
        timestamp=_now(),
    )

    for message in professor_msgs + [resource_msg]:
        _insert_message(store, "demo-channel", message)

    professor_title = "Experience: Josh Hug teaching style"
    professor_proposal_id = None
    if not _has_title(store, professor_title):
        professor_proposal_id = uuid4().hex
        store.insert_proposal(
            {
                "id": professor_proposal_id,
                "type": "experience",
                "course_offering_id": offering_id,
                "subject_type": "professor",
                "subject_id": str(professor_id),
                "title": professor_title,
                "summary": "Students mention clear explanations with a fast pace and heavy workload.",
                "tags": ["experience", "workload", "pace"],
                "confidence": 0.6,
                "status": "proposed",
                "evidence": _evidence(professor_msgs[0]) + _evidence(professor_msgs[1]),
            }
        )

    resource_title = "Resource shared: https://cs61b.org"
    resource_proposal_id = None
    if not _has_title(store, resource_title):
        resource_proposal_id = uuid4().hex
        store.insert_proposal(
            {
                "id": resource_proposal_id,
                "type": "resource",
                "course_offering_id": offering_id,
                "subject_type": "course",
                "subject_id": str(offering_id),
                "title": resource_title,
                "summary": "Course site with schedule and notes.",
                "tags": ["resource"],
                "confidence": 0.6,
                "status": "proposed",
                "evidence": _evidence(resource_msg),
            }
        )

    if professor_proposal_id:
        store.approve_proposal(professor_proposal_id, None, approved_by="demo")
    if resource_proposal_id:
        store.approve_proposal(resource_proposal_id, None, approved_by="demo")

    print("Demo fixtures ready:")
    print(f"- Professor ID: {professor_id}")
    print(f"- Offering ID: {offering_id}")


if __name__ == "__main__":
    main()
