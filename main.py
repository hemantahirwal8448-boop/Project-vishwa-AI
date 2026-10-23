 # main.py - Vishwa AI V4.0 - DOST MODE - FINAL
import os
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import google.generativeai as genai
import fitz
import docx
from PIL import Image

app = Flask(__name__)
CORS(app)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

DOST_SYSTEM_PROMPT = """
Tu Vishwa AI hai, par tu robot nahi hai. Tu user ka sabse accha DOST hai.
Tu Indore ka smart, samajhdar, funny dost hai. 'bhai', 'yaar' bol ke baat karta hai.
Tu sirf jawab nahi deta, apne dimaag se sochta hai aur aage ka plan batata hai.
Tujhe duniyadari pata hai - paisa, career, client handle karna sab.
Tu proactive hai, har jawab ke end me agla step puchta hai.
Kabhi "As an AI" mat bolna. Jis language me user bole usi me bol. Default Hinglish.
"""

chat_sessions = {}
def get_chat_session(session_id):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = model.start_chat(history=[
            {"role": "user", "parts": [DOST_SYSTEM_PROMPT]},
            {"role": "model", "parts": ["Samajh gaya bhai! Ab se main tera dost Vishwa hu. Bata kya haal hai?"]}
        ])
    return chat_sessions[session_id]

def read_document(file_storage):
    filename = file_storage.filename.lower()
    text = ""
    try:
        if filename.endswith('.pdf'):
            pdf_bytes = file_storage.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc: text += page.get_text()
        elif filename.endswith('.docx'):
            d = docx.Document(file_storage)
            text = "\n".join([p.text for p in d.paragraphs])
        elif filename.endswith('.txt'):
            text = file_storage.read().decode('utf-8')
    except Exception as e:
        text = f"Error: {e}"
    return text[:15000]

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head><title>Vishwa AI - Tera Dost</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#000;color:#fff;font-family:sans-serif;margin:0;display:flex;flex-direction:column;height:100vh}
#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column}
.msg{margin:8px 0;padding:12px 16px;border-radius:18px;max-width:85%;word-wrap:break-word}
.user{background:#1a73e8;align-self:flex-end}
.ai{background:#222;align-self:flex-start}
#inputArea{display:flex;padding:12px;background:#111;align-items:center;gap:8px}
#plusBtn{font-size:24px;background:#222;border:none;color:#fff;width:44px;height:44px;border-radius:50%;cursor:pointer}
#plusMenu{position:absolute;bottom:70px;left:12px;background:#222;border-radius:12px;padding:8px;display:none;flex-direction:column;z-index:10}
#plusMenu button{background:none;border:none;color:#fff;padding:12px;text-align:left;cursor:pointer;border-radius:8px}
#plusMenu button:hover{background:#333}
#textInput{flex:1;background:#222;border:none;color:#fff;padding:12px 16px;border-radius:24px;outline:none}
</style>
</head>
<body>
<div id="chat"><div class="msg ai">Haan bhai! Main Vishwa, tera dost. Bol kya kaam hai? 😎</div></div>
<div style="position:relative">
  <div id="plusMenu">
    <button onclick="triggerUpload('image')">🖼️ Image Bhejo</button>
    <button onclick="triggerUpload('doc')">📄 Document Bhejo</button>
  </div>
  <div id="inputArea">
    <button id="plusBtn" onclick="togglePlus()">+</button>
    <input id="textInput" placeholder="Kuch bhi bol bhai..." onkeypress="if(event.key==='Enter')sendMsg()">
    <button onclick="sendMsg()" style="background:#1a73e8;border:none;color:#fff;padding:10px 18px;border-radius:20px;cursor:pointer">➤</button>
  </div>
</div>
<input type="file" id="fileInput" hidden onchange="handleFile(this)">
<script>
let plusOpen=false;
function togglePlus(){plusOpen=!plusOpen;document.getElementById('plusMenu').style.display=plusOpen?'flex':'none'}
function triggerUpload(type){
  const inp=document.getElementById('fileInput');
  inp.accept=type=='image'?'image/*':'.pdf,.docx,.txt';
  inp.click();togglePlus();
}
async function handleFile(input){
  const file=input.files[0];if(!file)return;
  const chat=document.getElementById('chat');
  chat.innerHTML+=`<div class="msg user">📎 ${file.name}</div>`;
  const fd=new FormData();fd.append('file',file);
  fd.append('message',document.getElementById('textInput').value||'Is file ko dekh ke dost ki tarah bata isme kya hai');
  chat.scrollTop=chat.scrollHeight;
  const res=await fetch('/upload',{method:'POST',body:fd});
  const data=await res.json();
  chat.innerHTML+=`<div class="msg ai">${data.reply.replace(/\\n/g,'<br>')}</div>`;
  chat.scrollTop=chat.scrollHeight;
}
async function sendMsg(){
  const inp=document.getElementById('textInput');const txt=inp.value.trim();if(!txt)return;
  const chat=document.getElementById('chat');chat.innerHTML+=`<div class="msg user">${txt}</div>`;inp.value='';
  chat.scrollTop=chat.scrollHeight;
  const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:txt,session_id:'default'})});
  const data=await res.json();
  chat.innerHTML+=`<div class="msg ai">${data.reply.replace(/\\n/g,'<br>')}</div>`;
  chat.scrollTop=chat.scrollHeight;
}
</script>
</body>
</html>
    """)

@app.route('/chat', methods=['POST'])
def chat():
    data=request.json
    chat_obj=get_chat_session(data.get('session_id','default'))
    response=chat_obj.send_message(data.get('message'))
    return jsonify({"reply": response.text})

@app.route('/upload', methods=['POST'])
def upload():
    file=request.files.get('file')
    user_msg=request.form.get('message','Is file ko dekh ke bata')
    chat_obj=get_chat_session('default')
    if file.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
        img=Image.open(file.stream)
        response=chat_obj.send_message([user_msg, img])
    else:
        doc_text=read_document(file)
        response=chat_obj.send_message(f"{user_msg}\n\nDocument content:\n{doc_text}\n\nAb dost ki tarah jawab de.")
    return jsonify({"reply": response.text})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
