"""Minimal Python client for the Berkeley engine."""

from __future__ import annotations

import json
from typing import Any
from urllib import request


class EngineClient:
    def __init__(self, base_url: str, client_id: str | None = None, client_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_token = client_token

    def ingest_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self.client_id and self.client_token:
            headers["X-CLIENT-ID"] = self.client_id
            headers["X-CLIENT-TOKEN"] = self.client_token
        return self._request("POST", "/api/ingest/message", payload, headers)

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/ask", payload, {})

    def _request(self, method: str, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
        with request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
