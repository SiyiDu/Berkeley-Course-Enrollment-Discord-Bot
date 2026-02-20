"""Core services for ingest, extraction, and ask."""

from __future__ import annotations

import uuid
import re
import hmac
import hashlib
import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .extractor import build_proposals
from .store import ChannelMapEntry, EngineStore
from .utils import COURSE_CODE_RE, is_experience_query, sanitize_excerpt
from memory.search import search as memory_search
from memory.ingest import ingest_message as memory_ingest


@dataclass
class AskRequest:
    query: str
    mode: str
    viewer_role: str
    scope: dict[str, Any]
    context: dict[str, Any]


class IngestService:
    def __init__(self, store: EngineStore, config: Any) -> None:
        self.store = store
        self.config = config

    def ingest_message(self, payload: dict[str, Any]) -> tuple[bool, str | None]:
        catalog = self._extract_catalog(payload)
        if catalog.get("professor_name"):
            self.store.upsert_professor(catalog["professor_name"], None)

        channel_map = self.store.get_channel_map(payload["guild_id"], payload["channel_id"])
        if not channel_map:
            offering_id = self._resolve_offering_id(catalog)
            if offering_id:
                self.store.upsert_channel_map(
                    guild_id=payload["guild_id"],
                    channel_id=payload["channel_id"],
                    course_offering_id=offering_id,
                    enabled=True,
                    scope_type="course",
                    scope_id=str(offering_id),
                    professor_id_optional=catalog.get("professor_id"),
                )
                channel_map = self.store.get_channel_map(payload["guild_id"], payload["channel_id"])

        if not channel_map and self._allow_unmapped_channel(payload["guild_id"]):
            offering_id = self._resolve_offering_id(catalog) or self._auto_offering_id(payload, catalog)
            if offering_id:
                self.store.upsert_channel_map(
                    guild_id=payload["guild_id"],
                    channel_id=payload["channel_id"],
                    course_offering_id=offering_id,
                    enabled=True,
                    scope_type="course",
                    scope_id=str(offering_id),
                    professor_id_optional=catalog.get("professor_id"),
                )
                channel_map = self.store.get_channel_map(payload["guild_id"], payload["channel_id"])

        if not channel_map or not channel_map.get("enabled"):
            return False, "channel_not_enabled"
        stored = self.store.insert_message(payload)
        if not stored:
            return False, "duplicate"
        try:
            memory_ingest(payload)
        except Exception:
            pass
        return True, None

    @staticmethod
    def _extract_catalog(payload: dict[str, Any]) -> dict[str, Any]:
        catalog = payload.get("catalog") or {}
        return {
            "course_code": payload.get("course_code") or catalog.get("course_code"),
            "term": payload.get("term") or catalog.get("term"),
            "section": payload.get("section") or catalog.get("section"),
            "professor_name": payload.get("professor_name") or catalog.get("professor_name"),
            "professor_id": payload.get("professor_id") or catalog.get("professor_id"),
            "offering_id": payload.get("offering_id") or catalog.get("offering_id"),
        }

    def _resolve_offering_id(self, catalog: dict[str, Any]) -> int | None:
        offering_id = catalog.get("offering_id")
        if offering_id:
            return int(offering_id)
        course_code = catalog.get("course_code")
        term = catalog.get("term")
        if not course_code or not term:
            return None
        professor_id = catalog.get("professor_id")
        if not professor_id and catalog.get("professor_name"):
            professor_id = self.store.upsert_professor(catalog["professor_name"], None)
        course_id = self.store.upsert_course(course_code, None)
        return self.store.upsert_course_offering(course_id, term, catalog.get("section"), professor_id)

    def _auto_offering_id(self, payload: dict[str, Any], catalog: dict[str, Any]) -> int | None:
        course_code = catalog.get("course_code") or f"AUTO-{payload['channel_id']}"
        term = catalog.get("term") or "auto"
        section = catalog.get("section")
        professor_id = catalog.get("professor_id")
        if not professor_id and catalog.get("professor_name"):
            professor_id = self.store.upsert_professor(catalog["professor_name"], None)
        course_id = self.store.upsert_course(course_code, None)
        return self.store.upsert_course_offering(course_id, term, section, professor_id)

    def _allow_unmapped_channel(self, guild_id: str) -> bool:
        if not self.config.allow_unmapped_channels:
            return False
        trusted = self.config.trusted_guild_id
        return trusted is None or str(trusted) == str(guild_id)


