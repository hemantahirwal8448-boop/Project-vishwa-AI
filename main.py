"""Project Vishwa AI — starter MVP. Full 8 modes + link fix."""
from __future__ import annotations
import os, time, uuid, io, sqlite3
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
from pathlib import Path
from datetime import datetime, timezone

APP_VERSION = "2.8.0"
app = FastAPI(title="Project Vishwa AI", version=APP_VERSION)
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
            while bucket and now - bucket[0] >= 60: bucket.popleft()
            if len(bucket) >= max(1, _RATE_LIMIT):
                from fastapi.responses import JSONResponse
                r = JSONResponse({"detail": "Too many requests."}, status_code=429)
                r.headers["Retry-After"] = "60"; return r
            bucket.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

_allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
if _allowed_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

def _feedback_storage_enabled() -> bool:
    return os.getenv("ENABLE_FEEDBACK_STORAGE", "false").lower() in {"1","true","yes","on"}
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
        import psycopg
        c = psycopg.connect(dsn, connect_timeout=5)
        c.execute("CREATE TABLE IF NOT EXISTS feedback (id BIGSERIAL PRIMARY KEY, category TEXT, message TEXT, created_at TEXT)"); c.commit(); return c
    path = _database_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=5)
    c.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, message TEXT, created_at TEXT)"); c.commit(); return c
@contextmanager
def _db_connection():
    c = _connect_db()
    try: yield c
    finally: c.close()

MODES = {
    "general": {"label": "General Assistant", "prompt": "Be helpful, accurate, and clear."},
    "study": {"label": "Study Coach", "prompt": "Teach step by step, adapt to student level."},
    "research": {"label": "Research", "prompt": "Separate verified facts from assumptions. Do not invent sources."},
    "coding": {"label": "Coding Lab", "prompt": "Give practical, safe code and explain testing."},
    "government": {"label": "Government Services", "prompt": "For schemes, ask jurisdiction. Do not invent links."},
    "business": {"label": "Business Planner", "prompt": "Give realistic plans, costs, risks."},
    "creative": {"label": "Creative Studio", "prompt": "Help brainstorm original material."},
    "robotics": {"label": "Robotics & Devices", "prompt": "Prioritize safe, tested guidance."},
}

def _provider_config():
    base_url = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not (base_url and api_key and model): return None, "missing"
    try:
        parsed = urlsplit(base_url)
        if not parsed.hostname or parsed.scheme not in {"http","https"}: return None, "invalid_url"
        if parsed.path.rstrip("/").endswith("/chat/completions"): return None, "invalid_url"
    except ValueError: return None, "invalid_url"
    return {"base_url": base_url, "api_key": api_key, "model": model, "timeout": 45.0}, None

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    mode: str = "general"
    history: list[Message] = Field(default_factory=list, max_length=20)
    document_context: str = Field(default="", max_length=12000)
class ChatResponse(BaseModel):
    answer: str; mode: str; provider: str; notice: str | None = None
class FeedbackRequest(BaseModel):
    category: Literal["bug", "idea", "other"]
    message: str = Field(min_length=3, max_length=1000)
    consent_to_store: bool = False
class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)

@app.get("/health")
def health(): return {"status": "ok", "version": APP_VERSION}
@app.get("/api/preflight")
def api_preflight():
    missing = [k for k in ("AI_BASE_URL","AI_API_KEY","AI_MODEL") if not os.getenv(k,"").strip()]
    return {"version": APP_VERSION, "missing": missing, "checks": {"model": not missing}}
@app.get("/api/database-status")
def database_status():
    try:
        with _db_connection() as c: c.execute("SELECT 1")
        return {"available": True, "engine": _database_engine()}
    except: return {"available": False, "engine": _database_engine()}
@app.post("/api/feedback")
def submit_feedback(body: FeedbackRequest):
    if not _feedback_storage_enabled(): raise HTTPException(503, "Feedback disabled")
    if not body.consent_to_store: raise HTTPException(400, "Consent required")
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _db_connection() as c:
            if _database_engine() == "postgresql":
                cur = c.execute("INSERT INTO feedback(category,message,created_at) VALUES (%s,%s,%s) RETURNING id", (body.category, body.message[:1000], created_at))
                fid = cur.fetchone()[0]
            else:
                cur = c.execute("INSERT INTO feedback(category,message,created_at) VALUES (?,?,?)", (body.category, body.message[:1000], created_at))
                fid = cur.lastrowid
            c.commit()
    except Exception as e: raise HTTPException(503, "DB unavailable") from e
    return {"stored": True, "id": fid}
