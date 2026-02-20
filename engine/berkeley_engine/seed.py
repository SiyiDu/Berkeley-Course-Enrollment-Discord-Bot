"""Seed data for quick demo setup."""

from __future__ import annotations

import argparse

from .config import load_engine_config
from .store import EngineStore
from shared.db import Database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the knowledge engine database.")
    parser.add_argument("--guild-id", required=True, help="Discord guild ID")
    parser.add_argument("--channel-id", required=True, help="Discord channel ID")
    parser.add_argument("--course-code", default="CS61B", help="Course code (e.g., CS61B)")
    parser.add_argument("--term", default="fa25", help="Term (e.g., fa25)")
    parser.add_argument("--section", default="001", help="Section (optional)")
    parser.add_argument("--professor", default="Unknown", help="Professor name")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_engine_config()
    db = Database(
        config.database_url,
        connect_timeout=config.db_connect_timeout,
        max_retries=config.db_max_retries,
        retry_backoff_sec=config.db_retry_backoff_sec,
    )
    store = EngineStore(db)
    store.init_db()

    professor_id = store.upsert_professor(args.professor, None)
    course_id = store.upsert_course(args.course_code, None)
    offering_id = store.upsert_course_offering(course_id, args.term, args.section, professor_id)
    channel_map_id = store.upsert_channel_map(
        guild_id=args.guild_id,
        channel_id=args.channel_id,
        course_offering_id=offering_id,
        enabled=True,
    )

    print("Seed complete:")
    print(f"- Professor ID: {professor_id}")
    print(f"- Course ID: {course_id}")
    print(f"- Offering ID: {offering_id}")
    print(f"- Channel Map ID: {channel_map_id}")


if __name__ == "__main__":
    main()
