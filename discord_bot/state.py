"""Mutable runtime state shared across the bot."""

from __future__ import annotations

import os
import re
from typing import Callable, List

from dotenv import load_dotenv

from .config import PROJECT_ROOT


# Ensure environment overrides (DEFAULT_TERM) are available even if load_config()
# has not been called yet.
load_dotenv(PROJECT_ROOT / ".env")


TERM_PATTERN = re.compile(r"^(fa|sp)\d{2}$")

_current_term = os.getenv("DEFAULT_TERM", "fa25").lower()
_listeners: List[Callable[[str], None]] = []


def current_term() -> str:
    return _current_term


def set_current_term(term: str) -> None:
    global _current_term
    t = term.strip().lower()
    if not TERM_PATTERN.match(t):
        raise ValueError("Term must match faYY or spYY, e.g. fa25")
    _current_term = t
    for callback in list(_listeners):
        try:
            callback(t)
        except Exception:
            # Listeners should not break term updates.
            continue


def on_term_change(callback: Callable[[str], None]) -> None:
    _listeners.append(callback)

