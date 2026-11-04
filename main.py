"""
Project Vishwa AI — Flask single-file starter
Environment variables on Render:
  AI_BASE_URL=https://api.groq.com/openai/v1
  AI_API_KEY=your_secret_api_key
  AI_MODEL=openai/gpt-oss-20b
Optional:
  PORT (Render sets this automatically)

This is a working AI chat/file-reading starter, not a finished authentication/payment
platform. Google login and email/SMS OTP require separate OAuth/email/SMS providers.
"""
import os
import io
import logging
from collections import defaultdict

import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    import docx
except ImportError:
    docx = None
try:
    from PIL import Image
except ImportError:
    Image = None

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
logging.basicConfig(level=logging.INFO)

BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
API_KEY = os.getenv("AI_API_KEY", "").strip()
MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-20b").strip()
TIMEOUT = 60
MAX_HISTORY = 16
histories = defaultdict(list)

SYSTEM_PROMPT = """You are Project Vishwa AI, a helpful and honest assistant.
Reply in the language the user uses, including Hindi or Hinglish. Give clear,
useful answers. Do not claim you performed actions you did not perform. Be honest
about uncertainty. Never reveal secrets, API keys, or internal configuration."""


def read_file(file):
    name = (file.filename or "").lower()
    raw = file.read()
    if name.endswith(".pdf"):
        if fitz is None:
            raise ValueError("PDF support missing. Add PyMuPDF to requirements.txt.")
        pdf = fitz.open(stream=raw, filetype="pdf")
        return "\n".join(page.get_text() for page in pdf)[:18000]
    if name.endswith(".docx"):
        if docx is None:
            raise ValueError("DOCX support missing. Add python-docx to requirements.txt.")
        document = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in document.paragraphs)[:18000]
    if name.endswith((".txt", ".md", ".csv", ".json", ".py", ".html", ".xml")):
        return raw.decode("utf-8", errors="replace")[:18000]
    raise ValueError("Supported files: PDF, DOCX, TXT, MD, CSV, JSON, PY, HTML, XML.")


def ask_ai(messages):
    if not API_KEY:
        raise RuntimeError("AI_API_KEY Render Environment में सेट नहीं है.")
    if not BASE_URL.startswith("https://"):
        raise RuntimeError("AI_BASE_URL में provider का HTTPS API base URL रखें.")
    url = BASE_URL + "/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        raise RuntimeError("AI provider ने समय पर जवाब नहीं दिया. फिर प्रयास करें.")
    except requests.RequestException:
        raise RuntimeError("AI provider से कनेक्शन नहीं हुआ. AI_BASE_URL जाँचें.")

    if r.status_code >= 400:
        if r.status_code in (401, 403):
            msg = "API key गलत है या provider ने अनुमति नहीं दी. AI_API_KEY जाँचें."
        elif r.status_code == 404:
            msg = "मॉडल या API endpoint नहीं मिला. AI_BASE_URL और AI_MODEL जाँचें."
        elif r.status_code == 429:
            msg = "Provider की rate limit या quota पूरी है. कुछ देर बाद प्रयास करें."
        else:
            msg = f"AI provider ने HTTP {r.status_code} दिया. Render Logs देखें."
        # Log response detail without logging the API key.
        app.logger.warning("Provider error %s: %s", r.status_code, r.text[:300])
        raise RuntimeError(msg)
    try:
        data = r.json()
        answer = data["choices"][0]["message"]["content"]
        if isinstance(answer, list):
            answer = "\n".join(x.get("text", "") for x in answer if isinstance(x, dict))
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError()
        return answer.strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("Provider का जवाब समझ नहीं आया. AI_MODEL और provider compatibility जाँचें.")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "Project Vishwa AI", "version": "5.0"})


@app.get("/api/status")
def status():
    return jsonify({
        "app": "Project Vishwa AI",
        "version": "5.0",
        "api_key_configured": bool(API_KEY),
        "model": MODEL,
        "auth": "not configured",
        "note": "Google login/OTP need OAuth and email/SMS provider setup."
    })


@app.get("/")
def home():
    return render_template_string(HTML, model=MODEL)


@app.post("/chat")
@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    text = str(data.get("message", "")).strip()
    sid = str(data.get("session_id", "default"))[:80]
    if not text:
        return jsonify({"reply": "अपना सवाल लिखें."}), 400
    if len(text) > 12000:
        return jsonify({"reply": "सवाल बहुत लंबा है. छोटा करके भेजें."}), 413
    histories[sid].append({"role": "user", "content": text})
    histories[sid] = histories[sid][-MAX_HISTORY:]
    try:
        answer = ask_ai(histories[sid])
        histories[sid].append({"role": "assistant", "content": answer})
        histories[sid] = histories[sid][-MAX_HISTORY:]
        return jsonify({"reply": answer, "model": MODEL})
    except RuntimeError as e:
        if histories[sid] and histories[sid][-1]["role"] == "user":
            histories[sid].pop()
        return jsonify({"reply": str(e)}), 502
    except Exception:
        app.logger.exception("Unexpected chat error")
        return jsonify({"reply": "तकनीकी समस्या आई. बाद में फिर प्रयास करें."}), 500


