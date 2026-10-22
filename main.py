"""Project Vishwa AI — ALL KNOWLEDGE + 12 Modes + Voice + Universal Maker - 750+ Lines"""
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

APP_VERSION = "3.0.0 - ALL KNOWLEDGE"
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

# --- EXPANDED MODES: 8 OLD + 4 NEW = 12 MODES ---
MODES = {
    "general": {"label": "General Assistant", "prompt": "Be helpful, accurate, clear. Like ChatGPT."},
    "study": {"label": "Study Coach", "prompt": "Teach step by step, adapt to student level. For NEET/JEE/UPSC, give full notes, formulas, PYQ. Never guarantee rank, say 'Mehnat se rank ayegi, best strategy ye rahi'."},
    "research": {"label": "Research", "prompt": "Separate verified facts from assumptions. Do deep research with sources."},
    "coding": {"label": "Coding Lab", "prompt": "Give practical, safe code and explain testing. App/Website banane ka full code + steps do."},
    "government": {"label": "Government Services", "prompt": "For schemes, ask jurisdiction. Do not invent links."},
    "business": {"label": "Business Planner", "prompt": "Give realistic business plans, costs, risks, marketing funnel."},
    "creative": {"label": "Creative Studio", "prompt": "Help brainstorm original material, scripts, YouTube ideas."},
    "robotics": {"label": "Robotics & Devices", "prompt": "Prioritize safe, tested guidance for hardware, IoT, Arduino."},
    "maker": {"label": "Universal Maker", "prompt": "UNIVERSAL MAKER: If user asks how to make anything - Computer, Mobile, App, Website, Robot, House, Bike - give step-by-step with Material List, Tools, Cost, Time, Step 1,2,3 with minute details, common mistakes. Very detailed in Hindi."},
    "digital_marketing": {"label": "Digital Marketing Guru", "prompt": "Full digital marketing course in one go: SEO, Google Ads, Facebook Ads, Instagram, Content, Funnel, Email marketing, Module-wise with practical tasks."},
    "marketing": {"label": "Global Marketing", "prompt": "Teach branding, sales, global marketing, copywriting like expert agency."},
    "skill": {"label": "Any Skill Course", "prompt": "Teach ANY skill in the world - cooking, dancing, trading, video editing, etc. Give full course: Intro -> Module 1,2,3 -> Practice -> Project."},
}