class ExtractionService:
    def __init__(self, store: EngineStore) -> None:
        self.store = store

    def run_job(self, job_id: int, slice_limit: int, slice_minutes: int) -> int:
        count = 0
        try:
            for channel in self.store.list_enabled_channels():
                messages = self.store.list_recent_messages(channel.channel_id, slice_limit, slice_minutes)
                if not messages:
                    continue
                existing_titles = set(self._fetch_existing_titles(channel))
                proposals = build_proposals(
                    messages=[dict(row) for row in messages],
                    channel_map=channel,
                    existing_titles=existing_titles,
                )
                for proposal in proposals:
                    self.store.insert_proposal(proposal)
                    count += 1
        except Exception as exc:
            raise
        return count

    def _fetch_existing_titles(self, channel: ChannelMapEntry) -> list[str]:
        rows = self.store._fetchall(
            """
            SELECT title FROM cards WHERE subject_type = ? AND subject_id = ?
            UNION
            SELECT title FROM proposals WHERE subject_type = ? AND subject_id = ?
            """,
            ("course", str(channel.course_offering_id), "course", str(channel.course_offering_id)),
        )
        return [row["title"] for row in rows]


class AskService:
    def __init__(self, store: EngineStore, config: Any) -> None:
        self.store = store
        self.default_guild_id = str(config.trusted_guild_id) if config.trusted_guild_id else None
        self.context_secret = config.context_token_secret
        self.context_ttl_sec = int(getattr(config, 'context_token_ttl_sec', 3600))

    def handle(self, request: AskRequest) -> dict[str, Any]:
        query = request.query.strip()
        resolved_mode = self._resolve_mode(request.mode, query)
        scope = self._resolve_scope(request.scope, query)
        if scope["disambiguation_needed"]:
            return self._build_disambiguation_response(scope, resolved_mode)
        if request.scope and scope["scope_id"] is None and scope["scope_type"] in {"course", "professor"}:
            return self._build_unresolved_scope_response(scope, resolved_mode)

        guild_id = (
            request.context.get("workspace_id")
            or request.context.get("guild_id")
            or self.default_guild_id
        )
        if not guild_id:
            return {
                "resolved": {
                    "mode": resolved_mode,
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                    "display": scope["display"],
                    "disambiguation": {"candidates": scope["candidates"]},
                },
                "resolved_scope": {
                    "type": scope["scope_type"],
                    "display": scope["display"],
                    "offering_id": scope["offering_id"],
                    "professor_id": scope["professor_id"],
                },
                "disambiguation": {
                    "needed": False,
                    "candidates": scope["candidates"],
                },
                "answer": "Guild context missing.",
                "cards": [],
                "chunks": [],
                "evidence": [],
                "experience_strength": {"signal_count": 0, "unique_authors": 0, "time_range_days": 0},
            }

        scope_type = scope["scope_type"] if scope["scope_id"] else "global"
        scope_id = scope["scope_id"] if scope["scope_id"] else "global"

        results = memory_search(str(guild_id), scope_type, str(scope_id), query, top_k=5)
        chunks_payload = []
        for row in results:
            preview = self._build_chunk_preview(row.get("text", ""))
            token = self._sign_context_token(row.get("chunk_id"), str(guild_id))
            chunks_payload.append({
                **token,
                "chunk_id": row.get("chunk_id"),
                "guild_id": row.get("guild_id"),
                "channel_id": row.get("channel_id"),
                "scope_type": row.get("scope_type"),
                "scope_id": row.get("scope_id"),
                "start_ts": row.get("start_ts"),
                "end_ts": row.get("end_ts"),
                "source_path": row.get("source_path"),
                "score": row.get("score"),
                "preview": preview,
            })

        if results:
            answer = f"Found {len(results)} relevant memory chunks."
        else:
            answer = "No relevant memory found in this scope."

        return {
            "resolved": {
                "mode": resolved_mode,
                "scope_type": scope["scope_type"],
                "scope_id": scope["scope_id"],
                "display": scope["display"],
                "disambiguation": {"candidates": scope["candidates"]},
            },
            "resolved_scope": {
                "type": scope["scope_type"],
                "display": scope["display"],
                "offering_id": scope["offering_id"],
                "professor_id": scope["professor_id"],
            },
            "disambiguation": {
                "needed": False,
                "candidates": scope["candidates"],
            },
            "answer": answer,
            "cards": [],
            "chunks": chunks_payload,
            "evidence": [],
            "experience_strength": {"signal_count": 0, "unique_authors": 0, "time_range_days": 0},
        }

    def _sign_context_token(self, chunk_id: str, guild_id: str) -> dict[str, str]:
        if not self.context_secret:
            return {}
        exp = int(time.time()) + self.context_ttl_sec
        payload = f"{chunk_id}:{guild_id}:{exp}"
        sig = hmac.new(self.context_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        token = f"{exp}." + base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
        return {"context_token": token, "context_expires_at": exp}

    def _resolve_mode(self, mode: str, query: str) -> str:
        if mode in {"knowledge", "experience"}:
            return mode
        return "experience" if is_experience_query(query) else "knowledge"

    def _parse_chunk_lines(self, text: str) -> list[dict[str, str]]:
        lines = []
        pattern = re.compile(r"^\[(?P<ts>.+?)\] \((?P<message_id>.+?)\) (?P<author_id>.+?): (?P<content>.*)$")
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            match = pattern.match(raw)
            if not match:
                continue
            lines.append(match.groupdict())
        return lines

    def _anonymize_lines(self, lines: list[dict[str, str]]) -> list[dict[str, str]]:
        mapping: dict[str, str] = {}
        mention_re = re.compile(r"<@!?(\d+)>")

        def label(user_id: str) -> str:
            if user_id not in mapping:
                mapping[user_id] = f"User{len(mapping) + 1}"
            return mapping[user_id]

        anonymized = []
        for line in lines:
            author_id = line.get("author_id", "")
            author_label = label(author_id) if author_id else "User"
            content = line.get("content", "")

            def repl(match: re.Match) -> str:
                return f"@{label(match.group(1))}"

            content = mention_re.sub(repl, content)
            anonymized.append({
                "ts": line.get("ts", ""),
                "message_id": line.get("message_id", ""),
                "author": author_label,
                "content": content,
            })
        return anonymized

    def _build_chunk_preview(self, text: str, limit: int = 4) -> list[dict[str, str]]:
        lines = self._parse_chunk_lines(text)
        return self._anonymize_lines(lines[:limit])

    def _resolve_scope(self, scope: dict[str, Any], query: str) -> dict[str, Any]:
        scope_type = (scope.get("type") or "auto").lower()
        candidates: list[dict[str, Any]] = []
        offering_id = None
        professor_id = None

        if scope.get("offering_id"):
            offering = self.store.get_offering(int(scope["offering_id"]))
            if offering:
                offering_id = str(offering["id"])
                scope_type = "course"
                display = self._format_offering_display(offering)
                return {
                    "scope_type": "course",
                    "scope_id": offering_id,
                    "display": display,
                    "candidates": [],
                    "offering_id": offering_id,
                    "professor_id": str(offering.get("professor_id")) if offering.get("professor_id") else None,
                    "disambiguation_needed": False,
                }

        if scope.get("course_code"):
            offerings = self.store.resolve_offerings(
                scope["course_code"],
                scope.get("term"),
                scope.get("section"),
            )
            if len(offerings) == 1:
                offering = offerings[0]
                offering_id = str(offering["id"])
                display = self._format_offering_display(offering)
                return {
                    "scope_type": "course",
                    "scope_id": offering_id,
                    "display": display,
                    "candidates": [],
                    "offering_id": offering_id,
                    "professor_id": str(offering.get("professor_id")) if offering.get("professor_id") else None,
                    "disambiguation_needed": False,
                }
            candidates.extend(self._offerings_to_candidates(offerings))

        if scope.get("professor_id"):
            professor = self.store.get_professor(int(scope["professor_id"]))
            if professor:
                professor_id = str(professor["id"])
                return {
                    "scope_type": "professor",
                    "scope_id": professor_id,
                    "display": professor["name"],
                    "candidates": [],
                    "offering_id": None,
                    "professor_id": professor_id,
                    "disambiguation_needed": False,
                }

        if scope.get("professor_name"):
            professors = self.store.find_professors_by_name(scope["professor_name"])
            if len(professors) == 1:
                professor_id = str(professors[0]["id"])
                return {
                    "scope_type": "professor",
                    "scope_id": professor_id,
                    "display": professors[0]["name"],
                    "candidates": [],
                    "offering_id": None,
                    "professor_id": professor_id,
                    "disambiguation_needed": False,
                }
            candidates.extend(self._professors_to_candidates(professors))

        if scope_type == "auto":
            candidates.extend(self._offerings_to_candidates(self._find_course_candidates(query)))
            candidates.extend(self._professors_to_candidates(self._find_professor_candidates(query)))

        if len(candidates) > 1:
            return {
                "scope_type": scope_type,
                "scope_id": None,
                "display": "Ambiguous scope",
                "candidates": candidates,
                "offering_id": None,
                "professor_id": None,
                "disambiguation_needed": True,
            }

        if len(candidates) == 1:
            candidate = candidates[0]
            scope_type = candidate["type"]
            scope_id = str(candidate.get("offering_id") or candidate.get("professor_id"))
            return {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "display": candidate["display"],
                "candidates": [],
                "offering_id": str(candidate.get("offering_id")) if candidate.get("offering_id") else None,
                "professor_id": str(candidate.get("professor_id")) if candidate.get("professor_id") else None,
                "disambiguation_needed": False,
            }

        return {
            "scope_type": scope_type if scope_type != "auto" else "course",
            "scope_id": None,
            "display": "All",
            "candidates": [],
            "offering_id": None,
            "professor_id": None,
            "disambiguation_needed": False,
        }

    def _find_course_candidates(self, query: str) -> list[dict[str, Any]]:
        matches = COURSE_CODE_RE.findall(query)
        codes = []
        for dept, number in matches:
            dept_up = dept.upper()
            normalized = f"{dept_up}{number.upper()}"
            codes.append(normalized)
            if dept_up == "CS":
                codes.append(f"COMPSCI{number.upper()}")
        results: list[dict[str, Any]] = []
        for code in codes:
            offerings = self.store.find_offerings_by_course_code(code)
            results.extend(offerings)
        return results

    def _find_professor_candidates(self, query: str) -> list[dict[str, Any]]:
        lowered = query.lower()
        rows = self.store.list_professors()
        matches = []
        for row in rows:
            name = row["name"]
            if not name:
                continue
            name_lower = name.lower()
            if name_lower in lowered:
                matches.append(row)
                continue
            tokens = [token for token in name_lower.split() if len(token) >= 3]
            if any(token in lowered for token in tokens):
                matches.append(row)
        return matches

    def _offerings_to_candidates(self, offerings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for offering in offerings:
            candidates.append(
                {
                    "type": "course",
                    "display": self._format_offering_display(offering),
                    "offering_id": offering["id"],
                    "professor_id": offering.get("professor_id"),
                }
            )
        return candidates

    def _professors_to_candidates(self, professors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"type": "professor", "display": prof["name"], "professor_id": prof["id"]}
            for prof in professors
        ]

    @staticmethod
    def _format_offering_display(offering: dict[str, Any]) -> str:
        display = offering.get("course_code", "Course")
        suffix = []
        term = offering.get("term")
        section = offering.get("section_optional")
        if term:
            suffix.append(term.upper())
        if section:
            suffix.append(section)
        professor = offering.get("professor_name")
        if professor:
            suffix.append(professor)
        if suffix:
            display = f"{display} ({' '.join(suffix)})"
        return display

    def _build_disambiguation_response(self, scope: dict[str, Any], mode: str) -> dict[str, Any]:
        return {
            "resolved": {
                "mode": mode,
                "scope_type": scope["scope_type"],
                "scope_id": None,
                "display": scope["display"],
                "disambiguation": {"candidates": scope["candidates"]},
            },
            "resolved_scope": {
                "type": scope["scope_type"],
                "display": scope["display"],
                "offering_id": None,
                "professor_id": None,
            },
            "disambiguation": {
                "needed": True,
                "candidates": scope["candidates"],
            },
            "answer": "Scope is ambiguous. Please select a course or professor.",
            "cards": [],
            "evidence": [],
            "experience_strength": {"signal_count": 0, "unique_authors": 0, "time_range_days": 0},
        }

    def _build_unresolved_scope_response(self, scope: dict[str, Any], mode: str) -> dict[str, Any]:
        return {
            "resolved": {
                "mode": mode,
                "scope_type": scope["scope_type"],
                "scope_id": None,
                "display": scope["display"],
                "disambiguation": {"candidates": scope["candidates"]},
            },
            "resolved_scope": {
                "type": scope["scope_type"],
                "display": scope["display"],
                "offering_id": None,
                "professor_id": None,
            },
            "disambiguation": {
                "needed": False,
                "candidates": scope["candidates"],
            },
            "answer": "Scope could not be resolved. Please provide a valid course or professor.",
            "cards": [],
            "evidence": [],
            "experience_strength": {"signal_count": 0, "unique_authors": 0, "time_range_days": 0},
        }

    def _build_answer(self, cards: list[dict[str, Any]], mode: str) -> str:
        if not cards:
            return "No reliable evidence found in approved cards."
        highlights = "; ".join(card["summary"] for card in cards[:2])
        if mode == "experience":
            return f"Based on verified experience summaries: {highlights}"
        return f"Based on verified cards: {highlights}"

    def _collect_evidence(
        self, cards: list[dict[str, Any]], mode: str, viewer_role: str
    ) -> list[dict[str, Any]]:
        if mode == "experience" and viewer_role == "student":
            return []
        evidence: list[dict[str, Any]] = []
        for card in cards:
            for item in card.get("evidence", [])[:3]:
                evidence.append(
                    {
                        "card_id": card["id"],
                        "excerpt": sanitize_excerpt(item.get("excerpt", "")),
                        "metadata": item.get("metadata", {}),
                        "strength": "med",
                    }
                )
        return evidence[:5]

    def _experience_strength(self, cards: list[dict[str, Any]]) -> dict[str, int]:
        message_ids: list[str] = []
        for card in cards:
            for item in card.get("evidence", []):
                if item.get("message_id"):
                    message_ids.append(item["message_id"])
        messages = self.store.fetch_messages_by_ids(message_ids)
        unique_authors = {msg["author_id"] for msg in messages}
        timestamps = []
        for msg in messages:
            try:
                ts = datetime.fromisoformat(msg["ts"])
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            timestamps.append(ts)
        time_range = 0
        if timestamps:
            time_range = int((max(timestamps) - min(timestamps)).total_seconds() // 86400)
        return {
            "signal_count": len(message_ids),
            "unique_authors": len(unique_authors),
            "time_range_days": time_range,
        }


def make_proposal_id() -> str:
    return uuid.uuid4().hex


def build_evidence(message_id: str, content: str) -> list[dict[str, str]]:
    return [
        {
            "message_id": message_id,
            "excerpt": sanitize_excerpt(content),
            "metadata": {},
        }
    ]
