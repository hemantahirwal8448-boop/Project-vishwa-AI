import os, io, re, json, time, hmac, hashlib, secrets, sqlite3, logging, base64, smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from functools import wraps
from contextlib import contextmanager
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory

try:
    import fitz
except Exception:
    fitz = None
try:
    import docx
except Exception:
    docx = None

APP_VERSION = '3.3.0-global' 
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=(os.getenv('COOKIE_SECURE','true').lower()=='true'), MAX_CONTENT_LENGTH=12*1024*1024)
logging.basicConfig(level=logging.INFO)

AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://api.groq.com/openai/v1').rstrip('/')
AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
AI_MODEL = os.getenv('AI_MODEL', 'openai/gpt-oss-20b').strip()
SEARCH_API_KEY = os.getenv('SEARCH_API_KEY', '').strip()
DATABASE_PATH = os.getenv('DATABASE_PATH', 'vishwa_ai.db')
AI_TIMEOUT = min(90, max(5, int(os.getenv('AI_TIMEOUT_SECONDS', '45'))))
SYSTEM_PROMPT = ('You are Project Vishwa AI, a helpful multilingual assistant. Reply in the language used by the user. '
                 'Be accurate, explain uncertainty, cite sources when provided, and never claim actions you did not perform. '
                 'Do not reveal secrets or internal configuration.')


