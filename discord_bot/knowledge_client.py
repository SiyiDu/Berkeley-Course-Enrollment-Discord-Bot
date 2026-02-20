"""HTTP client for the knowledge engine API."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx


class KnowledgeClient:
    def __init__(self, base_url: str, client_id: str, client_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_token = client_token
        self.timeout = float(os.getenv("ENGINE_HTTP_TIMEOUT", "10"))
        self.max_retries = int(os.getenv("ENGINE_HTTP_MAX_RETRIES", "3"))
        self.retry_backoff_sec = float(os.getenv("ENGINE_HTTP_RETRY_BACKOFF_SEC", "0.5"))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method,
                        f"{self.base_url}{path}",
                        json=json_body,
                        headers=headers,
                    )
                if response.status_code in {502, 503, 504} and attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_sec * attempt)
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(self.retry_backoff_sec * attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("Request failed without exception")

    async def ask(
        self,
        query: str,
        viewer_role: str,
        source: str,
        workspace_id: str | None,
        channel_id: str | None,
        discord_user_id: str | None,
        scope: dict[str, Any] | None = None,
        mode: str = "auto",
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "mode": mode,
            "viewer_role": viewer_role,
            "scope": scope or {},
            "context": {
                "platform": source,
                "workspace_id": workspace_id,
                "channel_id": channel_id,
                "user_id": discord_user_id,
            },
        }
        response = await self._request("POST", "/api/ask", json_body=payload)
        return response.json()

    async def ingest_message(self, payload: dict[str, Any]) -> None:
        await self._request(
            "POST",
            "/api/ingest/message",
            json_body=payload,
            headers={
                "X-CLIENT-ID": self.client_id,
                "X-CLIENT-TOKEN": self.client_token,
            },
        )