@app.post("/upload")
@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"reply": "पहले कोई फ़ाइल चुनें."}), 400
    sid = str(request.form.get("session_id", "default"))[:80]
    prompt = str(request.form.get("message", "इस फ़ाइल को हिंदी में समझाएँ."))[:1500]
    try:
        name = f.filename.lower()
        if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            # Vision support differs by provider; encode image as a data URL.
            import base64
            raw = f.read()
            mime = f.mimetype or "image/jpeg"
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")}}
            ]
            messages = histories[sid][-MAX_HISTORY:] + [{"role": "user", "content": content}]
        else:
            text = read_file(f)
            messages = histories[sid][-MAX_HISTORY:] + [{
                "role": "user",
                "content": prompt + "\n\nफ़ाइल: " + f.filename + "\n\nसामग्री:\n" + (text or "(पढ़ने योग्य टेक्स्ट नहीं मिला)")
            }]
        answer = ask_ai(messages)
        histories[sid].append({"role": "user", "content": prompt + " [uploaded " + f.filename + "]"})
        histories[sid].append({"role": "assistant", "content": answer})
        histories[sid] = histories[sid][-MAX_HISTORY:]
        return jsonify({"reply": answer, "filename": f.filename, "model": MODEL})
    except (RuntimeError, ValueError) as e:
        return jsonify({"reply": str(e)}), 502
    except Exception:
        app.logger.exception("Upload error")
        return jsonify({"reply": "फ़ाइल पढ़ने या भेजने में समस्या आई."}), 500


@app.post("/api/model-check")
def model_check():
    try:
        answer = ask_ai([{"role": "user", "content": "Reply with OK only."}])
        return jsonify({"connected": True, "model": MODEL, "notice": "AI connection successful.", "reply": answer[:80]})
    except RuntimeError as e:
        return jsonify({"connected": False, "model": MODEL, "notice": str(e)}), 502


@app.post("/api/new-chat")
def new_chat():
    data = request.get_json(silent=True) or {}
    sid = str(data.get("session_id", "default"))[:80]
    histories.pop(sid, None)
    return jsonify({"ok": True, "reply": "नई चैट शुरू हो गई."})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"reply": "फ़ाइल 15 MB से बड़ी है. छोटी फ़ाइल भेजें."}), 413