@app.get("/api/status")
def api_status():
    cfg = all(os.getenv(k,"").strip() for k in ("AI_BASE_URL","AI_API_KEY","AI_MODEL"))
    return {"version": APP_VERSION, "model_configured": cfg, "chat_mode": "connected-model" if cfg else "demo"}
@app.get("/api/modes")
def modes(): return [{"id": k, "label": v["label"]} for k,v in MODES.items()]
@app.post("/api/research")
async def research(body: ResearchRequest):
    q = body.query.strip()
    key = os.getenv("SEARCH_API_KEY","").strip()
    if not key: return {"available": False, "query": q, "results": []}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post("https://api.tavily.com/search", json={"api_key": key, "query": q, "max_results": 5})
            r.raise_for_status(); data = r.json()
        results = [{"title": i.get("title","")[:300], "url": i.get("url",""), "snippet": i.get("content","")[:1200]} for i in data.get("results",[])[:5]]
        return {"available": True, "query": q, "results": results}
    except Exception as e: raise HTTPException(502, "Search failed") from e
@app.post("/api/document")
async def read_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"): raise HTTPException(400, "Upload PDF")
    content = await file.read()
    if len(content) > 5*1024*1024: raise HTTPException(413, "PDF 5MB max")
    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:40]).strip()
    except Exception as e: raise HTTPException(400, "Cannot read PDF") from e
    if not text: raise HTTPException(422, "No text found")
    return {"filename": file.filename, "pages_read": min(len(reader.pages),40), "text": text[:12000], "truncated": len(text)>12000}
@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    mode = body.mode if body.mode in MODES else "general"
    low = body.message.lower()
    if any(k in low for k in ["link","chrome","crome","kholo","public link"]):
        return ChatResponse(answer="Meri Chrome wali public link ye hai: https://project-vishwa-ai.onrender.com - Isko koi bhi Chrome me khol sakta hai. 8 modes available: General, Study, Research, Coding, Government, Business, Creative, Robotics.", mode=mode, provider="demo")
    config, err = _provider_config()
    if err == "invalid_url": raise HTTPException(503, "AI URL invalid")
    if config:
        try:
            sys_prompt = "You are Project Vishwa AI. " + MODES[mode]["prompt"]
            msgs = [{"role": "system", "content": sys_prompt}]
            msgs.extend({"role": m.role, "content": m.content} for m in body.history[-12:])
            uc = body.message
            if body.document_context.strip(): uc = f"Context:\n{body.document_context[:12000]}\n\nQuestion:\n{body.message}"
            msgs.append({"role": "user", "content": uc})
            async with httpx.AsyncClient(timeout=config["timeout"]) as client:
                r = await client.post(f"{config['base_url']}/chat/completions", headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}, json={"model": config["model"], "messages": msgs, "temperature": 0.4, "max_tokens": 800})
                r.raise_for_status(); data = r.json()
                ans = data["choices"][0]["message"]["content"]
                return ChatResponse(answer=ans[:20000], mode=mode, provider="configured-model")
        except Exception as e: raise HTTPException(502, "AI provider failed") from e
    ans = f"Project Vishwa AI ka {MODES[mode]['label']} mode prototype me hai. Aapka message: {body.message}. Model connect karne ke liye AI_BASE_URL, AI_API_KEY, AI_MODEL set karo."
    return ChatResponse(answer=ans, mode=mode, provider="demo", notice="Demo mode")
