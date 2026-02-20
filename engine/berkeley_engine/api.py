"""FastAPI app for the knowledge engine."""

from __future__ import annotations

import logging
import re
import hmac
import hashlib
import base64
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import load_engine_config
from .services import AskRequest, AskService, ExtractionService, IngestService
from .store import EngineStore
from memory.db import MemoryDB
from memory.config import load_memory_config
from memory.ingest import force_chunking
from shared.db import Database


class IngestMessage(BaseModel):
    guild_id: str | None = None
    channel_id: str
    message_id: str
    author_id: str
    content: str
    timestamp: str
    platform: str | None = None
    workspace_id: str | None = None
    permalink: str | None = None
    course_code: str | None = None
    term: str | None = None
    section: str | None = None
    professor_name: str | None = None
    professor_id: int | None = None
    offering_id: int | None = None
    author_name: str | None = None
    reply_to_message_id: str | None = None
    attachments: list[Any] | None = None
    message_url: str | None = None


class AskPayload(BaseModel):
    query: str
    override_mode: str | None = "auto"
    mode: str | None = None
    viewer_role: str | None = "student"
    scope: dict[str, Any] | None = Field(default_factory=dict)
    context: dict[str, Any] | None = Field(default_factory=dict)


class ProposalEdits(BaseModel):
    title: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    confidence: float | None = None


class MergePayload(BaseModel):
    card_id: str | None = None


class ClientCreate(BaseModel):
    client_id: str | None = None
    client_token: str | None = None
    name: str | None = None
    allowed_platforms: list[str] | None = None
    allowed_workspaces: list[str] | None = None


class ClientRotate(BaseModel):
    client_token: str | None = None


class AdminLogin(BaseModel):
    username: str
    password: str


class ChannelMapRequest(BaseModel):
    guild_id: str
    channel_id: str
    course_offering_id: int
    scope_type: str | None = None
    scope_id: str | None = None
    professor_id_optional: int | None = None
    enabled: bool = True


class ProfessorRequest(BaseModel):
    name: str
    dept_optional: str | None = None


class CourseOfferingRequest(BaseModel):
    term: str
    course_code: str
    section_optional: str | None = None
    professor_id_optional: int | None = None
    professor_name_optional: str | None = None


app = FastAPI()
config = load_engine_config()

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)


def _redact_db_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.password:
            safe_netloc = parsed.netloc.replace(parsed.password, "****")
            return parsed._replace(netloc=safe_netloc).geturl()
        return url
    except Exception:
        return url


db = Database(
    config.database_url,
    connect_timeout=config.db_connect_timeout,
    max_retries=config.db_max_retries,
    retry_backoff_sec=config.db_retry_backoff_sec,
)
store = EngineStore(db)
ingest_service = IngestService(store, config)
ask_service = AskService(store, config)
extract_service = ExtractionService(store)

web_root = Path(__file__).resolve().parents[2] / "web"
static_root = web_root / "static"
if static_root.exists():
    app.mount("/static", StaticFiles(directory=static_root, html=False), name="static")


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or x_admin_token != config.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    logging.info("Engine start DB=%s", _redact_db_url(config.database_url))
    logging.info("Engine host=%s port=%s env=%s", config.api_host, config.api_port, config.env)
    logging.info("LLM mode=%s", "enabled" if config.llm_enabled else "mocked")
    logging.info("Jobs inline=%s", config.run_jobs_inline)
    mem_config = load_memory_config()
    logging.info("Memory backend=%s enabled=%s", mem_config.backend, mem_config.enabled)


