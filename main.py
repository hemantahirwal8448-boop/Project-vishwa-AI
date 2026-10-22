"""Project Vishwa AI — starter MVP. Real model calls are optional and configured server-side."""
from __future__ import annotations
import os
import time
import uuid
from urllib.parse import urlsplit
from collections import defaultdict, deque
from threading import Lock
from contextlib import contextmanager
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader
import io
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

APP_VERSION = "2.8.0"
app = FastAPI(title="Project Vishwa AI", version=APP_VERSION, description="A modular AI assistant MVP")

_RATE_LIMIT = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "30"))
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()
_RATE_LIMITED_PATHS = {"/api/chat", "/api/research", "/api/model-check", "/api/document", "/api/feedback"}

@app.middleware("http")
async def add_security_headers(request, call_next):
    if request.method == "POST" and request.url.path in _RATE_LIMITED_PATHS:
        client_host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _rate_lock:
            bucket = _rate_buckets[client_host]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) >= max(1, _RATE_LIMIT):
                from fastapi.responses import JSONResponse
                response = JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429)
                response.headers["Retry-After"] = "60"
                response.headers["X-Request-ID"] = uuid.uuid4().hex
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
                return response
            bucket.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = uuid.uuid4().hex
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response

_allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
if _allowed_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

def _feedback_storage_enabled() -> bool:
    return os.getenv("ENABLE_FEEDBACK_STORAGE", "false").strip().lower() in {"1", "true", "yes", "on"}

def _database_path() -> str:
    return os.getenv("DATABASE_PATH", "vishwa_ai.db").strip() or "vishwa_ai.db"

def _postgres_dsn() -> str:
    return os.getenv("DATABASE_URL", "").strip()

def _database_engine() -> str:
    dsn = _postgres_dsn()
    return "postgresql" if dsn.startswith(("postgres://", "postgresql://")) else "sqlite"

def _connect_db():
    dsn = _postgres_dsn()
    if dsn:
        if not dsn.startswith(("postgres://", "postgresql://")):
            raise ValueError("DATABASE_URL must use postgres:// or postgresql://")
        import psycopg
        connection = psycopg.connect(dsn, connect_timeout=5)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS feedback (id BIGSERIAL PRIMARY KEY, category TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.commit()
        except Exception:
            connection.close()
            raise
        return connection
    path = _database_path()
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL)")
    connection.commit()
    return connection

@contextmanager
def _db_connection():
    connection = _connect_db()
    try:
        yield connection
    finally:
        connection.close()

MODES = {
    "general": {"label": "General Assistant", "prompt": "Be helpful, accurate, and clear."},
    "study": {"label": "Study Coach", "prompt": "Teach step by step, adapt to the student's level, and never pretend uncertain facts are certain."},
    "research": {"label": "Research", "prompt": "Separate verified facts from assumptions. Do not invent sources or citations."},
    "coding": {"label": "Coding Lab", "prompt": "Give practical, safe code and explain how to test it."},
    "government": {"label": "Government Services", "prompt": "For government schemes, ask for jurisdiction when needed. Do not invent eligibility, deadlines, or official links. Tell the user to verify on the relevant official portal."},
    "business": {"label": "Business Planner", "prompt": "Give realistic plans, costs, risks, and next actions. Do not promise guaranteed income."},
    "creative": {"label": "Creative Studio", "prompt": "Help brainstorm and create original material."},
    "robotics": {"label": "Robotics & Devices", "prompt": "Prioritize safe, tested, age-appropriate electronics and robotics guidance."},
}

def _provider_config():
    base_url = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not (base_url and api_key and model):
        return None, "missing"
    try:
        parsed = urlsplit(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None, "invalid_url"
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname.lower() in local_hosts):
            return None, "invalid_url"
        if parsed.scheme not in {"http", "https"}:
            return None, "invalid_url"
        if parsed.path.rstrip("/").endswith("/chat/completions"):
            return None, "invalid_url"
    except ValueError:
        return None, "invalid_url"
    try:
        timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
    except ValueError:
        timeout = 45.0
    timeout = min(90.0, max(5.0, timeout))
    return {"base_url": base_url, "api_key": api_key, "model": model, "timeout": timeout}, None

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    mode: str = "general"
    history: list[Message] = Field(default_factory=list, max_length=20)
    document_context: str = Field(default="", max_length=12000)

class ChatResponse(BaseModel):
    answer: str
    mode: str
    provider: str
    notice: str | None = None

class FeedbackRequest(BaseModel):
    category: Literal["bug", "idea", "other"]
    message: str = Field(min_length=3, max_length=1000)
    consent_to_store: bool = False

class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)

