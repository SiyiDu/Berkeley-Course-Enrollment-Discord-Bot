"""Utility helpers for extraction and ask handling."""

from __future__ import annotations

import re


COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{2,6})\s*-?\s*(\d{1,3}[A-Za-z]?)\b")
URL_RE = re.compile(r"(https?://\S+)")
MENTION_RE = re.compile(r"<@!?(\d+)>")
AT_HANDLE_RE = re.compile(r"@\w+")
DISCORD_ID_RE = re.compile(r"\b\d{17,20}\b")

EXPERIENCE_KEYWORDS = {
    "workload",
    "pace",
    "exam",
    "grading",
    "midterm",
    "final",
    "hard",
    "easy",
    "tough",
    "heavy",
    "light",
    "project",
    "assignment",
    "quiz",
    "lecture",
}


def normalize_course_code(text: str) -> str:
    match = COURSE_CODE_RE.search(text)
    if not match:
        return ""
    dept = match.group(1).upper()
    number = match.group(2).upper().replace(" ", "")
    return f"{dept}{number}"


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def sanitize_excerpt(text: str, limit: int = 300) -> str:
    text = MENTION_RE.sub("@redacted", text)
    text = AT_HANDLE_RE.sub("@redacted", text)
    text = DISCORD_ID_RE.sub("[redacted]", text)
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


def is_experience_query(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in EXPERIENCE_KEYWORDS)
