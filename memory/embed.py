"""Simple deterministic embedding for local search."""

from __future__ import annotations

import math
import re
from typing import List

TOKEN_RE = re.compile(r"[a-zA-Z0-9]{2,}")


def _hash_token(token: str) -> int:
    value = 0
    for ch in token:
        value = (value * 31 + ord(ch)) & 0xFFFFFFFF
    return value


def embed(text: str, dim: int) -> List[float]:
    vector = [0.0] * dim
    for token in TOKEN_RE.findall(text.lower()):
        idx = _hash_token(token) % dim
        vector[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