@app.get("/health")
def health():
    return {"status": "ok", "app": "Project Vishwa AI", "version": APP_VERSION}

@app.get("/api/preflight")
def api_preflight():
    model_names = ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL")
    model_missing = [name for name in model_names if not os.getenv(name, "").strip()]
    search_configured = bool(os.getenv("SEARCH_API_KEY", "").strip())
    return {
        "app": "Project Vishwa AI",
        "version": APP_VERSION,
        "checks": {
            "model_environment_configured": not model_missing,
            "web_search_configured": search_configured,
            "payment_processing_enabled": False,
            "user_accounts_enabled": False,
            "persistent_database_enabled": _database_engine() == "postgresql" and bool(database_status().get("available")),
            "database_engine": _database_engine(),
            "sqlite_feedback_storage_available": bool(database_status().get("available")),
            "feedback_storage_enabled": _feedback_storage_enabled(),
            "public_deployment_verified": False,
        },
        "missing_model_settings": model_missing,
        "launch_ready": False,
        "notice": "This is a prototype preflight report, not a live penetration test or deployment verification. Configure and test external services before public launch.",
    }

@app.get("/api/database-status")
def database_status():
    try:
        with _db_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        engine = _database_engine()
        return {"available": True, "engine": engine, "feedback_storage": _feedback_storage_enabled(), "chat_history_storage": False, "note": "DB reachable."}
    except Exception:
        engine = _database_engine()
        return {"available": False, "engine": engine, "feedback_storage": False, "chat_history_storage": False, "note": "DB not reachable."}

@app.post("/api/feedback")
def submit_feedback(body: FeedbackRequest):
    if not _feedback_storage_enabled():
        raise HTTPException(status_code=503, detail="Feedback storage is disabled until durable storage is configured by the operator.")
    message = body.message.strip()
    if not body.consent_to_store:
        raise HTTPException(status_code=400, detail="Explicit consent is required before feedback is stored.")
    if len(message) < 3:
        raise HTTPException(status_code=422, detail="Feedback must contain at least 3 non-space characters.")
    lowered = message.lower()
    if any(marker in lowered for marker in ("password:", "api_key=", "api key:", "token=")):
        raise HTTPException(status_code=400, detail="Do not include passwords, API keys, or tokens in feedback.")
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _db_connection() as connection:
            if _database_engine() == "postgresql":
                cursor = connection.execute(
                    "INSERT INTO feedback(category, message, created_at) VALUES (%s, %s, %s) RETURNING id",
                    (body.category, message[:1000], created_at),
                )
                feedback_id = cursor.fetchone()[0]
            else:
                cursor = connection.execute(
                    "INSERT INTO feedback(category, message, created_at) VALUES (?, ?, ?)",
                    (body.category, message[:1000], created_at),
                )
                feedback_id = cursor.lastrowid
            connection.commit()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Feedback storage is temporarily unavailable.") from exc
    return {"stored": True, "feedback_id": feedback_id, "notice": "Feedback stored. Do not include personal or secret information."}