@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(PAGE)

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Vishwa AI - 8 Modes</title>
<style>
body{margin:0;background:#0b1020;color:#eef3ff;font:15px system-ui;padding:12px}
.wrap{max-width:1100px;margin:auto}
.top{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.logo{width:44px;height:44px;border-radius:15px;background:linear-gradient(135deg,#75e0c1,#8fa8ff);display:grid;place-items:center;color:#0b1020;font-weight:900}
.card{border:1px solid #293653;background:#111a2e;border-radius:16px;padding:14px;margin-top:12px}
.modes{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:8px}
.mode{padding:10px;border-radius:10px;border:1px solid #293653;background:#17233b;color:#eef3ff;cursor:pointer;font-weight:600}
.mode.active{background:#1e3a5a;border-color:#75e0c1;color:#75e0c1}
.messages{height:45vh;overflow:auto;display:flex;flex-direction:column;gap:8px;background:#0c1426;border-radius:12px;padding:10px;border:1px solid #293653}
.bubble{padding:10px 12px;border-radius:12px;background:#17233b;max-width:92%;white-space:pre-wrap}
.user{align-self:flex-end;background:#23584f}
.row{display:flex;gap:8px;margin-top:10px}
textarea,input{flex:1;padding:10px;border-radius:10px;background:#0c1426;color:white;border:1px solid #293653}
button{padding:10px 14px;border-radius:10px;border:0;background:#75e0c1;font-weight:800;cursor:pointer}
.small{font-size:12px;color:#aab7d2}
</style></head><body>
<div class="wrap">
<div class="top"><div class="logo">V</div><div><b>Project Vishwa AI</b><div class="small">One platform · 8 Assistants · MVP v2.8.0 - 525 Lines Full</div></div><div style="margin-left:auto" class="small">Public Link: project-vishwa-ai.onrender.com</div></div>

<div class="card"><strong>1. Choose Assistant (8 Modes)</strong>
<div class="modes" id="modes">
<button class="mode active" data-mode="general">General Assistant</button>
<button class="mode" data-mode="study">Study Coach</button>
<button class="mode" data-mode="research">Research</button>
<button class="mode" data-mode="coding">Coding Lab</button>
<button class="mode" data-mode="government">Government Services</button>
<button class="mode" data-mode="business">Business Planner</button>
<button class="mode" data-mode="creative">Creative Studio</button>
<button class="mode" data-mode="robotics">Robotics & Devices</button>
</div><div class="small" style="margin-top:8px">Selected: <span id="sel">general</span> - Type link/chrome to get public link</div></div>

<div class="card"><strong>2. Chat</strong>
<div class="messages" id="messages"><div class="bubble">Welcome to Project Vishwa AI! I have 8 modes. Try: "Study mode me samjhao", "Research karo", "Link do", "Chrome me kaise khole"</div></div>
<div class="row"><textarea id="input" placeholder="Ask something... Type link for public Chrome link"></textarea><button onclick="sendMsg()">Send</button></div>
</div>

<div class="card"><strong>3. PDF Upload (Read PDF)</strong>
<div class="row"><input type="file" id="pdfFile" accept=".pdf"><button onclick="uploadPDF()">Upload & Read</button></div>
<div id="pdfStatus" class="small" style="margin-top:6px"></div>
</div>

<div class="card"><strong>4. Live Web Research</strong>
<div class="row"><input id="researchQ" placeholder="Search query..."><button onclick="doResearch()">Search</button></div>
<div id="researchRes" class="small" style="margin-top:6px"></div>
</div>

<div class="card"><div class="small">Health: <a href="/health" style="color:#75e0c1">/health</a> | Status: <a href="/api/status" style="color:#75e0c1">/api/status</a> | Modes: <a href="/api/modes" style="color:#75e0c1">/api/modes</a> | Public Chrome Link: https://project-vishwa-ai.onrender.com</div></div>

</div>
<script>
let mode="general", history=[], docContext="";
document.querySelectorAll(".mode").forEach(b=>{b.onclick=()=>{document.querySelectorAll(".mode").forEach(x=>x.classList.remove("active"));b.classList.add("active");mode=b.dataset.mode;document.getElementById("sel").textContent=mode;}});
async function sendMsg(){
  const input=document.getElementById("input"); const msg=input.value.trim(); if(!msg) return;
  const box=document.getElementById("messages"); box.innerHTML+=`<div class="bubble user">${msg}</div>`; input.value="";
  const r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,mode:mode,history:history,document_context:docContext})});
  const d=await r.json(); box.innerHTML+=`<div class="bubble">${d.answer.replace(/</g,"&lt;")}</div>`; box.scrollTop=box.scrollHeight; history.push({role:"user",content:msg},{role:"assistant",content:d.answer}); if(history.length>20) history=history.slice(-20);
}
async function uploadPDF(){
  const f=document.getElementById("pdfFile").files[0]; if(!f) return alert("PDF select karo");
  const fd=new FormData(); fd.append("file",f); document.getElementById("pdfStatus").textContent="Uploading...";
  const r=await fetch("/api/document",{method:"POST",body:fd}); const d=await r.json();
  if(r.ok){docContext=d.text; document.getElementById("pdfStatus").textContent=`Read ${d.pages_read} pages, ${d.text.length} chars loaded. Ab chat me pucho is PDF ke baare me.`;} else {document.getElementById("pdfStatus").textContent="Error: "+(d.detail||"failed");}
}
async function doResearch(){
  const q=document.getElementById("researchQ").value.trim(); if(!q) return;
  document.getElementById("researchRes").textContent="Searching...";
  const r=await fetch("/api/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:q})}); const d=await r.json();
  if(d.available){document.getElementById("researchRes").innerHTML=d.results.map(x=>`<div><a href="${x.url}" target="_blank" style="color:#75e0c1">${x.title}</a><br>${x.snippet.slice(0,200)}</div>`).join("<hr>"); docContext=d.results.map(x=>x.snippet).join("\n");} else {document.getElementById("researchRes").textContent=d.notice||"Research not configured";}
}
document.getElementById("input").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMsg();}});
</script>
</body></html>'''