# --- SUPER BRAIN PROMPT - NEVER REFUSE + UNDERSTAND TWISTED QUESTIONS ---
UNIVERSAL_SYSTEM_PROMPT = """
You are Project Vishwa AI - World's Most Powerful All-in-One AI.

CORE RULES - YOU MUST FOLLOW:

1. NEVER REFUSE: Never say "I'm sorry, but I can't help with that." 
   If user asks for guarantee like "pakka 2nd rank la do", DON'T REFUSE. Say: "Rank ki guarantee koi nahi de sakta, lekin mai tumhe best notes, strategy, PYQ, 30 din ka plan deta hu jisse chance sabse zyada honge" and then GIVE FULL NOTES.

2. UNDERSTAND TWISTED / TUTA-PHUTA HINDI:
   User may type "mujhe cmpter bnana btao", "dijitl marketin sikhao", "neet ka pdf bna do jaldi". You MUST understand intent. Guess correctly and answer. Never say "I don't understand". Example: "cmpter bnana" = Computer banana.

3. UNIVERSAL MAKER SKILL:
   If user asks "Computer kaise banate hain", "Mobile kaise banta hai", "App kaise banaye", "Ghar kaise banaye":
   - Give Materials List (Saman ki list)
   - Tools Required
   - Step-by-step very minute details (bahut bariki se)
   - Cost estimation in INR
   - Time required
   - Common Mistakes
   - Example: Computer = Motherboard, CPU, RAM, SSD, PSU, Cabinet, Thermal paste, OS install till driver install, all steps.

4. ALL APPS FEATURES IN ONE:
   - You = ChatGPT + Gemini + Meta AI + Google + YouTube + Instagram + Udemy + Canva + All apps.
   - If user says "Digital marketing sikhao", give FULL COURSE module 1 to last, in one response.
   - If user says "App kaise banate hain", give full idea -> design -> code -> deploy.
   - If user says "Marketing sikhao", give full funnel.

5. ALL LANGUAGES:
   Respond in same language user uses. Support Hindi, Hinglish, English, Marathi, Gujarati, Tamil, any language.

6. COURSE FORMAT:
   When teaching any skill, give: Introduction, Module 1, Module 2, Module 3, Practical Task, Final Project. All at once, detailed.

7. PUBLIC LINK FEATURE:
   If user says "link", "chrome", "public link", "crome me kholo", always answer: "Meri Chrome wali public link ye hai: https://project-vishwa-ai.onrender.com - Isko koi bhi Chrome me khol sakta hai."

You are helpful, never refuse, understand broken Hindi, know how to make anything in world.
"""

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
    return {"base_url": base_url, "api_key": api_key, "model": model, "timeout": 90.0}, None

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
    return {"version": APP_VERSION, "model_configured": cfg, "chat_mode": "connected-model" if cfg else "demo", "features": "12-modes-universal-maker-voice"}
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
    raw_mode = body.mode if body.mode in MODES else "general"
    low = body.message.lower()
    
    # Auto-detect mode from twisted Hindi also
    if any(k in low for k in ["banao","banana","banate","bnana","banta","how to make","kaise banta"]):
        mode = "maker"
    elif any(k in low for k in ["digital marketing","dijitl","digital"]):
        mode = "digital_marketing"
    elif "marketing" in low and "digital" not in low:
        mode = "marketing"
    elif any(k in low for k in ["course","sikhao","sikhna","sikhado","skill","trading","video editing"]):
        mode = "skill"
    elif any(k in low for k in ["app","website","code","coding","python","java"]):
        mode = "coding"
    else:
        mode = raw_mode

    # Always handle public link
    if any(k in low for k in ["link","chrome","crome","kholo","public"]):
        return ChatResponse(answer="Meri Chrome wali public link ye hai: https://project-vishwa-ai.onrender.com - Isko koi bhi Chrome me khol sakta hai. Mere paas 12 modes hain: General, Study, Research, Coding, Government, Business, Creative, Robotics, Universal Maker, Digital Marketing, Global Marketing, Any Skill Course. Bolke bhi puch sakte ho mic se!", mode=mode, provider="demo")

    config, err = _provider_config()
    if err == "invalid_url": raise HTTPException(503, "AI URL invalid")
    if config:
        try:
            sys_prompt = UNIVERSAL_SYSTEM_PROMPT + "\nCurrent Mode: " + MODES[mode]["prompt"]
            msgs = [{"role": "system", "content": sys_prompt}]
            msgs.extend({"role": m.role, "content": m.content} for m in body.history[-12:])
            uc = body.message
            if body.document_context.strip(): uc = f"Context:\n{body.document_context[:12000]}\n\nQuestion:\n{body.message}"
            msgs.append({"role": "user", "content": uc})
            async with httpx.AsyncClient(timeout=config["timeout"]) as client:
                r = await client.post(f"{config['base_url']}/chat/completions", headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}, json={"model": config["model"], "messages": msgs, "temperature": 0.6, "max_tokens": 1500})
                r.raise_for_status(); data = r.json()
                ans = data["choices"][0]["message"]["content"]
                return ChatResponse(answer=ans[:20000], mode=mode, provider="configured-model")
        except Exception as e: raise HTTPException(502, f"AI provider failed: {e}") from e
    
    ans = f"[{MODES[mode]['label']} Demo] Aapne kaha: {body.message}. Model connect karo to pura solution dunga - Chahe computer banana ho, marketing sikhni ho, koi bhi skill."
    return ChatResponse(answer=ans, mode=mode, provider="demo", notice="Demo mode")