HTML = r"""
<!doctype html><html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#090d16">
<title>Project Vishwa AI</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#090d16;color:#f4f6fb;font:16px system-ui,sans-serif;height:100dvh;display:flex;flex-direction:column}
header{padding:14px 16px;background:#101827;border-bottom:1px solid #263246;display:flex;justify-content:space-between;align-items:center}
.brand{font-size:19px;font-weight:750}.sub{font-size:12px;color:#a9b6ca;margin-top:3px}
button{cursor:pointer;border:1px solid #334155;border-radius:12px;background:#1b293d;color:white;padding:9px 12px}
#chat{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px;width:100%;max-width:900px;margin:auto}
.msg{max-width:90%;padding:12px 15px;border-radius:17px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}
.user{align-self:flex-end;background:#2563eb}.ai{align-self:flex-start;background:#182334;border:1px solid #29384d}
.actions{display:flex;gap:7px;margin-top:8px}.actions button{font-size:12px;padding:5px 9px}
#composer{background:#0e1522;border-top:1px solid #29384d;padding:12px;padding-bottom:max(12px,env(safe-area-inset-bottom))}
#tools,#form{max-width:900px;margin:0 auto;display:flex;gap:7px}#tools{overflow:auto;margin-bottom:10px}
#form textarea{flex:1;min-width:0;max-height:130px;resize:vertical;background:#182334;color:white;border:1px solid #334155;border-radius:15px;padding:12px;font:inherit}
.primary{background:#2563eb;border-color:#2563eb;font-weight:bold}.note{text-align:center;font-size:11px;color:#8492a8;margin-top:8px}
#file{display:none}@media(max-width:520px){#tools button{white-space:nowrap;padding:8px;font-size:13px}.msg{max-width:95%}}
</style></head><body>
<header><div><div class="brand">🌐 Project Vishwa AI</div><div class="sub">AI मॉडल: {{ model }}</div></div><button onclick="newChat()">नई चैट</button></header>
<main id="chat"><div class="msg ai">नमस्ते! मैं Vishwa AI हूँ। अपना सवाल हिंदी, Hinglish या English में पूछें। आप दस्तावेज़ भी अपलोड कर सकते हैं।</div></main>
<section id="composer"><div id="tools">
<button onclick="pick('image/*')">📷 फोटो</button><button onclick="pick('.pdf,.docx,.txt,.md,.csv,.json,.py,.html,.xml')">📄 फ़ाइल</button>
<button onclick="voice()">🎙️ बोलें</button><button onclick="toggleRead()">🔊 आवाज़: <span id="read">बंद</span></button><button onclick="check()">कनेक्शन जाँचें</button>
</div><form id="form" onsubmit="send(event)"><textarea id="input" rows="1" placeholder="अपना सवाल लिखें…"></textarea><button class="primary" id="send">भेजें</button></form>
<input id="file" type="file" hidden><div class="note">AI गलतियाँ कर सकता है। महत्वपूर्ण जानकारी की पुष्टि करें।</div></section>
<script>
const chatBox=document.getElementById('chat'),input=document.getElementById('input');
let sid=localStorage.getItem('vishwa_sid')||'v-'+Math.random().toString(36).slice(2);localStorage.setItem('vishwa_sid',sid);
let busy=false,readAloud=false;
function add(text,who){let d=document.createElement('div');d.className='msg '+who;let t=document.createElement('div');t.textContent=text;d.appendChild(t);
if(who==='ai'){let a=document.createElement('div');a.className='actions';let c=document.createElement('button');c.textContent='कॉपी';c.onclick=()=>navigator.clipboard?.writeText(text);let s=document.createElement('button');s.textContent='🔊 सुनें';s.onclick=()=>speak(text);a.append(c,s);d.appendChild(a);if(readAloud)speak(text);}
chatBox.appendChild(d);chatBox.scrollTop=chatBox.scrollHeight;return d;}
function setBusy(x){busy=x;document.getElementById('send').disabled=x;document.getElementById('send').textContent=x?'रुकें…':'भेजें';}
async function send(e){if(e)e.preventDefault();let message=input.value.trim();if(!message||busy)return;add(message,'user');input.value='';setBusy(true);let wait=add('जवाब तैयार हो रहा है…','ai');
try{let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,session_id:sid})});let d=await r.json();wait.remove();add(d.reply||'जवाब नहीं मिला.','ai');}
catch(err){wait.remove();add('नेटवर्क समस्या. इंटरनेट जाँचकर फिर कोशिश करें.','ai');}finally{setBusy(false);}}
function pick(accept){let f=document.getElementById('file');f.accept=accept;f.click();}
document.getElementById('file').onchange=async e=>{let f=e.target.files[0];if(!f)return;if(busy)return;add('फ़ाइल: '+f.name,'user');setBusy(true);let w=add('फ़ाइल पढ़ी जा रही है…','ai');let fd=new FormData();fd.append('file',f);fd.append('session_id',sid);fd.append('message','इस फ़ाइल या फोटो को ध्यान से देखकर हिंदी में समझाओ।');try{let r=await fetch('/api/upload',{method:'POST',body:fd});let d=await r.json();w.remove();add(d.reply||'जवाब नहीं मिला.','ai');}catch(err){w.remove();add('फ़ाइल भेजने में समस्या.','ai');}finally{setBusy(false);e.target.value='';}};
function speak(text){if(!('speechSynthesis'in window)){add('इस ब्राउज़र में आवाज़ उपलब्ध नहीं है.','ai');return;}speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(text);u.lang=/[\\u0900-\\u097F]/.test(text)?'hi-IN':'en-US';u.rate=1;speechSynthesis.speak(u);}
function toggleRead(){readAloud=!readAloud;document.getElementById('read').textContent=readAloud?'चालू':'बंद';}
function voice(){let SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){add('इस ब्राउज़र में आवाज़ पहचान उपलब्ध नहीं है. Chrome माइक्रोफ़ोन अनुमति जाँचें.','ai');return;}let r=new SR();r.lang='hi-IN';r.onresult=e=>{input.value=e.results[0][0].transcript;input.focus();};r.onerror=()=>add('आवाज़ पहचान नहीं पाई. माइक्रोफ़ोन अनुमति जाँचें.','ai');r.start();}
async function check(){let w=add('AI कनेक्शन जाँचा जा रहा है…','ai');try{let r=await fetch('/api/model-check',{method:'POST'});let d=await r.json();w.remove();add(d.notice||'जाँच पूरी हुई.','ai');}catch(e){w.remove();add('कनेक्शन जाँच नहीं हो सकी.','ai');}}
async function newChat(){try{await fetch('/api/new-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid})});}catch(e){}chatBox.innerHTML='';add('नई चैट शुरू हो गई. अपना सवाल लिखें.','ai');}
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
</script></body></html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
