# आज की तैनाती — आसान चेकलिस्ट

## 1. GitHub
- एक नई repository बनाएं, जैसे `Project-Vishwa-AI`.
- ZIP को फोन/कंप्यूटर पर extract करें। `Project-Vishwa-AI-v2.5.0` के अंदर की सभी files repository के root में रखें; ZIP को अकेले upload न करें।
- `main.py`, `requirements.txt`, `render.yaml`, `README.md`, `scripts/`, `tests/` root स्तर पर दिखने चाहिए।
- `.env` या API keys upload न करें। केवल `.env.example` रखें।

## 2. Render
- New → Web Service → GitHub repository चुनें।
- Runtime: Python; Build command: `pip install -r requirements.txt`.
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Health check path: `/health`.
- Free tier/availability may change; paid plan या card की माँग आए तो आगे न बढ़ें।

## 3. AI provider
Render dashboard → Environment में `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` सेट करें। Key निजी रखें। Provider की कीमत/मुफ़्त सीमा पहले जाँचें; API call से शुल्क लग सकता है।

## 4. लॉन्च जाँच
- `https://YOUR-SERVICE-URL/health` खोलें; status `ok` होना चाहिए।
- `/api/status` में `chat_mode` को `connected-model` देखना पर्याप्त नहीं है; इसके बाद `/api/model-check` को सफल होना चाहिए।
- इस package से चलाएँ: `python scripts/smoke_test.py https://YOUR-SERVICE-URL --check-model`.
- फोन से वास्तविक chat भेजकर जाँचें। किसी भी check में failure हो तो public launch रोकें और error देखें।

## सीमाएँ
इस MVP में user login, payment, persistent hosted database, independent security audit और public deployment पहले से सिद्ध नहीं हैं। Launch को बिना login वाला public demo/pilot ही कहें, जब तक ये अलग से बनाए और जाँचे न जाएँ।


### स्थायी डेटाबेस (वैकल्पिक)
- होस्टिंग डैशबोर्ड में managed PostgreSQL बनाकर उसका connection URL `DATABASE_URL` के रूप में server environment में रखें। URL को GitHub, README या चैट में न डालें।
- `ENABLE_FEEDBACK_STORAGE=true` तभी करें जब PostgreSQL कनेक्शन और डेटा retention/privacy नियम जाँच लिए हों। यह विकल्प डिफ़ॉल्ट रूप से बंद है।
- PostgreSQL सेट न होने पर ऐप SQLite fallback इस्तेमाल करता है; मुफ़्त host पर उसकी फ़ाइल स्थायी रहेगी, इसकी गारंटी नहीं है।


## नई रिलीज़ सावधानियाँ (v2.8.0)
- ZIP में स्थानीय `.db` फाइल नहीं रखी जाती।
- GitHub पर push करने के बाद Actions टैब में CI run सफल होना देखें।
- deploy के बाद `python scripts/smoke_test.py https://YOUR-SERVICE.onrender.com` चलाएँ।
- असली provider connection जाँचने के लिए ही `--check-model` जोड़ें; इससे provider को एक छोटा request भेजा जाएगा।
- बिना login/payments के demo ही लॉन्च करें; paid plans चालू न करें।
