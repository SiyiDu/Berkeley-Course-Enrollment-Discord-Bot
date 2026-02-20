import pathlib

from discord_bot.config import PathConfig
from discord_bot.storage import DataStore
from shared.db import Database


def test_database_sqlite_roundtrip(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "db.sqlite"
    db = Database(f"sqlite:///{db_path}")
    db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO sample (name) VALUES (?)", ("alice",))
    row = db.fetchone("SELECT name FROM sample WHERE id = ?", (1,))
    assert row["name"] == "alice"


def test_bot_datastore_db_backend(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "bot.sqlite"
    paths = PathConfig(
        course_index=tmp_path / "course_index.json",
        enrollments=tmp_path / "enrollments.json",
        users=tmp_path / "users.json",
    )
    store = DataStore(paths, database_url=f"sqlite:///{db_path}")

    store.user_upsert(123, "0000000001", "student@berkeley.edu", "Test User")
    record = store.user_get(123)
    assert record is not None
    assert record["student_id"] == "0000000001"

    store.index_upsert("fa25-cs-61b", 10, 20)
    index = store.index_get("fa25-cs-61b")
    assert index == {"container_id": 10, "thread_id": 20}

    store.add_enrollment(123, "fa25-cs-61b")
    store.add_enrollment(123, "fa25-cs-61b")
    enrollments = store.list_enrollments(123)
    assert enrollments == ["fa25-cs-61b"]

    store.remove_enrollment(123, "fa25-cs-61b")
    assert store.list_enrollments(123) == []