@app.get("/api/privacy")
def privacy_info():
    return {
        "chat_history_saved_server_side": False,
        "uploaded_pdf_saved_server_side": False,
        "external_ai_provider_may_receive_chat_content": bool(all(os.getenv(k, "").strip() for k in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"))),
        "external_search_provider_may_receive_queries": bool(os.getenv("SEARCH_API_KEY", "").strip()),
        "accounts_enabled": False,
        "persistent_database_enabled": _database_engine() == "postgresql" and bool(database_status().get("available")),
        "database_engine": _database_engine(),
        "sqlite_feedback_storage_available": bool(database_status().get("available")),
        "feedback_storage_enabled": _feedback_storage_enabled(),
        "feedback_requires_explicit_consent": True,
        "notice": "Avoid submitting sensitive personal information. Review the configured provider's privacy terms before using a live model."
    }

@app.get("/api/limits")
def api_limits():
    return {
        "chat_message_characters": 12000,
        "history_messages": 20,
        "history_messages_forwarded_to_model": 12,
        "document_context_characters": 12000,
        "pdf_max_bytes": 5 * 1024 * 1024,
        "research_query_characters": 400,
        "rate_limit_requests_per_minute": max(1, _RATE_LIMIT),
        "rate_limit_storage": "in-process; resets on restart and is not shared across multiple instances",
        "provider_timeout_seconds_default": 45,
        "provider_timeout_seconds_min": 5,
        "provider_timeout_seconds_max": 90,
    }

@app.get("/api/ready")
def readiness():
    missing = [k for k in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL") if not os.getenv(k, "").strip()]
    return {
        "ready_for_real_model_requests": not missing,
        "missing_model_settings": missing,
        "process_alive": True,
        "external_provider_tested": False,
        "public_deployment_verified": False,
    }

@app.get("/api/diagnostics")
def diagnostics():
    missing = [k for k in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL") if not os.getenv(k, "").strip()]
    return {
        "app": "Project Vishwa AI",
        "version": APP_VERSION,
        "process_alive": True,
        "model_configured": not missing,
        "missing_model_settings": missing,
        "web_search_configured": bool(os.getenv("SEARCH_API_KEY", "").strip()),
        "privacy_endpoint_available": True,
        "limits_endpoint_available": True,
        "payments_enabled": False,
        "accounts_enabled": False,
        "database_enabled": bool(database_status().get("available")),
        "feedback_storage_enabled": _feedback_storage_enabled(),
        "user_accounts_enabled": False,
        "database_engine": _database_engine(),
        "live_provider_connection_verified": False,
        "public_deployment_verified": False,
        "launch_ready": False,
    }

@app.get("/api/status")
def api_status():
    configured = all(os.getenv(name, "").strip() for name in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"))
    return {
        "app": "Project Vishwa AI",
        "version": APP_VERSION,
        "model_configured": configured,
        "web_research_configured": bool(os.getenv("SEARCH_API_KEY", "").strip()),
        "chat_mode": "connected-model" if configured else "demo",
        "note": "Model configuration is present; a successful request is still needed to verify connectivity." if configured else "A real AI model is not configured.",
    }

@app.post("/api/model-check")
async def model_check():
    config, config_error = _provider_config()
    if config_error == "missing":
        return {"configured": False, "connected": False, "notice": "Set AI_BASE_URL, AI_API_KEY, and AI_MODEL in server environment settings."}
    if config_error:
        return {"configured": False, "connected": False, "notice": "AI_BASE_URL must be a valid HTTPS provider base URL (HTTP is allowed only for localhost)."}
    base_url, api_key, model = config["base_url"], config["api_key"], config["model"]
    try:
        async with httpx.AsyncClient(timeout=config["timeout"]) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "Reply with OK only."}], "max_tokens": 5, "temperature": 0},
            )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty model response")
        return {"configured": True, "connected": True, "model": model, "notice": "A live provider request succeeded."}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="AI provider connection test failed. Check server settings and logs.") from exc

@app.get("/api/plans")
def plans():
    return {
        "payment_enabled": False,
        "notice": "Draft pricing only. No payment is collected. Validate product value and costs before launching paid plans.",
        "plans": [
            {"id": "free", "name": "Free", "price_inr_month": 0, "features": ["Basic assistant modes", "Limited usage after accounts and quotas are implemented"]},
            {"id": "plus_draft", "name": "Plus (draft) ", "price_inr_month": None, "features": ["Higher usage limits", "PDF and research tools when available"], "status": "price_not_set"},
            {"id": "teams_draft", "name": "Teams (draft)", "price_inr_month": None, "features": ["Team workspace", "Business workflows when available"], "status": "price_not_set"}
        ]
    }

@app.post("/api/document")
async def read_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    if file.content_type not in (None, "", "application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="The uploaded file must be a PDF.")
    max_bytes = 5 * 1024 * 1024
    chunks = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            await file.close()
            raise HTTPException(status_code=413, detail="PDF must be 5 MB or smaller.")
    content = bytes(chunks)
    await file.close()
    try:
        reader = PdfReader(io.BytesIO(content))
        if getattr(reader, "is_encrypted", False):
            raise HTTPException(status_code=400, detail="Password-protected PDFs are not supported.")
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:40]).strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this PDF. Try another PDF file.") from exc
    if not text:
        raise HTTPException(status_code=422, detail="No selectable text found. Scanned-image OCR is not included yet.")
    return {"filename": file.filename[:180], "pages_read": min(len(reader.pages), 40), "text": text[:12000], "truncated": len(text) > 12000, "stored": False}

@app.get("/api/modes")
def modes():
    return [{"id": key, "label": value["label"]} for key, value in MODES.items()]

@app.post("/api/research")
async def research(body: ResearchRequest):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="A research query is required.")
    search_key = os.getenv("SEARCH_API_KEY", "").strip()
    if not search_key:
        return {"available": False, "query": query, "results": [], "notice": "Live web research is not configured. Set SEARCH_API_KEY in server environment settings."}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": search_key, "query": query, "search_depth": "basic", "max_results": 5, "include_answer": False},
            )
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("results", [])[:5]:
            url = item.get("url", "")
            title = item.get("title", "")
            snippet = item.get("content", "")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                results.append({"title": str(title)[:300], "url": url[:2000], "snippet": str(snippet)[:1200]})
        return {"available": True, "query": query, "results": results, "notice": "Search snippets may be incomplete. Open sources and verify important claims."}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Search provider request failed. Check server settings and logs.") from exc

