"""Hybrid search over memory chunks."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .config import load_memory_config
from .db import MemoryDB
from .embed import cosine, embed


def search(
    guild_id: str,
    scope_type: str,
    scope_id: str,
    query: str,
    top_k: int = 5,
    candidate_multiplier: int = 3,
) -> list[dict[str, Any]]:
    config = load_memory_config()
    if not config.enabled or config.backend != "filesystem":
        return []
    db = MemoryDB(guild_id)

    text_scores: dict[str, float] = {}
    if config.enable_bm25:
        bm25_rows = db.search_bm25(guild_id, scope_type, scope_id, query, top_k * candidate_multiplier)
        for row in bm25_rows:
            rank = row.get("rank") if isinstance(row, dict) else row["rank"]
            rank_value = float(rank) if rank is not None else 0.0
            text_scores[row["chunk_id"]] = 1.0 / (1.0 + max(0.0, rank_value))

    vector_scores: dict[str, float] = {}
    if config.enable_embeddings:
        query_vec = embed(query, config.embed_dim)
        for row in db.list_embeddings(guild_id, scope_type, scope_id):
            vector = json.loads(row["vector_json"])
            vector_scores[row["chunk_id"]] = cosine(query_vec, vector)

    merged: dict[str, float] = {}
    for chunk_id, score in text_scores.items():
        merged[chunk_id] = merged.get(chunk_id, 0.0) + config.text_weight * score
    for chunk_id, score in vector_scores.items():
        merged[chunk_id] = merged.get(chunk_id, 0.0) + config.vector_weight * score

    ranked = sorted(merged.items(), key=lambda item: item[1], reverse=True)
    chunk_ids = [chunk_id for chunk_id, _ in ranked[: top_k * candidate_multiplier]]
    results = []
    for chunk_id, score in ranked:
        if chunk_id not in chunk_ids:
            continue
        row = db._fetchone("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        if not row:
            continue
        payload = dict(row)
        payload["score"] = score
        results.append(payload)
        if len(results) >= top_k:
            break
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search memory.")
    parser.add_argument("--guild", required=True)
    parser.add_argument("--scope", required=True, choices=["course", "professor", "global"])
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    results = search(args.guild, args.scope, args.scope_id, args.query, top_k=args.top)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
