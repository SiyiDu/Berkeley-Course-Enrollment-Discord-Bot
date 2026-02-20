"""Filesystem layout helpers for memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_memory_config
from .utils import join_lines, normalize_course_code, slugify


def scope_root(guild_id: str, scope_type: str, scope_id: str, metadata: dict[str, Any] | None = None) -> Path:
    config = load_memory_config()
    base = config.root / "workspace" / f"guild_{guild_id}"
    metadata = metadata or {}
    if scope_type == "course":
        course_code = normalize_course_code(metadata.get("course_code") or scope_id)
        term = metadata.get("term")
        if term:
            return base / "courses" / course_code / term
        return base / "courses" / course_code
    if scope_type == "professor":
        slug = slugify(metadata.get("professor_name") or scope_id)
        return base / "professors" / slug
    return base / "global"


def ensure_scope_dirs(root: Path) -> None:
    (root / "daily").mkdir(parents=True, exist_ok=True)
    (root / "chunks").mkdir(parents=True, exist_ok=True)
    memory_file = root / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("# Memory\n\n", encoding="utf-8")


def append_daily(root: Path, day: str, lines: list[str]) -> Path:
    daily_dir = root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    path = daily_dir / f"{day}.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(join_lines(lines))
    return path


def write_chunk(root: Path, day: str, chunk_id: str, header: dict[str, str], lines: list[str]) -> Path:
    chunk_dir = root / "chunks" / day
    chunk_dir.mkdir(parents=True, exist_ok=True)
    path = chunk_dir / f"chunk_{header['start_message_id']}_{header['end_message_id']}.md"
    header_lines = ["# Chunk"]
    for key, value in header.items():
        header_lines.append(f"{key}: {value}")
    header_lines.append("---")
    content = join_lines(header_lines + lines)
    path.write_text(content, encoding="utf-8")
    return path


def append_memory(root: Path, title: str, body: str) -> None:
    memory_file = root / "MEMORY.md"
    with memory_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {title}\n\n{body}\n")
