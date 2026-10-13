# Project Vishwa AI — रिलीज़ स्थिति (v2.8.0)

## इस पैकेज में
- FastAPI ऐप और मोबाइल-अनुकूल इंटरफ़ेस
- 8 assistant modes
- कॉन्फ़िगर करने योग्य OpenAI-compatible model connector
- PDF text extraction (अधिकतम 5 MB; OCR शामिल नहीं)
- वैकल्पिक web search connector
- opt-in feedback endpoint (डिफ़ॉल्ट बंद)
- health, readiness, diagnostics और model connection-check endpoints
- GitHub Actions CI workflow और post-deploy smoke-test script

## सत्यापित
- स्थानीय `pytest` suite और Python compile check इस पैकेज पर चलाए गए हैं।
- CI workflow जोड़ा गया है; GitHub पर workflow चलने की पुष्टि repository में push करने के बाद ही होगी।
- इस environment से उपयोगकर्ता के GitHub/Render खाते पर deployment नहीं किया गया।

## अभी पूर्ण उत्पादन लॉन्च नहीं
- वास्तविक provider credentials और सफल live model request की पुष्टि नहीं हुई।
- Render deployment और public HTTPS URL की पुष्टि नहीं हुई।
- User accounts/login, password reset, account data, payments, shared rate limiter, production monitoring, backup/restore और independent security review शामिल नहीं हैं।
- SQLite file package में शामिल नहीं है; deploy के बाद app अपना local database बना सकती है। Cloud पर SQLite persistence के लिए persistent disk चाहिए; managed PostgreSQL के लिए `DATABASE_URL` चाहिए।

## पहला सार्वजनिक डेमो
बिना login/payment के एक सीमित demo तैनात किया जा सकता है, लेकिन इसे स्पष्ट रूप से prototype बताना होगा, secrets server-side रखने होंगे, और provider तथा public URL smoke tests सफल होने चाहिए। `LAUNCH_CHECKLIST_HI.md` का पालन करें।