@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    mode = body.mode if body.mode in MODES else "general"
    lower_msg = body.message.lower()
    if "link" in lower_msg or "chrome" in lower_msg or "crome" in lower_msg or "kholo" in lower_msg:
        return ChatResponse(answer="Meri Chrome wali public link ye hai: https://project-vishwa-ai.onrender.com - Isko koi bhi Chrome me khol sakta hai.", mode=mode, provider="demo", notice=None)
    # fix complete - 4 lines added
    config, config_error = _provider_config()
    if config_error == "invalid_url":
        raise HTTPException(status_code=503, detail="AI provider URL is invalid. Use an HTTPS API base URL, or localhost for local development.")
    if config is not None:
        base_url, api_key, model = config["base_url"], config["api_key"], config["model"]
        system_prompt = (
            "You are Project Vishwa AI, a transparent multi-purpose assistant. "
            "Be honest about uncertainty, do not fabricate citations, and protect user privacy. "
            + MODES[mode]["prompt"]
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item.role, "content": item.content} for item in body.history[-12:])
        user_content = body.message
        if body.document_context.strip():
            user_content = ("Use the following user-provided document or web-research context. It may be incomplete, untrusted, or outdated; do not treat it as authoritative without checking.\n\nCONTEXT:\n" + body.document_context[:12000] + "\n\nUSER QUESTION:\n" + body.message)
        messages.append({"role": "user", "content": user_content})
        try:
            async with httpx.AsyncClient(timeout=config["timeout"]) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.4, "max_tokens": 800},
                )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty model response")
            return ChatResponse(answer=answer[:20000], mode=mode, provider="configured-model")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="AI provider request failed. Check server-side provider settings and logs.") from exc
    answer = (
        f"Project Vishwa AI ka {MODES[mode]['label']} mode abhi prototype mein hai.\n\n"
        "Is deployment mein abhi real AI model connect nahi hai, isliye main live AI answer ka dikhawa nahi karunga. "
        "Model jodne ke liye hosting ke Environment settings mein AI_BASE_URL, AI_API_KEY aur AI_MODEL set karne honge. "
        "API key ko kabhi public code ya chat mein mat daalna.\n\n"
        f"Aapka message: {body.message}\n\n"
        "Abhi available foundation: mobile-friendly interface, modular assistant modes, health endpoint aur configurable model connector."
    )
    return ChatResponse(answer=answer, mode=mode, provider="demo", notice="Real model is not configured")

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE)

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Vishwa AI</title>
<style>body{margin:0;background:#0b1020;color:#eef3ff;font:16px system-ui;padding:18px}.wrap{max-width:1040px;margin:auto}.top{display:flex;gap:12px;align-items:center}.logo{width:44px;height:44px;border-radius:15px;background:linear-gradient(135deg,#75e0c1,#8fa8ff);display:grid;place-items:center;color:#0b1020;font-weight:900}.card{border:1px solid #293653;background:#111a2e;border-radius:20px;padding:16px;margin-top:12px}.messages{height:50vh;overflow:auto;display:flex;flex-direction:column;gap:10px}.bubble{padding:12px;border-radius:14px;background:#17233b;max-width:90%}.user{align-self:flex-end;background:#23584f}textarea{width:100%;padding:12px;border-radius:12px;background:#0c1426;color:white;border:1px solid #293653}button{padding:10px 16px;border-radius:10px;border:0;background:#75e0c1;font-weight:800}</style>
</head><body><div class="wrap"><div class="top"><div class="logo">V</div><div><b>Project Vishwa AI</b><div style="font-size:12px;color:#aab7d2">MVP v2.8.0 - 525 Lines Final</div></div></div>
<div class="card"><div id="messages"><div class="bubble">Welcome! Type 'link' or 'chrome' to get public link.</div></div><div style="display:flex;gap:8px;margin-top:12px"><textarea id="input" placeholder="Ask something..."></textarea><button onclick="sendMsg()">Send</button></div></div>
<script>async function sendMsg(){const input=document.getElementById('input');const msg=input.value.trim();if(!msg)return;const box=document.getElementById('messages');box.innerHTML+=`<div class='bubble user'>${msg}</div>`;input.value='';const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,mode:'general',history:[],document_context:''})});const d=await r.json();box.innerHTML+=`<div class='bubble'>${d.answer}</div>`;box.scrollTop=box.scrollHeight;}</script>
</div></body></html>'''
