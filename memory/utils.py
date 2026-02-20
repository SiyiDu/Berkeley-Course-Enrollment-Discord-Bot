"""Utility helpers for memory system."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

SLUG_RE = re.compile(r"[^a-z0-9]+")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(text: str) -> str:
    lowered = text.strip().lower()
    cleaned = SLUG_RE.sub("-", lowered).strip("-")
    return cleaned or "unknown"


def normalize_course_code(code: str) -> str:
    return re.sub(r"\s+", "", code or "").upper()


def join_lines(lines: Iterable[str]) -> str:
    return "\n".join(lines).strip() + "\n"
