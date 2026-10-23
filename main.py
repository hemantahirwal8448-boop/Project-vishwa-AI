# main.py - Vishwa AI V4.0 - DOST MODE - FINAL RENDER FIXED
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
Kabhi "As an AI" mat bolna. Jis language me user bole usi me bol. Default Hinglish.
"""

chat_sessions = {}
def get_chat_session(session_id):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = model.start_chat(history=[
            {"role": "user", "parts": [DOST_SYSTEM_PROMPT]},
            {"role": "model", "parts": ["Samajh gaya bhai! Ab se main tera dost Vishwa hu."]}
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

@app.route('/health')
def health():
    return "ok", 200

@app.route('/')
def index():
    return render_template_string("""<!DOCTYPE html><html><head><title>Vishwa AI</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{background:#000;color:#fff;font-family:sans-serif;margin:0;display:flex;flex-direction:column;height:100vh}#chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column}.msg{margin:8px 0;padding:12px 16px;border-radius:18px;max-width:85%;word-wrap:break-word}.user{background:#1a73e8;align-self:flex-end}.ai{background:#222;align-self:flex-start}#inputArea{display:flex;padding:12px;background:#111;gap:8px}#plusBtn{font-size:24px;background:#222;border:none;color:#fff;width:44px;height:44px;border-radius:50%}#plusMenu{position:absolute;bottom:70px;left:12px;background:#222;border-radius:12px;padding:8px;display:none;flex-direction:column}#plusMenu button{background:none;border:none;color:#fff;padding:12px;text-align:left}#textInput