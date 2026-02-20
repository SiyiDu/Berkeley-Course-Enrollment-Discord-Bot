"""Rule-based extraction to generate proposal cards."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .store import ChannelMapEntry
from .utils import EXPERIENCE_KEYWORDS, extract_urls, sanitize_excerpt


EXPLANATION_HINTS = ("because", "means", "so that", "in order to", "this is why")


def _new_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_question(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()


def _topic_from_experience(text: str) -> str:
    lowered = text.lower()
    for keyword in EXPERIENCE_KEYWORDS:
        if keyword in lowered:
            return keyword
    return "general"


def build_proposals(
    messages: Iterable[dict],
    channel_map: ChannelMapEntry,
    existing_titles: set[str],
    experience_window_days: int = 7,
) -> list[dict]:
    proposals: list[dict] = []
    created_at = _utcnow()
    subject_type = "course"
    subject_id = str(channel_map.course_offering_id)

    for message in messages:
        content = message["content"]
        metadata = {"author_id": message["author_id"], "timestamp": message["ts"]}
        urls = extract_urls(content)
        if urls:
            for url in urls:
                title = f"Resource shared: {url}"
                if title in existing_titles:
                    continue
                proposals.append(
                    {
                        "id": _new_id(),
                        "type": "resource",
                        "course_offering_id": channel_map.course_offering_id,
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "title": title,
                        "summary": "A helpful resource was shared in the channel.",
                        "tags": ["resource"],
                        "confidence": 0.6,
                        "status": "proposed",
                        "evidence": [
                            {
                                "message_id": message["message_id"],
                                "excerpt": sanitize_excerpt(content),
                                "metadata": metadata,
                            }
                        ],
                        "created_at": created_at,
                        "updated_at": created_at,
                    }
                )
                existing_titles.add(title)

    question_counts: Counter[str] = Counter()
    question_evidence: dict[str, list[dict]] = defaultdict(list)
    experience_counts: dict[str, dict[str, set[str] | list[dict]]] = defaultdict(
        lambda: {"authors": set(), "evidence": []}
    )
    knowledge_candidates: list[dict] = []

    for message in messages:
        content = message["content"]
        metadata = {"author_id": message["author_id"], "timestamp": message["ts"]}
        if "?" in content:
            norm = _normalize_question(content)
            if norm:
                question_counts[norm] += 1
                question_evidence[norm].append(
                    {
                        "message_id": message["message_id"],
                        "excerpt": sanitize_excerpt(content),
                        "metadata": metadata,
                    }
                )

        if any(keyword in content.lower() for keyword in EXPERIENCE_KEYWORDS):
            topic = _topic_from_experience(content)
            entry = experience_counts[topic]
            entry["authors"].add(message["author_id"])
            entry["evidence"].append(
                {
                    "message_id": message["message_id"],
                    "excerpt": sanitize_excerpt(content),
                    "metadata": metadata,
                }
            )

        if any(hint in content.lower() for hint in EXPLANATION_HINTS):
            knowledge_candidates.append(message)

    for norm, count in question_counts.items():
        if count < 3:
            continue
        title = f"FAQ: {norm[:60].capitalize()}?"
        if title in existing_titles:
            continue
        evidence = question_evidence[norm][:3]
        proposals.append(
            {
                "id": _new_id(),
                "type": "faq",
                "course_offering_id": channel_map.course_offering_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "title": title,
                "summary": "This question comes up repeatedly. Consider linking to a knowledge card.",
                "tags": ["faq"],
                "confidence": 0.55,
                "status": "proposed",
                "evidence": evidence,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        existing_titles.add(title)

    cutoff = datetime.now(timezone.utc) - timedelta(days=experience_window_days)
    for topic, payload in experience_counts.items():
        evidence = [
            ev
            for ev in payload["evidence"]
            if _recent_message(ev.get("message_id"), messages, cutoff)
        ]
        unique_authors = payload["authors"]
        if len(unique_authors) < 2 and len(evidence) < 3:
            continue
        title = f"Experience: {topic} feedback"
        if title in existing_titles:
            continue
        proposals.append(
            {
                "id": _new_id(),
                "type": "experience",
                "course_offering_id": channel_map.course_offering_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "title": title,
                "summary": f"Students mention {topic} in a neutral tone.",
                "tags": ["experience", topic],
                "confidence": 0.5,
                "status": "proposed",
                "evidence": evidence[:3],
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        existing_titles.add(title)

    for message in knowledge_candidates:
        title = "Knowledge: Clarified concept"
        if title in existing_titles:
            continue
        proposals.append(
            {
                "id": _new_id(),
                "type": "knowledge",
                "course_offering_id": channel_map.course_offering_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "title": title,
                "summary": sanitize_excerpt(message["content"], limit=200),
                "tags": ["knowledge"],
                "confidence": 0.45,
                "status": "proposed",
                "evidence": [
                    {
                        "message_id": message["message_id"],
                        "excerpt": sanitize_excerpt(message["content"]),
                        "metadata": {"author_id": message["author_id"], "timestamp": message["ts"]},
                    }
                ],
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        existing_titles.add(title)

    return proposals


def _recent_message(message_id: str | None, messages: Iterable[dict], cutoff: datetime) -> bool:
    if not message_id:
        return False
    for message in messages:
        if message["message_id"] != message_id:
            continue
        try:
            ts = datetime.fromisoformat(message["ts"])
        except ValueError:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts >= cutoff
    return False
