"""Ingest JSONL fixture messages into the running engine."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .config import load_engine_config


def _iter_messages(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    config = load_engine_config()
    parser = argparse.ArgumentParser(description="Ingest JSONL fixture messages.")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(__file__).resolve().parent / "fixtures" / "virtual_discord_messages.jsonl",
    )
    parser.add_argument(
        "--base-url",
        default=f"http://{config.api_host}:{config.api_port}",
    )
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--client-token", default=None)
    parser.add_argument("--bot-token", default=config.ingest_token)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"Fixture file not found: {args.path}")
        return 1

    headers: dict[str, str] = {}
    if args.client_id or args.client_token:
        if not args.client_id or not args.client_token:
            print("Both --client-id and --client-token are required together.")
            return 1
        headers["X-CLIENT-ID"] = args.client_id
        headers["X-CLIENT-TOKEN"] = args.client_token
    else:
        headers["X-BOT-TOKEN"] = args.bot_token

    url = f"{args.base_url}/api/ingest/message"
    total = 0
    ok = 0
    for payload in _iter_messages(args.path):
        total += 1
        status, body = _post(url, payload, headers)
        if status == 200:
            ok += 1
        else:
            print(f"[{status}] {payload.get('message_id')}: {body}")
        if args.limit and total >= args.limit:
            break

    print(f"Ingested {ok}/{total} messages.")
    if ok == 0:
        print("If you see 403, add channel_map entries before ingesting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
