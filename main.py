# main.py - Vishwa AI V4.3 - SARI CHIJO WALA + ERROR FIXED - FINAL
import os
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import google.generativeai as genai
import fitz
import docx
from PIL import Image

app = Flask(__name__)
CORS(app)

api_key = os.getenv("GEMINI_API_KEY")
model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("Model OK")
    except Exception as e:
        print("API Key Error:", e)
else:
    print("API Key Missing!")

DOST_SYSTEM_PROMPT = "Tu Vishwa AI hai, tu user ka sabse accha DOST hai. Indore ka smart, samajhdar, funny dost hai. 'bhai', 'yaar' bol ke baat karta hai. Kabhi 'As an AI' mat bolna. Default Hinglish me baat kar."

chat_sessions = {}
def get_chat_session(sid):
    if not model:
        return None
    if sid not in chat_sessions:
        chat_sessions[sid] = model.start_chat(history=[
            {"role": "user", "parts": [DOST_SYSTEM_PROMPT]},
            {"role": "model", "parts": ["Samajh gaya bhai! Ab se main tera dost Vishwa hu."]}
        ])
    return chat_sessions[sid]

def read_document(f):
    name = f.filename.lower()
    txt = ""
    try:
        if name.endswith('.pdf'):
            pdf_bytes = f.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for p in doc:
                txt += p.get_text()
        elif name.endswith('.docx'):
            d = docx.Document(f)
            txt = "\n".join([para.text for para in d.paragraphs])
        elif name.endswith('.txt'):
            txt = f.read().decode('utf-8', errors='ignore')
    except Exception as e:
        txt = "Error: " + str(e)
    return txt[:15000]

@app.route('/health')
def health():
    return "ok", 200

@app.route('/')
def index():
    html = """
<!DOCTYPE html><html><head><title>Vishwa AI - Sari Chije Wala</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#000;color:#fff;font-family:sans-serif;margin:0;display:flex;flex-direction:column;height:100vh}
#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column}
.msg{margin:8px 0;padding:12px 16px;border-radius:18px;max-width:85%;word-wrap:break-word;white-space:pre-wrap}
.user{background:#1a73e8;align-self:flex-end}
.ai{background:#222;align-self:flex-start}
#bottom{padding:12px;background:#111}
#quickBtns{display:flex;gap:8px;margin-bottom:12px;overflow-x:auto}
.qbtn{background:#222;border:1px solid #333;color:#fff;padding:8px 14px;border-radius:20px;white-space:nowrap;cursor:pointer;font-size:14px}
#inputArea{display:flex;gap:8px;align-items:center}
#textInput{flex:1;background:#222;border:none;color:#fff;padding:12px 16px;border-radius:24px;outline:none}
#sendBtn{background:#1a73e8;border:none;color:#fff;padding:12px 18px;border-radius:20px;font-weight:bold}
</style></head><body>
<div id="chat"><div class="msg ai">Haan bhai! Main Vishwa, tera dost. Bol kya kaam hai? Photo, PDF sab bhej sakta hai ab.</div></div>
<div id="bottom">
<div id="quickBtns">
<button class="qbtn" onclick="triggerUpload('image')">📷 Photo</button>
<button class="qbtn" onclick="triggerUpload('doc')">📄 Document</button>
<button class="qbtn" onclick="alert('Voice feature kal tak aa jayega bhai!')">🎤 Voice</button>
<button class="qbtn" onclick="document.getElementById('textInput').value='Is photo ko samjha'; document.getElementById('textInput').focus()">🧠 Samjha</button>
</div>
<div id="inputArea"><input id="textInput" placeholder="Kuch bhi bol bhai..."><button id="sendBtn" onclick="sendMsg()">Send</button></div>
</div>
<input type="file" id="fileInput" hidden onchange="handleFile(this)">
<script>
function triggerUpload(t){var i=document.getElementById('fileInput');if(t=='image'){i.accept='image/*';}else{i.accept='.pdf,.docx,.txt';}i.click();}
async function handleFile(inp){
 var file=inp.files[0]; if(!file) return;
 var chat=document.getElementById('chat');
 chat.innerHTML+='<div class="msg user">📎 File: '+file.name+'</div>'; chat.scrollTop=chat.scrollHeight;
 var fd=new FormData(); fd.append('file',file); fd.append('message','Is file ko dost ki tarah samjha de bhai');
 try{
  var res=await fetch('/upload',{method:'POST',body:fd}); var data=await res.json();
  chat.innerHTML+='<div class="msg ai">'+data.reply+'</div>'; 
 }catch(e){ chat.innerHTML+='<div class="msg ai">Bhai file me error aa gaya: '+e+'</div>'; }
 chat.scrollTop=chat.scrollHeight; inp.value='';
}
async function sendMsg(){
 var inp=document.getElementById('textInput'); var txt=inp.value.trim(); if(!txt) return;
 var chat=document.getElementById('chat'); chat.innerHTML+='<div class="msg user">'+txt+'</div>'; inp.value=''; chat.scrollTop=chat.scrollHeight;
 try{
  var res