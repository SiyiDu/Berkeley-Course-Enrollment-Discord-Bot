"""Rebuild memory SQLite index from on-disk chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_memory_config
from .db import MemoryDB
from .embed import embed
from .utils import sha256_text, utcnow_iso


def _parse_chunk(path: Path) -> dict[str, str]:
    header = {}
    text_lines = []
    in_header = True
    for line in path.read_text(encoding="utf-8").splitlines():
        if in_header:
            if line.strip() == "---":
                in_header = False
                continue
            if ":" in line and not line.startswith("#"):
                key, value = line.split(":", 1)
                header[key.strip()] = value.strip()
            continue
        text_lines.append(line)
    header["text"] = "\n".join(text_lines).strip()
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild memory index from files.")
    parser.add_argument("--guild", required=True)
    args = parser.parse_args()

    config = load_memory_config()
    if not config.enabled or config.backend != "filesystem":
        print("Memory backend disabled; reindex skipped.")
        return
    guild_id = str(args.guild)
    root = config.root / "workspace" / f"guild_{guild_id}"
    db = MemoryDB(guild_id)

    chunk_paths = list(root.glob("**/chunks/*/chunk_*.md"))
    for path in chunk_paths:
        header = _parse_chunk(path)
        chunk_id = header.get("chunk_id") or path.stem
        text = header.get("text", "")
        content_hash = sha256_text(text)
        scope_type = header.get("scope_type", "global")
        scope_id = header.get("scope_id", "global")
        chunk_guild = header.get("guild_id") or guild_id
        day = path.parent.name
        db.insert_chunk(
            {
                "chunk_id": chunk_id,
                "guild_id": chunk_guild,
                "channel_id": header.get("channel_id", ""),
                "scope_type": scope_type,
                "scope_id": scope_id,
                "offering_id": header.get("offering_id") or None,
                "professor_id": header.get("professor_id") or None,
                "day": day,
                "start_message_id": header.get("start_message_id", ""),
                "end_message_id": header.get("end_message_id", ""),
                "start_ts": header.get("start_ts", ""),
                "end_ts": header.get("end_ts", ""),
                "authors": header.get("authors", "").split(",") if header.get("authors") else [],
                "text": text,
                "source_path": str(path.relative_to(config.root)),
                "content_hash": content_hash,
                "created_at": utcnow_iso(),
            }
        )
        vector = embed(text, config.embed_dim)
        db.upsert_embedding(chunk_id, content_hash, json.dumps(vector), "hash-embed-v1")

    print(f"Reindexed {len(chunk_paths)} chunks for guild {guild_id}.")


if __name__ == "__main__":
    main()