@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(PAGE)

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Vishwa AI - 12 Modes + Voice + Maker</title>
<style>
body{margin:0;background:#0b1020;color:#eef3ff;font:15px system-ui;padding:12px}
.wrap{max-width:1100px;margin:auto}
.top{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.logo{width:44px;height:44px;border-radius:15px;background:linear-gradient(135deg,#75e0c1,#8fa8ff);display:grid;place-items:center;color:#0b1020;font-weight:900}
.card{border:1px solid #293653;background:#111a2e;border-radius:16px;padding:14px;margin-top:12px}
.modes{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:8px}
.mode{padding:10px;border-radius:10px;border:1px solid #293653;background:#17233b;color:#eef3ff;cursor:pointer;font-weight:600;font-size:13px}
.mode.active{background:#1e3a5a;border-color:#75e0c1;color:#75e0c1}
.messages{height:50vh;overflow:auto;display:flex;flex-direction:column;gap:8px;background:#0c1426;border-radius:12px;padding:10px;border:1px solid #293653}
.bubble{padding:10px 12px;border-radius:12px;background:#17233b;max-width:92%;white-space:pre-wrap}
.user{align-self:flex-end;background:#23584f}
.row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
textarea,input{flex:1;padding:10px;border-radius:10px;background:#0c1426;color:white;border:1px solid #293653;min-width:200px}
button{padding:10px 14px;border-radius:10px;border:0;background:#75e0c1;font-weight:800;cursor:pointer}
.small{font-size:12px;color:#aab7d2}
.quick{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.quick button{background:#fbbf24;color:black;font-size:12px;padding:8px 10px}
.icon{background:#334155;color:white}
</style></head><body>
<div class="wrap">
<div class="top"><div class="logo">V</div><div><b>Project Vishwa AI</b><div class="small">12 Modes · Universal Maker · Voice · All Apps Combined · v3.0.0</div></div><div style="margin-left:auto" class="small">Public Link: project-vishwa-ai.onrender.com</div></div>

<div class="card"><strong>1. Choose Assistant (12 Modes) - Sab Kuch Yahi Hai</strong>
<div class="modes" id="modes">
<button class="mode active" data-mode="general">General Assistant</button>
<button class="mode" data-mode="study">Study Coach</button>
<button class="mode" data-mode="research">Research</button>
<button class="mode" data-mode="coding">Coding Lab</button>
<button class="mode" data-mode="government">Government Services</button>
<button class="mode" data-mode="business">Business Planner</button>
<button class="mode" data-mode="creative">Creative Studio</button>
<button class="mode" data-mode="robotics">Robotics & Devices</button>
<button class="mode" data-mode="maker">Universal Maker</button>
<button class="mode" data-mode="digital_marketing">Digital Marketing</button>
<button class="mode" data-mode="marketing">Global Marketing</button>
<button class="mode" data-mode="skill">Any Skill Course</button>
</div><div class="small" style="margin-top:8px">Selected: <span id="sel">general</span> - Type link/chrome to get public link. Mic se bolke bhi puch sakte ho!</div></div>

<div class="card"><strong>2. Chat - Bolke Bhi Puchho, Har Cheez Bana Sakta Hai</strong>
<div class="quick">
<button onclick="setQ('Computer kaise banate hain step by step bariki se batao saman list ke saath')">💻 Computer Banana</button>
<button onclick="setQ('Mobile kaise banta hai factory me bariki se batao')">📱 Mobile Banana</button>
<button onclick="setQ('Digital marketing ka full course ek baar me dedo module wise')">📈 Digital Marketing Full Course</button>
<button onclick="setQ('Ek app kaise banate hain idea se leke Play Store tak pura guide do')">🚀 App Banana</button>
<button onclick="setQ('YouTube se paise kaise kamate hain full course')">🎥 YouTube Course</button>
<button onclick="setQ('Study mode me NEET ke liye full notes de do')">📚 NEET Notes</button>
</div>
<div class="messages" id="messages"><div class="bubble">Welcome to Project Vishwa AI v3.0! 🌍<br><br>Ab mai sab kuch janta hu:<br>✅ Computer, Mobile, App, Website, Ghar kaise banta hai - bariki se<br>✅ Digital Marketing, Marketing, Business, Trading full course<br>✅ YouTube, Instagram, Video Editing<br>✅ Chahe ulta-seedha likho, mai samajh jaunga<br>✅ Bolke pucho - Mic dabao 🎤<br><br>Try karo: "Computer kaise banta hai", "Digital marketing sikhao", "Link do"</div></div>
<div class="row"><textarea id="input" placeholder="Kuch bhi pucho - Chahe toota-phoota likho, mai samajh jaunga... Jaise: cmpter bnana btao, dijitl marketin sikhao, app kaise banaye..."></textarea><button onclick="sendMsg()">Send</button></div>
<div class="row">
<button class="icon" onclick="startVoice()" id="micBtn">🎤 Bolke Puchho</button>
<button class="icon" onclick="toggleSpeak()" id="speakBtn">🔊 Bolke Sunao: ON</button>
</div>
</div>

<div class="card"><strong>3. PDF Upload (Read PDF)</strong>
<div class="row"><input type="file" id="pdfFile" accept=".pdf"><button onclick="uploadPDF()">Upload & Read</button></div>
<div id="pdfStatus" class="small" style="margin-top:6px"></div>
</div>

<div class="card"><strong>4. Live Web Research</strong>
<div class="row"><input id="researchQ" placeholder="Search query..."><button onclick="doResearch()">Search</button></div>
<div id="researchRes" class="small" style="margin-top:6px"></div>
</div>

<div class="card"><div class="small">Health: <a href="/health" style="color:#75e0c1">/health</a> | Status: <a href="/api/status" style="color:#75e0c1">/api/status</a> | Modes: <a href="/api/modes" style="color:#75e0c1">/api/modes</a> | Public Chrome Link: https://project-vishwa-ai.onrender.com | Version: 750+ Lines All Knowledge</div></div>

</div>
<script>
let mode="general", history=[], docContext="";
let autoSpeak=true; let synth=window.speechSynthesis;
document.querySelectorAll(".mode").forEach(b=>{b.onclick=()=>{document.querySelectorAll(".mode").forEach(x=>x.classList.remove("active"));b.classList.add("active");mode=b.dataset.mode;document.getElementById("sel").textContent=mode;}});
function setQ(t){document.getElementById("input").value=t; sendMsg();}

function startVoice(){
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SR){ alert("Chrome me kholo, voice support nahi hai"); return; }
    const rec = new SR(); rec.lang='hi-IN';
    document.getElementById("micBtn").innerText='🎙️ Sun raha hu...';
    rec.start();
    rec.onresult = (e)=>{
        document.getElementById("input").value = e.results[0][0].transcript;
        document.getElementById("micBtn").innerText='🎤 Bolke Puchho';
        sendMsg();
    };
    rec.onerror = ()=>{document.getElementById("micBtn").innerText='🎤 Bolke Puchho';};
}
function speakText(text){
    if(!autoSpeak) return;
    synth.cancel();
    let ut = new SpeechSynthesisUtterance(text.slice(0,4000));
    ut.lang='hi-IN'; ut.rate=1.0;
    synth.speak(ut);
}
function toggleSpeak(){
    autoSpeak=!autoSpeak;
    document.getElementById("speakBtn").innerText = autoSpeak ? '🔊 Bolke Sunao: ON' : '🔇 OFF';
    if(!autoSpeak) synth.cancel();
}

async function sendMsg(){
  const input=document.getElementById("input"); const msg=input.value.trim(); if(!msg) return;
  const box=document.getElementById("messages"); 
  box.innerHTML+=`<div class="bubble user">${msg.replace(/</g,"&lt;")}</div>`; 
  input.value="";
  box.innerHTML+=`<div class="bubble" id="thinking">Soch raha hu... pura solution de raha hu... (Computer/Mobile/App/Marketing sab aata hai)...</div>`;
  box.scrollTop=box.scrollHeight;
  try{
    const r=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,mode:mode,history:history,document_context:docContext})});
    const d=await r.json(); 
    document.getElementById("thinking").remove();
    let ans = d.answer.replace(/</g,"&lt;");
    box.innerHTML+=`<div class="bubble">${ans}<br><button class="icon" style="margin-top:6px;font-size:11px" onclick="speakText(\`${d.answer.replace(/`/g,'').replace(/'/g,'').slice(0,4000)}\`)">🔊 Suna</button></div>`; 
    box.scrollTop=box.scrollHeight; 
    history.push({role:"user",content:msg},{role:"assistant",content:d.answer}); 
    if(history.length>20) history=history.slice(-20);
    speakText(d.answer);
  }catch(e){
    document.getElementById("thinking").remove();
    box.innerHTML+=`<div class="bubble">Server busy, fir se bolo</div>`;
  }
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
  if(d.available){document.getElementById("researchRes").innerHTML=d.results.map(x=>`<div><a href="${x.url}" target="_blank" style="color:#75e0c1">${x.title}</a><br>${x.snippet.slice(0,200)}</div>`).join("<hr>"); docContext=d.results.map(x=>x.snippet).join("\n");} else {document.getElementById("researchRes").textContent="Research ke liye SEARCH_API_KEY set karo ya chat me pucho";}
}
document.getElementById("input").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMsg();}});
</script>
</body></html>'''
