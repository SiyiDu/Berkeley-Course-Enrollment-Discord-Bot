"""Replay demo workflow: ingest -> extract -> approve -> ask."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_engine_config


@dataclass
class DemoConfig:
    base_url: str
    ingest_token: str
    admin_token: str


def _request(method: str, url: str, headers: dict[str, str] | None = None, body: Any | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload)


def main() -> None:
    config = load_engine_config()
    demo = DemoConfig(
        base_url=f"http://{config.api_host}:{config.api_port}",
        ingest_token=config.ingest_token,
        admin_token=config.admin_token,
    )

    print("1) Ask with no approved cards")
    empty = _request(
        "POST",
        f"{demo.base_url}/api/ask",
        body={"query": "CS61B autograder tips", "override_mode": "auto", "viewer_role": "student"},
    )
    print("Cards returned:", len(empty.get("cards", [])))

    print("2) Seed minimal catalog and whitelist")
    professor = _request(
        "POST",
        f"{demo.base_url}/api/admin/config/professor",
        headers={"X-ADMIN-TOKEN": demo.admin_token},
        body={"name": "Demo Professor"},
    )
    offering = _request(
        "POST",
        f"{demo.base_url}/api/admin/config/course_offering",
        headers={"X-ADMIN-TOKEN": demo.admin_token},
        body={"term": "fa25", "course_code": "CS61B", "section_optional": "001", "professor_id_optional": professor["id"]},
    )
    _request(
        "POST",
        f"{demo.base_url}/api/admin/config/channel_map",
        headers={"X-ADMIN-TOKEN": demo.admin_token},
        body={
            "guild_id": "demo",
            "channel_id": "demo-channel",
            "course_offering_id": offering["id"],
            "enabled": True,
        },
    )

    print("3) Ingest a message")
    message_id = f"demo-{uuid4().hex[:8]}"
    _request(
        "POST",
        f"{demo.base_url}/api/ingest/message",
        headers={"X-BOT-TOKEN": demo.ingest_token},
        body={
            "platform": "demo",
            "guild_id": "demo",
            "workspace_id": "demo",
            "channel_id": "demo-channel",
            "message_id": message_id,
            "author_id": "demo-user",
            "content": "Resource: https://example.com/autograder tips and prep checklist.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    print("4) Extract proposals")
    _request(
        "POST",
        f"{demo.base_url}/api/admin/jobs/extract",
        headers={"X-ADMIN-TOKEN": demo.admin_token},
        body={},
    )

    proposals: list[dict] = []
    for _ in range(10):
        time.sleep(0.5)
        payload = _request(
            "GET",
            f"{demo.base_url}/api/admin/proposals?status=proposed",
            headers={"X-ADMIN-TOKEN": demo.admin_token},
        )
        proposals = payload.get("proposals", [])
        if proposals:
            break

    if not proposals:
        print("No proposals created.")
        return

    proposal_id = proposals[0]["id"]
    print("5) Approve proposal", proposal_id)
    _request(
        "POST",
        f"{demo.base_url}/api/admin/proposals/{proposal_id}/approve",
        headers={"X-ADMIN-TOKEN": demo.admin_token},
        body={},
    )

    print("6) Ask again after approval")
    answered = _request(
        "POST",
        f"{demo.base_url}/api/ask",
        body={"query": "CS61B autograder tips", "override_mode": "auto", "viewer_role": "student"},
    )
    print("Cards returned:", len(answered.get("cards", [])))


if __name__ == "__main__":
    main()
