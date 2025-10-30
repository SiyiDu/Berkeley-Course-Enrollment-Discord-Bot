"""Course metadata and naming helpers."""

from __future__ import annotations

import re
from typing import List, Optional

from discord import app_commands

from . import state


VALID_DEPTS: List[str] = [
    "PHYSICS",
    "ASTRON",
    "CHEM",
    "MATH",
    "STAT",
    "BIOLOGY",
    "MCELLBI",
    "INTEGBI",
    "DATA",
    "EECS",
    "CS",
    "MECHE",
    "CIVENG",
    "INDENG",
    "NUCENG",
    "MSE",
    "BIOE",
    "ENGIN",
    "ECON",
    "UGBA",
    "POLSCI",
    "SOCIOL",
    "PSYCH",
    "PHILOS",
    "ESPM",
    "EPS",
    "GEOG",
    "ENGLISH",
    "HISTORY",
    "SPANISH",
    "FRENCH",
    "ITALIAN",
    "CHINESE",
    "KOREAN",
    "JAPAN",
    "LINGUIS",
    "RHETOR",
    "FILM",
    "ART",
    "DESINV",
    "ARCH",
]


def course_category_name(term: Optional[str] = None) -> str:
    t = (term or state.current_term()).upper()
    return f"📚 Courses ({t})"


def archive_category_name(term: Optional[str] = None) -> str:
    t = (term or state.current_term()).upper()
    return f"📦 Archived ({t})"


def norm_course(dept: str, number: str) -> str:
    dept_s = re.sub(r"\s+", "", dept.strip().lower())
    num_s = re.sub(r"\s+", "", number.strip().upper())
    return f"{dept_s}-{num_s}"


def container_name_for(dept_up: str, term: Optional[str] = None) -> str:
    t = (term or state.current_term()).lower()
    return f"{dept_up.lower()}-courses-{t}"


def course_slug_for(dept_up: str, number: str, term: Optional[str] = None) -> str:
    t = (term or state.current_term()).lower()
    return f"{t}-{norm_course(dept_up, number)}"


def dept_from_slug(slug: str) -> Optional[str]:
    m = re.match(r"^(fa|sp)\d{2}-([a-z]+)-", slug.lower())
    return m.group(2) if m else None


async def dept_autocomplete(interaction, current: str):
    query = (current or "").upper()
    starts = [d for d in VALID_DEPTS if d.startswith(query)]
    contains = [d for d in VALID_DEPTS if query in d and d not in starts]
    return [app_commands.Choice(name=d, value=d) for d in (starts + contains)[:25]]