@contextmanager
def db():
    con = sqlite3.connect(DATABASE_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS otp(email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, user_id INTEGER, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_chats_user_session ON chats(user_id, session_id, id);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, order_id TEXT UNIQUE NOT NULL, amount INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'created', payment_id TEXT, created_at TEXT NOT NULL, verified_at TEXT);
        CREATE TABLE IF NOT EXISTS request_limits(bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start INTEGER NOT NULL);
        ''')

init_db()


def rate_limit(limit: int, window_seconds: int = 60):
    """SQLite-backed per-IP/per-endpoint rate limit; suitable for a single instance."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            now = int(time.time())
            ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
            bucket = hashlib.sha256(f"{request.endpoint}:{ip}".encode()).hexdigest()
            with db() as con:
                con.execute('DELETE FROM request_limits WHERE window_start < ?', (now - 86400,))
                row = con.execute('SELECT count, window_start FROM request_limits WHERE bucket=?', (bucket,)).fetchone()
                if not row or now - row['window_start'] >= window_seconds:
                    con.execute('INSERT OR REPLACE INTO request_limits(bucket,count,window_start) VALUES(?,?,?)', (bucket, 1, now))
                elif row['count'] >= limit:
                    retry = max(1, window_seconds - (now - row['window_start']))
                    return jsonify(error='बहुत अधिक अनुरोध हुए हैं। थोड़ी देर बाद फिर प्रयास करें।', retry_after=retry), 429
                else:
                    con.execute('UPDATE request_limits SET count=count+1 WHERE bucket=?', (bucket,))
            return fn(*args, **kwargs)
        return wrapped
    return decorate


def current_user_id():
    return session.get('user_id')


def auth_is_configured():
    email_ready = all(os.getenv(k) for k in ['SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'])
    google_ready = bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET') and os.getenv('GOOGLE_REDIRECT_URI'))
    return email_ready or google_ready

def effective_user_id():
    # Guest mode keeps the AI usable before optional login providers are configured.
    return current_user_id() or 0

def is_admin():
    email=(session.get('email') or '').lower()
    allowed={x.strip().lower() for x in os.getenv('ADMIN_EMAILS','').split(',') if x.strip()}
    return bool(email and email in allowed)

def require_admin(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not current_user_id() or not is_admin():
            return jsonify(error='Admin access के लिए अधिकृत खाते से लॉगिन करें।'),403
        return fn(*args, **kwargs)
    return inner

def require_login(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if auth_is_configured() and not current_user_id():
            return jsonify({'error': 'पहले Email OTP या Google Login करें।'}), 401
        return fn(*args, **kwargs)
    return inner


def ai_call(messages, max_tokens=1800):
    if not AI_API_KEY:
        raise RuntimeError('AI_API_KEY Render Environment में सेट नहीं है।')
    if not AI_BASE_URL.startswith('https://'):
        raise RuntimeError('AI_BASE_URL में HTTPS API base URL रखें।')
    try:
        r = requests.post(AI_BASE_URL + '/chat/completions',
            headers={'Authorization': 'Bearer ' + AI_API_KEY, 'Content-Type': 'application/json'},
            json={'model': AI_MODEL, 'messages': [{'role':'system','content':SYSTEM_PROMPT}] + messages,
                  'temperature':0.65, 'max_tokens':max_tokens}, timeout=AI_TIMEOUT)
    except requests.Timeout:
        raise RuntimeError('AI provider ने समय पर जवाब नहीं दिया।')
    except requests.RequestException:
        raise RuntimeError('AI provider से कनेक्शन नहीं हुआ।')
    if r.status_code >= 400:
        if r.status_code in (401,403): msg='AI API key गलत है या अनुमति नहीं मिली।'
        elif r.status_code == 404: msg='मॉडल या API endpoint नहीं मिला।'
        elif r.status_code == 429: msg='AI provider की सीमा/कोटा पूरा है।'
        else: msg=f'AI provider ने HTTP {r.status_code} दिया।'
        app.logger.warning('AI provider HTTP %s: %s', r.status_code, r.text[:250])
        raise RuntimeError(msg)
    try:
        out = r.json()['choices'][0]['message']['content']
        if isinstance(out, list): out='\n'.join(x.get('text','') for x in out if isinstance(x,dict))
        if not isinstance(out,str) or not out.strip(): raise ValueError()
        return out.strip()
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError('AI provider का जवाब पढ़ा नहीं जा सका।')


def extract_file(file):
    name=(file.filename or '').lower(); raw=file.read()
    if len(raw)>10*1024*1024: raise ValueError('फ़ाइल 10 MB से छोटी रखें।')
    if name.endswith('.pdf'):
        if not fitz: raise ValueError('PDF पढ़ने के लिए PyMuPDF उपलब्ध नहीं है।')
        pdf=fitz.open(stream=raw,filetype='pdf')
        if len(pdf)>40: raise ValueError('PDF अधिकतम 40 पेज की हो सकती है।')
        return '\n'.join(p.get_text() for p in pdf)[:16000]
    if name.endswith('.docx'):
        if not docx: raise ValueError('DOCX support उपलब्ध नहीं है।')
        d=docx.Document(io.BytesIO(raw)); return '\n'.join(p.text for p in d.paragraphs)[:16000]
    if name.endswith(('.txt','.md','.csv','.json','.py','.html','.xml')):
        return raw.decode('utf-8',errors='replace')[:16000]
    raise ValueError('PDF, DOCX, TXT, MD, CSV, JSON, PY, HTML या XML फ़ाइल भेजें।')


def send_otp_email(to_email, code):
    host=os.getenv('SMTP_HOST',''); user=os.getenv('SMTP_USER',''); password=os.getenv('SMTP_PASSWORD','')
    sender=os.getenv('SMTP_FROM',user); port=int(os.getenv('SMTP_PORT','587'))
    if not all([host,user,password,sender]):
        raise RuntimeError('Email OTP चालू करने के लिए Render में SMTP_HOST, SMTP_USER, SMTP_PASSWORD और SMTP_FROM सेट करें।')
    msg=EmailMessage(); msg['Subject']='Project Vishwa AI login code'; msg['From']=sender; msg['To']=to_email
    msg.set_content(f'Your Project Vishwa AI login code is {code}. It expires in 10 minutes. Do not share it.')
    with smtplib.SMTP(host,port,timeout=20) as s:
        s.starttls(); s.login(user,password); s.send_message(msg)


@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'; resp.headers['X-Frame-Options']='DENY'
    resp.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy']='camera=(), microphone=(self), geolocation=()'
    resp.headers['Cache-Control']='no-store' if request.path.startswith('/api/') else 'no-cache'
    return resp

@app.get('/')
def home(): return render_template('index.html', model=AI_MODEL, version=APP_VERSION)

@app.get('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js', mimetype='application/javascript')

@app.get('/privacy')
def privacy_page():
    return render_template('privacy.html')

@app.get('/health')
def health(): return jsonify(status='ok', app='Project Vishwa AI', version=APP_VERSION)

@app.get('/api/status')
def status():
    return jsonify(app='Project Vishwa AI', version=APP_VERSION, ai_configured=bool(AI_API_KEY),
        search_configured=bool(SEARCH_API_KEY), email_otp_configured=all(os.getenv(k) for k in ['SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM']),
        google_login_configured=bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET') and os.getenv('GOOGLE_REDIRECT_URI')),
        payment_configured=bool(os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_KEY_SECRET')),
        logged_in=(bool(current_user_id()) or not auth_is_configured()), guest_mode=(not auth_is_configured()), is_admin=is_admin(), email=session.get('email') or ('Guest mode' if not auth_is_configured() else None))

@app.post('/api/auth/request-otp')
@rate_limit(5, 600)
def request_otp():
    email=(request.json or {}).get('email','').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): return jsonify(error='सही email address लिखें।'),400
    code=f'{secrets.randbelow(1000000):06d}'; digest=hashlib.sha256((code+app.secret_key).encode()).hexdigest()
    try: send_otp_email(email,code)
    except RuntimeError as e: return jsonify(error=str(e)),503
    except Exception: app.logger.exception('OTP email failed'); return jsonify(error='OTP email नहीं भेजा जा सका। SMTP सेटिंग जाँचें।'),502
    with db() as con: con.execute('INSERT OR REPLACE INTO otp(email,code_hash,expires_at,attempts) VALUES(?,?,?,0)',(email,digest,int(time.time())+600))
    return jsonify(ok=True,message='OTP भेज दिया गया है। 10 मिनट में उपयोग करें।')

@app.post('/api/auth/verify-otp')
@rate_limit(12, 600)
def verify_otp():
    data=request.json or {}; email=data.get('email','').strip().lower(); code=data.get('code','').strip()
    with db() as con:
        row=con.execute('SELECT * FROM otp WHERE email=?',(email,)).fetchone()
        if not row or row['expires_at']<time.time() or row['attempts']>=5:
            return jsonify(error='OTP समाप्त है या उपलब्ध नहीं है। नया OTP लें।'),400
        digest=hashlib.sha256((code+app.secret_key).encode()).hexdigest()
        if not hmac.compare_digest(digest,row['code_hash']):
            con.execute('UPDATE otp SET attempts=attempts+1 WHERE email=?',(email,)); return jsonify(error='OTP सही नहीं है।'),400
        con.execute('DELETE FROM otp WHERE email=?',(email,))
        con.execute('INSERT OR IGNORE INTO users(email,created_at) VALUES(?,?)',(email,datetime.now(timezone.utc).isoformat()))
        user=con.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
    session.clear(); session['user_id']=user['id']; session['email']=email
    return jsonify(ok=True,email=email)

@app.post('/api/auth/logout')
def logout(): session.clear(); return jsonify(ok=True)

@app.get('/api/account/export')
@require_login
def export_account_data():
    uid=current_user_id()
    if not uid: return jsonify(error='डेटा export के लिए पहले अपने खाते में लॉगिन करें।'),403
    with db() as con:
        user=con.execute('SELECT email,created_at FROM users WHERE id=?',(uid,)).fetchone()
        chats=con.execute('SELECT session_id,role,content,created_at FROM chats WHERE user_id=? ORDER BY id',(uid,)).fetchall()
    return jsonify(account=dict(user) if user else None, chats=[dict(x) for x in chats], exported_at=datetime.now(timezone.utc).isoformat())

@app.post('/api/account/delete')
@require_login
def delete_account():
    uid=current_user_id()
    if not uid: return jsonify(error='खाता हटाने के लिए पहले अपने खाते में लॉगिन करें।'),403
    with db() as con:
        user=con.execute('SELECT email FROM users WHERE id=?',(uid,)).fetchone()
        if not user: return jsonify(error='खाता नहीं मिला।'),404
        con.execute('DELETE FROM chats WHERE user_id=?',(uid,))
        con.execute('DELETE FROM otp WHERE email=?',(user['email'],))
        # Keep the minimum payment transaction record for reconciliation, but detach it from the deleted account.
        con.execute('UPDATE payments SET user_id=0 WHERE user_id=?',(uid,))
        con.execute('DELETE FROM users WHERE id=?',(uid,))
    session.clear()
    return jsonify(ok=True,message='खाता और चैट डेटा हटाया गया। भुगतान reconciliation के लिए transaction record पहचान से अलग रखा गया।')

@app.get('/api/auth/google')
def google_login():
    cid=os.getenv('GOOGLE_CLIENT_ID'); redirect_uri=os.getenv('GOOGLE_REDIRECT_URI')
    if not cid or not os.getenv('GOOGLE_CLIENT_SECRET') or not redirect_uri: return jsonify(error='Google Login के लिए CLIENT_ID, CLIENT_SECRET और REDIRECT_URI तीनों सेट करें।'),503
    state=secrets.token_urlsafe(24); session['oauth_state']=state
    params={'client_id':cid,'redirect_uri':redirect_uri,'response_type':'code','scope':'openid email profile','state':state,'prompt':'select_account'}
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params))

@app.get('/api/auth/google/callback')
def google_callback():
    if not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'): return 'Google OAuth not configured',503
    if not request.args.get('state') or request.args.get('state') != session.pop('oauth_state',None): return 'Invalid OAuth state',400
    try:
        token=requests.post('https://oauth2.googleapis.com/token',data={'code':request.args.get('code'),'client_id':os.getenv('GOOGLE_CLIENT_ID'),'client_secret':os.getenv('GOOGLE_CLIENT_SECRET'),'redirect_uri':os.getenv('GOOGLE_REDIRECT_URI'),'grant_type':'authorization_code'},timeout=20).json()
        info=requests.get('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+token['access_token']},timeout=20).json()
        email=info.get('email','').lower()
        if not info.get('email_verified') or not email: return 'Google email verification failed',403
        with db() as con:
            con.execute('INSERT OR IGNORE INTO users(email,created_at) VALUES(?,?)',(email,datetime.now(timezone.utc).isoformat()))
            uid=con.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()['id']
        session.clear(); session['user_id']=uid; session['email']=email
        return redirect('/')
    except Exception: app.logger.exception('Google OAuth callback failed'); return 'Google login failed. Check OAuth settings.',502

@app.post('/api/chat')
@rate_limit(30, 60)
@require_login
def chat():
    data=request.get_json(silent=True) or {}; text=str(data.get('message','')).strip(); sid=str(data.get('session_id','main'))[:80]
    if not text: return jsonify(error='अपना सवाल लिखें।'),400
    if len(text)>10000: return jsonify(error='सवाल बहुत लंबा है।'),413
    with db() as con:
        rows=con.execute('SELECT role,content FROM chats WHERE user_id=? AND session_id=? ORDER BY id DESC LIMIT 12',(effective_user_id(),sid)).fetchall()
    messages=[{'role':r['role'],'content':r['content']} for r in reversed(rows)]+[{'role':'user','content':text}]
    try: answer=ai_call(messages)
    except RuntimeError as e: return jsonify(error=str(e)),502
    with db() as con:
        now=datetime.now(timezone.utc).isoformat()
        con.executemany('INSERT INTO chats(user_id,session_id,role,content,created_at) VALUES(?,?,?,?,?)',[(effective_user_id(),sid,'user',text,now),(effective_user_id(),sid,'assistant',answer,now)])
    return jsonify(reply=answer,model=AI_MODEL)

@app.post('/api/upload')
@rate_limit(10, 60)
@require_login
def upload():
    f=request.files.get('file'); sid=str(request.form.get('session_id','main'))[:80]
    if not f or not f.filename: return jsonify(error='पहले फ़ाइल चुनें।'),400
    prompt=request.form.get('message','इस फ़ाइल को हिंदी में समझाएँ।')[:1000]
    try:
        if f.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
            raw=f.read()
            if len(raw)>5*1024*1024: return jsonify(error='Image 5 MB से छोटी रखें।'),413
            mime=f.mimetype or 'image/jpeg'
            content=[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii')}}]
        else:
            extracted=extract_file(f); content=prompt+'\n\nFile: '+f.filename+'\n\n'+(extracted or 'पढ़ने योग्य टेक्स्ट नहीं मिला।')
        answer=ai_call([{'role':'user','content':content}])
        with db() as con:
            now=datetime.now(timezone.utc).isoformat(); con.executemany('INSERT INTO chats(user_id,session_id,role,content,created_at) VALUES(?,?,?,?,?)',[(effective_user_id(),sid,'user',prompt+' [file: '+f.filename+']',now),(effective_user_id(),sid,'assistant',answer,now)])
        return jsonify(reply=answer,filename=f.filename)
    except (ValueError,RuntimeError) as e: return jsonify(error=str(e)),400
    except Exception: app.logger.exception('Upload failed'); return jsonify(error='फ़ाइल पढ़ने में समस्या आई।'),500

@app.get('/api/history')
@require_login
def history():
    sid=request.args.get('session_id','main')[:80]
    with db() as con: rows=con.execute('SELECT role,content,created_at FROM chats WHERE user_id=? AND session_id=? ORDER BY id DESC LIMIT 50',(effective_user_id(),sid)).fetchall()
    return jsonify(messages=[dict(r) for r in reversed(rows)])

@app.post('/api/new-chat')
@require_login
def new_chat():
    sid=str((request.json or {}).get('session_id','main'))[:80]
    with db() as con: con.execute('DELETE FROM chats WHERE user_id=? AND session_id=?',(effective_user_id(),sid))
    return jsonify(ok=True)

@app.post('/api/research')
@rate_limit(10, 60)
@require_login
def research():
    q=str((request.json or {}).get('query','')).strip()[:350]
    if not q: return jsonify(error='Search query लिखें।'),400
    if not SEARCH_API_KEY: return jsonify(error='Web Search चालू करने के लिए SEARCH_API_KEY सेट करें।'),503
    try:
        r=requests.post('https://api.tavily.com/search',json={'api_key':SEARCH_API_KEY,'query':q,'search_depth':'basic','max_results':5},timeout=25); r.raise_for_status(); data=r.json()
        results=[{'title':x.get('title',''),'url':x.get('url',''),'snippet':x.get('content','')[:700]} for x in data.get('results',[])]
        return jsonify(results=results)
    except Exception: app.logger.exception('Search failed'); return jsonify(error='Web search सेवा से जवाब नहीं मिला।'),502

@app.post('/api/model-check')
@rate_limit(5, 60)
@require_login
def model_check():
    try: return jsonify(connected=True,model=AI_MODEL,reply=ai_call([{'role':'user','content':'Reply only: OK'}],50))
    except RuntimeError as e: return jsonify(connected=False,error=str(e)),502

@app.get('/admin')
def admin_page():
    if not current_user_id() or not is_admin():
        return 'Admin access denied. Sign in with an email listed in ADMIN_EMAILS.', 403
    return render_template('admin.html')

@app.get('/api/admin/overview')
@require_admin
def admin_overview():
    with db() as con:
        users=con.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        chats=con.execute('SELECT COUNT(*) FROM chats').fetchone()[0]
        recent=con.execute('SELECT email,created_at FROM users ORDER BY id DESC LIMIT 25').fetchall()
    return jsonify(users=users, chat_messages=chats, recent_users=[dict(x) for x in recent])

@app.get('/api/payments/config')
def payment_config():
    key=os.getenv('RAZORPAY_KEY_ID','').strip()
    try: amount=int(os.getenv('PAYMENT_AMOUNT_PAISE','0'))
    except ValueError: amount=0
    return jsonify(enabled=bool(key and os.getenv('RAZORPAY_KEY_SECRET') and amount>=100), key_id=key if amount>=100 else None, amount=amount, currency='INR')

@app.post('/api/payments/create-order')
@rate_limit(5, 300)
@require_login
def create_payment_order():
    key=os.getenv('RAZORPAY_KEY_ID','').strip(); secret=os.getenv('RAZORPAY_KEY_SECRET','').strip()
    try: amount=int(os.getenv('PAYMENT_AMOUNT_PAISE','0'))
    except ValueError: amount=0
    if not key or not secret or amount<100:
        return jsonify(error='Payment अभी बंद है। Render में Razorpay keys और PAYMENT_AMOUNT_PAISE सेट करें।'),503
    try:
        r=requests.post('https://api.razorpay.com/v1/orders',auth=(key,secret),json={'amount':amount,'currency':'INR','receipt':'vishwa_'+secrets.token_hex(8)},timeout=20)
        if r.status_code>=400:
            app.logger.warning('Razorpay order failed HTTP %s',r.status_code)
            return jsonify(error='Payment provider order नहीं बना सका। Razorpay dashboard/settings जाँचें।'),502
        order=r.json(); order_id=order.get('id')
        if not order_id: return jsonify(error='Payment provider का order जवाब अधूरा है।'),502
        with db() as con:
            con.execute('INSERT INTO payments(user_id,order_id,amount,currency,status,created_at) VALUES(?,?,?,?,?,?)',
                (effective_user_id(),order_id,amount,'INR','created',datetime.now(timezone.utc).isoformat()))
        return jsonify(order_id=order_id,amount=amount,currency='INR',key_id=key)
    except Exception:
        app.logger.exception('Razorpay order request failed')
        return jsonify(error='Payment सेवा से कनेक्शन नहीं हुआ।'),502

@app.post('/api/payments/verify')
@require_login
def verify_payment():
    key=os.getenv('RAZORPAY_KEY_ID','').strip(); secret=os.getenv('RAZORPAY_KEY_SECRET','').strip()
    if not key or not secret: return jsonify(error='Razorpay सेटिंग उपलब्ध नहीं है।'),503
    data=request.get_json(silent=True) or {}
    order_id=str(data.get('razorpay_order_id','')); payment_id=str(data.get('razorpay_payment_id','')); signature=str(data.get('razorpay_signature',''))
    if not all([order_id,payment_id,signature]) or len(order_id)>100 or len(payment_id)>100:
        return jsonify(error='Payment verification data अधूरा है।'),400
    with db() as con:
        saved=con.execute('SELECT * FROM payments WHERE order_id=? AND user_id=?',(order_id,effective_user_id())).fetchone()
    if not saved: return jsonify(error='यह payment order इस खाते से जुड़ा नहीं मिला।'),404
    expected=hmac.new(secret.encode(),(order_id+'|'+payment_id).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): return jsonify(error='Payment signature सत्यापित नहीं हुआ।'),400
    try:
        r=requests.get('https://api.razorpay.com/v1/payments/'+payment_id,auth=(key,secret),timeout=20)
        if r.status_code>=400: return jsonify(error='Razorpay payment status सत्यापित नहीं हो सका।'),502
        pay=r.json()
        if pay.get('order_id')!=order_id or pay.get('status')!='captured' or pay.get('amount')!=saved['amount'] or pay.get('currency')!='INR':
            return jsonify(error='Payment captured नहीं है या order/amount मेल नहीं खाते।'),409
        with db() as con:
            con.execute('UPDATE payments SET status=?,payment_id=?,verified_at=? WHERE order_id=? AND user_id=?',
                ('captured',payment_id,datetime.now(timezone.utc).isoformat(),order_id,effective_user_id()))
        return jsonify(verified=True,status='captured',message='Payment captured और server पर सत्यापित हुआ।')
    except Exception:
        app.logger.exception('Razorpay verification failed')
        return jsonify(error='Payment सत्यापन सेवा से कनेक्शन नहीं हुआ।'),502

@app.get('/api/plans')
def plans():
    try: amount=int(os.getenv('PAYMENT_AMOUNT_PAISE','0'))
    except ValueError: amount=0
    return jsonify(note='Single configured Razorpay checkout; no recurring subscription system.',plans=[{'name':'Configured plan','price_paise':amount,'currency':'INR','status':'payment enabled' if amount>=100 and os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_KEY_SECRET') else 'payment disabled until Razorpay setup'}])

@app.get('/api/privacy')
def privacy(): return jsonify(auth='Email OTP / Google OAuth when configured',chat_storage='Chat text is stored in the configured database for signed-in users.',uploads='Uploaded files are processed in memory and not stored as files.',secrets='API keys are read from server environment variables and are not returned by APIs.')

@app.errorhandler(413)
def too_large(_): return jsonify(error='फ़ाइल बहुत बड़ी है।'),413

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
