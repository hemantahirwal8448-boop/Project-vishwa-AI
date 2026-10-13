# Project Vishwa AI — लॉन्च जाँच सूची (हिंदी)

यह सूची MVP को ईमानदारी से जाँचने के लिए है। कोई भी चेकलिस्ट अकेले शून्य-गलती की गारंटी नहीं देती।

## कोड/सर्वर पर किए जा सकने वाले परीक्षण
- [ ] `pip install -r requirements.txt`
- [ ] `pytest -q` — सभी परीक्षण पास हों
- [ ] `uvicorn main:app --host 0.0.0.0 --port 8000` से ऐप शुरू हो
- [ ] `/health`, `/api/modes`, `/api/privacy`, `/api/limits` सही JSON दें
- [ ] `/api/model-check` को केवल निजी server environment में provider settings डालने के बाद चलाएँ
- [ ] तैनाती के बाद `python scripts/smoke_test.py https://YOUR-SERVICE-URL` चलाएँ

## लाइव लॉन्च से पहले अनिवार्य बाहरी काम
- [ ] मालिक द्वारा चुने गए AI प्रदाता की वैध API key और मॉडल; key सिर्फ hosting Environment में रखें
- [ ] वास्तविक provider call सफल हो और प्रदाता की लागत/सीमाएँ समझी गई हों
- [ ] फ़ीडबैक/डेटा रखना हो तो durable storage configure करें; free-host local disk को स्थायी न मानें
- [ ] यूज़र अकाउंट चाहिए तो अलग से सुरक्षित authentication, password reset, session/CSRF controls और privacy policy implement तथा test हों
- [ ] सार्वजनिक deployment URL HTTPS पर खुले; smoke test पास हो
- [ ] Android फोन पर chat, mode buttons, PDF, errors, छोटे स्क्रीन और slow network की मैनुअल जाँच हो
- [ ] dependency/security review, logging/monitoring, abuse limits, privacy notice और incident/recovery plan की समीक्षा हो
- [ ] भुगतान तब तक बंद रखें जब तक checkout, webhook verification, refunds/terms, entitlements और खर्च की जाँच पूरी न हो

## अभी स्पष्ट सीमाएँ
- इस MVP में user login/accounts, paid checkout, persistent chat history, OCR और पूर्ण production security audit शामिल नहीं हैं।
- Smoke test केवल सार्वजनिक endpoints की बुनियादी उपलब्धता जाँचता है; यह AI प्रदाता को call नहीं करता और launch readiness की घोषणा नहीं करता।
