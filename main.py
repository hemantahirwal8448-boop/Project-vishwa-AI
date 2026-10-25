# main.py - Vishwa AI V4.4 - DEPLOY FIXED - FINAL
import os
from flask import Flask, request, jsonify
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
    except Exception as e:
        print("Key Error:", e)

DOST_PROMPT = "Tu Vishwa AI hai, Indore ka dost hai. Bhai yaar bol ke baat kar. Hinglish me jawab de."

chat_sessions = {}
def get_chat_session(sid):
    if not model:
        return None
    if sid not in chat_sessions:
        chat_sessions[sid] = model.start_chat(history=[
            {"role": "user", "parts": [DOST_PROMPT]},
            {"role": "model", "parts": ["Samajh gaya bhai! Main Vishwa hu."]}
        ])
    return chat_sessions[sid]

def read_doc(f):
    name = f.filename.lower()
    txt = ""
    try:
        if name.endswith('.pdf'):
            data = f.read()
            doc = fitz.open(stream=data, filetype="pdf")
            for p in doc:
                txt += p.get_text()
        elif name.endswith('.docx'):
            d = docx.Document(f)
            txt = "\n".join([para.text for para in d.paragraphs])
        else:
            txt = f.read().decode('utf-8', errors='ignore')
    except Exception as e:
        txt = str(e)
    return txt[:12000]

@app.route('/health')
def health():
    return "ok", 200

@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html>
<head>
<title>Vishwa AI</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#000;color:#fff;font-family:sans-serif;margin:0;display:flex;flex-direction:column;height:100vh}
#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column}
.msg{margin:8px 0;padding:12px 16px;border-radius:18px;max-width:85%;word-wrap:break-word;white-space:pre-wrap}
.user{background:#1a73e8;align-self:flex-end}
.ai{background:#222;align-self:flex-start}
#bottom{padding:12px;background:#111}
#quickBtns{display:flex;gap:8px;margin-bottom:12px;overflow-x:auto}
.qbtn{background:#222;border:1px solid #333;color:#fff;padding:8px 14px;border-radius:20px;cursor:pointer}
#inputArea{display:flex;gap:8px}
#textInput{flex:1;background:#222;border:none;color:#fff;padding:12px 16px;border-radius:24px;outline:none}
#sendBtn{background:#1a73e8;border:none;color:#fff;padding:12px 18px;border-radius:20px}
</style>
</head>
<body>
<div id="chat"><div class="msg ai">Haan bhai! Main Vishwa, tera dost. Bol kya kaam hai? Photo, PDF sab bhej sakta hai ab.</div></div>
<div id="bottom">
<div id="quickBtns">
<button class="qbtn" onclick="triggerUpload('image')">Photo</button>
<button class="qbtn" onclick="triggerUpload('doc')">Document</button>
<button class="qbtn" onclick="alert('Voice kal aayega bhai')">Voice</button>
</div>
<div id="inputArea">
<input id="textInput" placeholder="Kuch bhi bol bhai...">
<button id="sendBtn" onclick="sendMsg()">Send</button>
</div>
</div>
<input type="file" id="fileInput" hidden onchange="handleFile(this)">
<script>
function triggerUpload(t){
  var i=document.getElementById('fileInput');
  if(t=='image'){i.accept='image/*';} else {i.accept='.pdf,.docx,.txt';}
  i.click();
}
async function handleFile(inp){
  var file=inp.files[0]; if(!file) return;
  var chat=document.getElementById('chat');
  chat.innerHTML+='<div class="msg user">File: '+file.name+'</div>';
  chat.scrollTop=chat.scrollHeight;
  var fd=new FormData();
  fd.append('file',file);
  fd.append('message','Is file ko dost ki tarah samjha');
  try{
    var res=await fetch('/upload',{method:'POST',body:fd});
    var data=await res.json();
    chat.innerHTML+='<div class="msg ai">'+data.reply+'</div>';
  }catch(e){
    chat.innerHTML+='<div class="msg ai">Upload error: '+e+'</div>';
  }
  chat.scrollTop=chat.scrollHeight;
  inp.value='';
}
async function sendMsg(){
  var inp=document.getElementById('textInput');
  var txt=inp.value.trim();
  if(!txt) return;
  var chat=document.getElementById('chat');
  chat.innerHTML+='<div class="msg user">'+txt+'</div>';
  inp.value='';
  chat.scrollTop=chat.scrollHeight;
  try{
    var res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:txt,session_id:'default'})});
    var data=await res.json();
    chat.innerHTML+='<div class="msg ai">'+data.reply+'</div>';
  }catch(e){
    chat.innerHTML+='<div class="msg ai">Network error: '+e+'</div>';
  }
  chat.scrollTop=chat.scrollHeight;
}
document.getElementById('textInput').addEventListener('keypress',function(e){if(e.key==='Enter')sendMsg();});
</script>
</body>
</html>
'''

@app.route('/chat', methods=['POST'])
def chat_route():
    try:
        data = request.json
        sess = get_chat_session(data.get('session_id','default'))
        if not sess:
            return jsonify({"reply": "Bhai GEMINI_API_KEY Render me set nahi hai. Render > Environment me ja ke nayi key daal. aistudio.google.com/app/apikey se free milti hai."})
        resp = sess.send_message(data.get('message','hi'))
        return jsonify({"reply": resp.text})
    except Exception as e:
        return jsonify({"reply": "Error: " + str(e)[:300]})

@app.route('/upload', methods=['POST'])
def upload_route():
    try:
        f = request.files.get('file')
        msg = request.form.get('message','Is file ko dekh ke bata')
        sess = get_chat_session('default')
        if not sess:
            return jsonify({"reply": "API Key missing hai bhai, Environment me check kar."})
        if f.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
            img = Image.open(f.stream)
            resp = sess.send_message([msg, img])
        else:
            txt = read_doc(f)
            resp = sess.send_message(msg + "\n\nDocument:\n" + txt)
        return jsonify({"reply": resp.text})
    except Exception as e:
        return jsonify({"reply": "Upload Error: " + str(e)[:300]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))