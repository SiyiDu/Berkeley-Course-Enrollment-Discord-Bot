"""Persistent JSON storage helpers for the Berkeley bot."""

from __future__ import annotations

import json
import pathlib
from typing import Dict, List, Optional, Tuple

from .config import PathConfig


class DataStore:
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

    def list_enrollments_for_term(self, user_id: int, term: str) -> List[str]:
        prefix = term.lower() + "-"
        return [slug for slug in self.list_enrollments(user_id) if slug.lower().startswith(prefix)]

    def courses_by_term_and_dept(
        self, user_id: int, term: str, dept_slug: str
    ) -> List[str]:
        matches = []
        for slug in self.list_enrollments(user_id):
            if slug.lower().startswith(term.lower()) and f"-{dept_slug.lower()}-" in slug.lower():
                matches.append(slug)
        return matches

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


def indexed_course_and_thread(store: DataStore, slug: str) -> Optional[Tuple[int, int]]:
    meta = store.index_get(slug)
    if not meta:
        return None
    return int(meta["container_id"]), int(meta["thread_id"])