@app.middleware("http")
async def log_requests(request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logging.exception(
            "request_failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    logging.info(
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def _run_extraction_job(job_id: int) -> None:
    try:
        store.update_job(job_id, "running", increment_attempts=True)
        extract_service.run_job(job_id, config.slice_limit, config.slice_minutes)
        store.update_job(job_id, "completed")
    except Exception as exc:
        current = store.get_job(job_id) or {}
        attempts = int(current.get("attempts") or 0)
        if attempts < 3:
            delay = min(120, 5 * (2 ** max(0, attempts - 1)))
            store.requeue_job(job_id, delay_seconds=delay, last_error=str(exc))
            logging.warning("Extraction job %s failed; requeued in %ss", job_id, delay)
        else:
            store.update_job(job_id, "failed", last_error=str(exc))
            logging.exception("Extraction job %s failed: %s", job_id, exc)


@app.get("/")
def root() -> FileResponse:
    index = web_root / "ask" / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="web/index.html missing")
    return FileResponse(index)


@app.get("/ask")
def ask_page() -> FileResponse:
    return root()


def _verify_context_token(chunk_id: str, guild_id: str, token: str) -> bool:
    if not config.context_token_secret or not token:
        return False
    try:
        exp_str, sig_b64 = token.split(".", 1)
        exp = int(exp_str)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{chunk_id}:{guild_id}:{exp}"
    sig = hmac.new(config.context_token_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return hmac.compare_digest(expected, sig_b64)


def _authorize_ingest(
    client_id: str | None,
    client_token: str | None,
    legacy_token: str | None,
    platform: str | None,
    workspace_id: str | None,
) -> None:
    if client_id or client_token:
        if not client_id or not client_token:
            raise HTTPException(status_code=401, detail="Missing client credentials")
        client = store.get_client(client_id)
        if not client or client.get("revoked"):
            raise HTTPException(status_code=401, detail="Invalid client credentials")
        if client_token != client.get("client_token"):
            raise HTTPException(status_code=401, detail="Invalid client credentials")
        allowed_platforms = client.get("allowed_platforms", [])
        if allowed_platforms and (not platform or platform not in allowed_platforms):
            raise HTTPException(status_code=403, detail="Platform not allowed")
        allowed_workspaces = client.get("allowed_workspaces", [])
        if allowed_workspaces and (not workspace_id or workspace_id not in allowed_workspaces):
            raise HTTPException(status_code=403, detail="Workspace not allowed")
        return

    if not legacy_token or legacy_token != config.ingest_token:
        raise HTTPException(status_code=401, detail="Invalid bot token")


@app.get("/api/health")
def health() -> dict[str, Any]:
    db_ok = store.ping()
    status = "ok" if db_ok else "error"
    mem_config = load_memory_config()
    return {
        "status": status,
        "db_ok": db_ok,
        "version": __version__,
        "env": config.env,
        "memory_enabled": mem_config.enabled and mem_config.backend == "filesystem",
    }


@app.get("/api/ready")
def ready() -> dict[str, Any]:
    db_ok = store.ping()
    status = "ready" if db_ok else "degraded"
    mem_config = load_memory_config()
    return {
        "status": status,
        "db_ok": db_ok,
        "version": __version__,
        "env": config.env,
        "memory_enabled": mem_config.enabled and mem_config.backend == "filesystem",
    }


@app.get("/admin")
def admin_page() -> FileResponse:
    index = web_root / "admin" / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="web/admin.html missing")
    return FileResponse(index)


@app.post("/api/ingest/message")
def ingest_message(
    payload: IngestMessage,
    x_client_id: str | None = Header(default=None),
    x_client_token: str | None = Header(default=None),
    x_bot_token: str | None = Header(default=None),
) -> dict[str, Any]:
    workspace_id = payload.workspace_id or payload.guild_id
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id or guild_id required")

    _authorize_ingest(
        client_id=x_client_id,
        client_token=x_client_token,
        legacy_token=x_bot_token,
        platform=payload.platform,
        workspace_id=workspace_id,
    )

    raw_payload = payload.model_dump()
    raw_payload["guild_id"] = workspace_id
    raw_payload["raw_json_optional"] = {
        "author_name": payload.author_name,
        "reply_to_message_id": payload.reply_to_message_id,
        "attachments": payload.attachments,
        "message_url": payload.message_url,
        "platform": payload.platform,
        "workspace_id": payload.workspace_id,
        "permalink": payload.permalink or payload.message_url,
        "catalog": {
            "course_code": payload.course_code,
            "term": payload.term,
            "section": payload.section,
            "professor_name": payload.professor_name,
            "professor_id": payload.professor_id,
            "offering_id": payload.offering_id,
        },
    }
    stored, reason = ingest_service.ingest_message(raw_payload)
    store.insert_audit(
        "ingest_message",
        {"accepted": stored, "reason": reason, "message_id": payload.message_id},
    )
    if not stored and reason == "channel_not_enabled":
        raise HTTPException(status_code=403, detail=reason)
    return {"ok": True, "stored": stored, "reason": reason}


def _anonymize_messages(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    mention_re = re.compile(r"<@!?(\d+)>")

    def label(user_id: str) -> str:
        if user_id not in mapping:
            mapping[user_id] = f"User{len(mapping) + 1}"
        return mapping[user_id]

    anonymized = []
    for record in records:
        author_id = record.get("author_id", "")
        author_label = label(author_id) if author_id else "User"
        content = record.get("content", "")

        def repl(match: re.Match) -> str:
            return f"@{label(match.group(1))}"

        content = mention_re.sub(repl, content)
        anonymized.append({
            "message_id": record.get("message_id", ""),
            "ts": record.get("ts", ""),
            "author": author_label,
            "content": content,
        })
    return anonymized


@app.post("/api/ask")
def ask(payload: AskPayload) -> dict[str, Any]:
    request = AskRequest(
        query=payload.query,
        mode=payload.mode or payload.override_mode or "auto",
        viewer_role=payload.viewer_role or "student",
        scope=payload.scope or {},
        context=payload.context or {},
    )
    return ask_service.handle(request)


@app.get("/api/messages/context")
def get_message_context(
    chunk_id: str,
    guild_id: str | None = None,
    days: int = 1,
    limit: int = 300,
    offset: int = 0,
) -> dict[str, Any]:
    mem_config = load_memory_config()
    if not mem_config.enabled or mem_config.backend != "filesystem":
        raise HTTPException(status_code=503, detail="Memory backend disabled")
    resolved_guild = guild_id or (str(config.trusted_guild_id) if config.trusted_guild_id else None)
    if not resolved_guild:
        raise HTTPException(status_code=400, detail="guild_id required")

    mem_db = MemoryDB(str(resolved_guild))
    chunk = mem_db.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    try:
        start_ts = datetime.fromisoformat(chunk["start_ts"])
    except ValueError:
        start_ts = datetime.now(timezone.utc)
    try:
        end_ts = datetime.fromisoformat(chunk["end_ts"])
    except ValueError:
        end_ts = datetime.now(timezone.utc)

    if start_ts.tzinfo is None:
        start_ts = start_ts.replace(tzinfo=timezone.utc)
    if end_ts.tzinfo is None:
        end_ts = end_ts.replace(tzinfo=timezone.utc)

    window_start = start_ts - timedelta(days=days)
    window_end = end_ts + timedelta(days=days)

    total = store.count_messages_in_window(
        str(resolved_guild),
        str(chunk["channel_id"]),
        window_start.isoformat(),
        window_end.isoformat(),
    )
    records = store.list_messages_in_window(
        str(resolved_guild),
        str(chunk["channel_id"]),
        window_start.isoformat(),
        window_end.isoformat(),
        limit=limit,
        offset=offset,
    )
    messages = _anonymize_messages(records)

    return {
        "chunk": {
            "chunk_id": chunk.get("chunk_id"),
            "channel_id": chunk.get("channel_id"),
            "scope_type": chunk.get("scope_type"),
            "scope_id": chunk.get("scope_id"),
            "start_ts": chunk.get("start_ts"),
            "end_ts": chunk.get("end_ts"),
            "source_path": chunk.get("source_path"),
        },
        "range": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "days": days,
        },
        "messages": messages,
        "total": total,
        "truncated": total > (offset + len(messages)),
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/cards/search")
def search_cards(
    subject_type: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    card_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict[str, Any]:
    types = [card_type] if card_type else ["knowledge", "resource", "faq", "experience"]
    return {"cards": store.search_cards(types, subject_type, subject_id, query=q)}


@app.get("/api/cards/{card_id}")
def get_card(card_id: str) -> dict[str, Any]:
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/api/catalog/courses")
def list_courses() -> dict[str, Any]:
    return {"courses": store.list_courses()}


@app.get("/api/catalog/offerings")
def list_offerings() -> dict[str, Any]:
    return {"offerings": store.list_course_offerings()}


@app.get("/api/catalog/professors")
def list_professors() -> dict[str, Any]:
    return {"professors": store.list_professors()}


@app.post("/api/admin/config/channel_map")
def upsert_channel_map(
    payload: ChannelMapRequest, _: None = Depends(require_admin_token)
) -> dict[str, Any]:
    entry_id = store.upsert_channel_map(
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        course_offering_id=payload.course_offering_id,
        enabled=payload.enabled,
        scope_type=payload.scope_type or "course",
        scope_id=payload.scope_id or str(payload.course_offering_id),
        professor_id_optional=payload.professor_id_optional,
    )
    return {"ok": True, "id": entry_id}


@app.post("/api/admin/config/professor")
def upsert_professor(payload: ProfessorRequest, _: None = Depends(require_admin_token)) -> dict[str, Any]:
    professor_id = store.upsert_professor(payload.name, payload.dept_optional)
    return {"ok": True, "id": professor_id}


@app.post("/api/admin/config/course_offering")
def upsert_course_offering(
    payload: CourseOfferingRequest, _: None = Depends(require_admin_token)
) -> dict[str, Any]:
    course_id = store.upsert_course(payload.course_code, None)
    professor_id = payload.professor_id_optional
    if payload.professor_name_optional:
        professor_id = store.upsert_professor(payload.professor_name_optional, None)
    offering_id = store.upsert_course_offering(
        course_id=course_id,
        term=payload.term,
        section_optional=payload.section_optional,
        professor_id_optional=professor_id,
    )
    return {"ok": True, "id": offering_id}


@app.get("/api/admin/proposals")
def list_proposals(
    status: str | None = Query(default="proposed"),
    proposal_type: str | None = Query(default=None),
    _: None = Depends(require_admin_token),
) -> dict[str, Any]:
    proposals = store.list_proposals(status=status, proposal_type=proposal_type)
    return {"proposals": proposals}


@app.get("/api/admin/jobs")
def list_jobs(_: None = Depends(require_admin_token)) -> dict[str, Any]:
    return {"jobs": store.list_jobs()}


@app.get("/api/admin/clients")
def list_clients(_: None = Depends(require_admin_token)) -> dict[str, Any]:
    return {"clients": store.list_clients()}


@app.post("/api/admin/login")
def admin_login(payload: AdminLogin) -> dict[str, Any]:
    if payload.username != config.admin_username or payload.password != config.admin_password:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    return {"token": config.admin_token}


@app.post("/api/admin/clients")
def create_client(payload: ClientCreate, _: None = Depends(require_admin_token)) -> dict[str, Any]:
    client_id = payload.client_id or f"client_{__version__}_{uuid4().hex[:8]}"
    existing = store.get_client(client_id)
    if existing:
        raise HTTPException(status_code=409, detail="Client already exists")
    client_token = payload.client_token or uuid4().hex
    store.create_client(
        client_id=client_id,
        client_token=client_token,
        name=payload.name,
        allowed_platforms=payload.allowed_platforms,
        allowed_workspaces=payload.allowed_workspaces,
    )
    store.insert_audit("client_create", {"client_id": client_id})
    return {"client_id": client_id, "client_token": client_token}


@app.post("/api/admin/clients/{client_id}/rotate")
def rotate_client(
    client_id: str, payload: ClientRotate | None = None, _: None = Depends(require_admin_token)
) -> dict[str, Any]:
    new_token = payload.client_token if payload and payload.client_token else uuid4().hex
    ok = store.update_client_token(client_id, new_token)
    if not ok:
        raise HTTPException(status_code=404, detail="Client not found")
    store.insert_audit("client_rotate", {"client_id": client_id})
    return {"client_id": client_id, "client_token": new_token}


@app.post("/api/admin/clients/{client_id}/revoke")
def revoke_client(client_id: str, _: None = Depends(require_admin_token)) -> dict[str, Any]:
    ok = store.revoke_client(client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Client not found")
    store.insert_audit("client_revoke", {"client_id": client_id})
    return {"ok": True}


@app.post("/api/admin/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    edits: ProposalEdits | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, Any]:
    card_id = store.approve_proposal(proposal_id, edits.model_dump() if edits else None, approved_by="admin")
    if not card_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    store.insert_audit("proposal_approve", {"proposal_id": proposal_id, "card_id": card_id})
    return {"ok": True, "card_id": card_id}


@app.post("/api/admin/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, _: None = Depends(require_admin_token)) -> dict[str, Any]:
    ok = store.reject_proposal(proposal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Proposal not found")
    store.insert_audit("proposal_reject", {"proposal_id": proposal_id})
    return {"ok": True}


@app.post("/api/admin/proposals/{proposal_id}/merge")
def merge_proposal(
    proposal_id: str,
    payload: MergePayload | None = None,
    card_id: str | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, Any]:
    target_card_id = payload.card_id if payload and payload.card_id else card_id
    ok = store.merge_proposal(proposal_id, target_card_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Proposal not found")
    store.insert_audit("proposal_merge", {"proposal_id": proposal_id, "card_id": target_card_id})
    return {"ok": True}


@app.post("/api/admin/memory/flush")
def admin_memory_flush(
    guild_id: str | None = None,
    limit_per_channel: int = 200,
    _: None = Depends(require_admin_token),
) -> dict[str, Any]:
    resolved_guild = guild_id or (str(config.trusted_guild_id) if config.trusted_guild_id else None)
    if not resolved_guild:
        raise HTTPException(status_code=400, detail="guild_id required")
    summary = force_chunking(str(resolved_guild), limit_per_channel=limit_per_channel)
    return {"ok": True, "channels": len(summary), "messages_chunked": sum(summary.values()), "summary": summary}


@app.post("/api/admin/jobs/extract")
def run_extraction(
    background_tasks: BackgroundTasks, _: None = Depends(require_admin_token)
) -> dict[str, Any]:
    existing = store.find_active_job("extract_cycle")
    if existing:
        return {"ok": True, "job_id": existing["id"], "status": existing["status"]}
    job_id = store.create_job(
        "extract_cycle",
        {"slice_limit": config.slice_limit, "slice_minutes": config.slice_minutes},
        status="queued",
    )
    if config.run_jobs_inline:
        background_tasks.add_task(_run_extraction_job, job_id)
    return {"ok": True, "job_id": job_id, "status": "queued"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("engine.berkeley_engine.api:app", host=config.api_host, port=config.api_port, reload=False)
