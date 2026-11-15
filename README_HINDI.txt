PROJECT VISHWA AI — COMBO 3.3.0
================================
यह source package एक multilingual AI assistant website/backend, installable PWA shell, और Android phone/Android TV WebView app source को एक साथ रखता है। यह production-certified enterprise service नहीं है। बाहरी providers और owner accounts configure करना आवश्यक है।

वेबसाइट में शामिल source features
---------------------------------
1. OpenAI-compatible AI Chat (Groq जैसे provider से)
2. PDF/DOCX/TXT/MD/CSV/JSON/PY/HTML/XML पढ़ना
3. Image input (चुने गए AI model में vision support जरूरी)
4. Browser voice input/output (browser/device support और permissions पर निर्भर)
5. SQLite chat history
6. Tavily Web Search integration (API key आवश्यक)
7. Browser print-to-PDF export
8. Email OTP और Google OAuth login (credentials आवश्यक)
9. Signed-in account data export और account/chat deletion
9. Admin dashboard + email allowlist
10. Optional one-time Razorpay checkout + server-side payment verification
11. Request rate limits, upload limits, secure cookie options, security headers
12. Installable PWA manifest/service worker/icons
13. Android phone + Android TV Kotlin wrapper source और GitHub Actions build workflow
14. Privacy policy template page (owner details भरना अनिवार्य)

GITHUB / RENDER
---------------
ZIP को Extract करें। Extracted contents (अंदर की files/folders) GitHub repository ROOT में upload करें; ZIP को सीधे repository में न डालें। Root में main.py, requirements.txt, render.yaml, templates/, static/, tests/, android/ और .github/ दिखना चाहिए।

Render Build Command:
pip install -r requirements.txt

Render Start Command:
gunicorn main:app --workers 1 --threads 4 --timeout 90

Render Environment Variables — AI के लिए जरूरी
----------------------------------------------
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=अपनी निजी provider key (Render Secret में ही)
AI_MODEL=openai/gpt-oss-20b (या provider में उपलब्ध compatible model)
FLASK_SECRET_KEY=लंबी random secret (Render generateValue)
COOKIE_SECURE=true

Optional integrations
---------------------
SEARCH_API_KEY=Tavily API key
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM=Email OTP के लिए SMTP
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI=Google OAuth
ADMIN_EMAILS=verified admin email addresses, comma-separated
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, PAYMENT_AMOUNT_PAISE=one-time payment
DATABASE_PATH=vishwa_ai.db (स्थायी data के लिए persistent disk/PostgreSQL migration/configuration जरूरी)

Google OAuth redirect URI:
https://YOUR-APP.onrender.com/api/auth/google/callback

डेटाबेस
-------
वर्तमान backend SQLite है। Render free instance की local filesystem ephemeral हो सकती है; इसलिए permanent chat history की गारंटी नहीं। वास्तविक launch से पहले persistent disk या managed PostgreSQL, backup और restore test लगाएँ। एक से अधिक server instance चलाने पर SQLite rate-limit/database design पर्याप्त नहीं है; PostgreSQL migration करें।

PWA / मोबाइल वेबसाइट
-------------------
HTTPS domain पर Android Chrome से वेबसाइट खोलें और browser menu में Install app / Add to Home screen चुनें। PWA installability browser/OS criteria पर निर्भर है। AI और account APIs online चाहिए; service worker केवल static shell cache करता है।

Android / Android TV
--------------------
Native source android/ में है। यह phone और Android TV दोनों के लिए launcher entries रखता है और उसी HTTPS website को WebView में खोलता है। GitHub Actions workflow .github/workflows/android.yml debug APK बनाता है; release AAB तभी बनेगा जब repository secrets में signing keystore values configure हों। निर्देश ANDROID_BUILD_HINDI.txt में हैं।
यह package compiled APK/AAB नहीं देता। Android SDK/Gradle build और वास्तविक device/TV testing GitHub Actions या Android Studio में करनी होगी। Native WebView में Google OAuth और Razorpay checkout की compatibility अलग से वास्तविक डिवाइस पर जाँचें; Google sign-in के लिए जरूरत पड़ने पर native OAuth/Custom Tabs callback integration करना होगा। Samsung Tizen और LG webOS app इसमें नहीं हैं।

Privacy policy
--------------
/privacy page पर policy template है। Play Store पर भेजने से पहले [OWNER LEGAL NAME] और [SUPPORT EMAIL] बदलें, policy को वास्तविक data flow के अनुरूप review करें और सार्वजनिक URL पर उपलब्ध रखें। Terms, refund policy, data deletion process, support contact और applicable legal requirements भी owner को final करने होंगे।

Payment
-------
Razorpay checkout default में बंद है। Test mode में order, captured payment, refund, webhook reconciliation, subscriptions, invoices, tax, plan entitlements और customer support flow अभी पूर्ण billing platform के रूप में शामिल नहीं हैं। असली ग्राहक से भुगतान लेने से पहले test mode, legal/business details और refund process तैयार करें।

Security / launch checklist
---------------------------
- API keys केवल Render Secrets में रखें; GitHub में नहीं।
- AI model की chat और vision compatibility provider dashboard से verify करें।
- Google OAuth consent screen और exact redirect URI configure करें।
- SMTP sender/domain verification करें।
- SEARCH_API_KEY जोड़कर search test करें।
- Razorpay test mode में पूरा payment lifecycle जाँचें।
- Persistent DB, backups, restore, deletion और retention लागू करें।
- Privacy policy placeholders और Terms of Service final करें।
- Android release keystore सुरक्षित रखें; signed AAB बनाकर phone + Android TV test करें।
- Play Console developer account, app listing, screenshots, app content/data safety declarations, age rating और review owner पूरा करे।
- Independent security, accessibility, load and privacy review के बिना इसे enterprise-certified न कहें।

TESTING
-------
Python syntax: python -m py_compile main.py
JavaScript syntax: node --check static/app.js && node --check static/service-worker.js
Automated tests: pip install -r requirements.txt && python -m pytest -q
Flask/AI/provider, OAuth, SMTP, Razorpay, Android build, Play Store review और Android TV physical-device tests इस package creation environment में execute नहीं किए गए।

ईमानदार स्थिति
--------------
यह पूरा source bundle है जिसमें website/PWA/Android wrapper source और integrations के code paths हैं। लेकिन बाहरी credentials, persistent hosting/database, legal owner details, signed Android build, Play Console submission और live end-to-end testing user/operator के accounts और devices से करना जरूरी है। इन्हें ZIP में fake या pre-activated नहीं बताया गया है।
