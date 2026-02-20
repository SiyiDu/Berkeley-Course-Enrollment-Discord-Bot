"""Seed demo data and run lightweight API checks for the web UI flow."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import load_engine_config
from .demo_fixtures import main as seed_demo_fixtures


def _request(method: str, url: str, body: Any | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def _print_result(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")


def main() -> None:
    config = load_engine_config()
    base_url = f"http://{config.api_host}:{config.api_port}"

    print("Seeding demo fixtures...")
    seed_demo_fixtures()

    try:
        _request("GET", f"{base_url}/api/health")
    except urllib.error.URLError:
        print("Engine not reachable. Start it with: python -m engine.berkeley_engine.api")
        return

    professors = _request("GET", f"{base_url}/api/catalog/professors").get("professors", [])
    has_josh = any(row.get("name") == "Josh Hug" for row in professors)
    _print_result("Professor suggestions", has_josh, "Josh Hug present" if has_josh else "Missing Josh Hug")

    ask_professor = _request(
        "POST",
        f"{base_url}/api/ask",
        body={
            "query": "workload",
            "override_mode": "experience",
            "viewer_role": "student",
            "scope": {"type": "professor", "professor_name": "Josh Hug"},
        },
    )
    prof_cards = ask_professor.get("cards", [])
    prof_scope = ask_professor.get("resolved_scope", {}).get("type") == "professor"
    prof_evidence = ask_professor.get("evidence", [])
    _print_result(
        "Professor ask (experience)",
        bool(prof_cards) and prof_scope and not prof_evidence,
        f"cards={len(prof_cards)} evidence={len(prof_evidence)} scope_professor={prof_scope}",
    )

    ask_course = _request(
        "POST",
        f"{base_url}/api/ask",
        body={
            "query": "resources",
            "override_mode": "knowledge",
            "viewer_role": "student",
            "scope": {"type": "course", "course_code": "CS61B", "term": "2026-spring"},
        },
    )
    course_cards = ask_course.get("cards", [])
    course_evidence = ask_course.get("evidence", [])
    _print_result(
        "Course ask (knowledge)",
        bool(course_cards) and bool(course_evidence),
        f"cards={len(course_cards)} evidence={len(course_evidence)}",
    )


if __name__ == "__main__":
    main()
