"""Configuration for memory subsystem."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}") from exc


@dataclass(frozen=True)
class MemoryConfig:
    backend: str
    enabled: bool
    root: pathlib.Path
    data_root: pathlib.Path
    chunk_size: int
    chunk_overlap: int
    embed_dim: int
    vector_weight: float
    text_weight: float
    enable_bm25: bool
    enable_embeddings: bool
    llm_model: str
    llm_api_key: str | None


def load_memory_config() -> MemoryConfig:
    default_backend = "disabled" if os.getenv("ENGINE_ENV") == "prod" else "filesystem"
    backend = os.getenv("MEMORY_BACKEND", default_backend).lower()
    enabled = backend not in {"disabled", "off", "false", "0"}
    root = pathlib.Path(os.getenv("MEMORY_ROOT", PROJECT_ROOT / "memory"))
    data_root = pathlib.Path(os.getenv("MEMORY_DATA_ROOT", root / "data"))
    chunk_size = _env_int("MEMORY_CHUNK_SIZE", 20)
    chunk_overlap = _env_int("MEMORY_CHUNK_OVERLAP", 5)
    embed_dim = _env_int("MEMORY_EMBED_DIM", 128)
    vector_weight = float(os.getenv("MEMORY_VECTOR_WEIGHT", "0.7"))
    text_weight = float(os.getenv("MEMORY_TEXT_WEIGHT", "0.3"))
    enable_bm25 = os.getenv("MEMORY_ENABLE_BM25", "true").lower() in {"1", "true", "yes", "on"}
    enable_embeddings = os.getenv("MEMORY_ENABLE_EMBEDDINGS", "true").lower() in {"1", "true", "yes", "on"}
    llm_model = os.getenv("MEMORY_LLM_MODEL", "gpt-4o-mini")
    llm_api_key = os.getenv("MEMORY_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    return MemoryConfig(
        backend=backend,
        enabled=enabled,
        root=root,
        data_root=data_root,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_dim=embed_dim,
        vector_weight=vector_weight,
        text_weight=text_weight,
        enable_bm25=enable_bm25,
        enable_embeddings=enable_embeddings,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
    )
