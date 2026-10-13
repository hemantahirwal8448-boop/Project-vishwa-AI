# Project Vishwa AI — MVP 2.8.0

A prototype foundation for a multi-purpose assistant. It is **not** a finished world-scale AI product.

## Included
- Responsive single-page interface and eight assistant modes.
- OpenAI-compatible chat connector configured only through server environment variables.
- Honest demo mode when no provider is configured.
- Health, status, and mode endpoints.
- Optional PDF text extraction endpoint and UI (5 MB limit; up to 40 pages; text capped at 12,000 characters). Uploaded PDF bytes are processed in memory and are not saved by this app. Scanned-image OCR is not included.
- Basic automated tests.
- Optional live web search endpoint (`POST /api/research`) using Tavily when `SEARCH_API_KEY` is configured. It returns source titles, snippets, and URLs; users must verify important claims.

## Run locally
1. Install Python 3.11 or newer.
2. `python -m venv .venv` then activate it.
3. `pip install -r requirements.txt`
4. `uvicorn main:app --reload`
5. Open `http://127.0.0.1:8000`.

## Connect a compatible AI API
Set server environment variables `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL`. For optional web research, set `SEARCH_API_KEY` using a Tavily key in the server environment. Search may have costs or limited free quotas; check the provider’s current terms before use. `AI_BASE_URL` should be the API base URL **without** `/chat/completions`; the app appends that route. Never put keys in frontend code, GitHub, screenshots, or chat. A successful request is needed to confirm the provider actually works. Provider costs and free limits vary.

## Deploy
`render.yaml` defines a free-plan attempt. Free availability, sleep limits, outbound access, and provider compatibility may change; deployment is not guaranteed. Set secrets in the hosting dashboard's environment settings. Do not add payment details unless you deliberately choose a paid plan.

## Run tests
`pytest -q`

## Monetization readiness (draft only)
- `GET /api/plans` returns a transparent draft of free, Plus, and Teams plans. Paid prices are deliberately unset.
- No checkout, payment collection, customer accounts, entitlements, or quota enforcement is implemented. Do not advertise paid access yet.
- Before charging anyone: validate demand, estimate AI/hosting costs, implement secure checkout and server-side entitlements, publish clear terms/privacy/refund support, and test payment webhooks.
- Suggested early approach: free pilot with a small group, talk to users about one concrete problem, then consider a simple paid tier only if people get reliable value. Revenue is not guaranteed.

## Not included yet
- Automatic search grounding inside every chat answer (the search endpoint is separate and must be explicitly called).
- OCR for scanned PDFs, persistent user accounts, database, chat history across sessions, rate limiting, admin tools, billing, analytics, mobile app, agent execution, robotics/device control.
- Security audit, privacy/legal review, production monitoring, load testing, or a public deployment verification.

## Safety and privacy
Do not upload confidential documents. PDF extraction is bounded, but a production deployment still needs stronger abuse controls and privacy review. Government, medical, legal, and financial answers must be checked against authoritative sources. This project does not guarantee income.


## Security baseline in v1.4.0

Responses include baseline browser security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Cross-Origin-Opener-Policy`). These headers do not replace HTTPS, authentication, abuse prevention, dependency updates, privacy review, or a production security assessment. Payments remain disabled; draft plan names are not a live subscription system.


## Version 1.0.0 additions
- `/api/model-check` makes a minimal live request to the configured OpenAI-compatible endpoint. A successful configuration alone is not treated as a successful connection.
- Web research results can be added as context to the next chat message. Search snippets are untrusted and must be checked at the linked sources.
- Model and search API credentials stay in server environment variables.

## Important status
This is still an MVP, not a complete global AI platform. No model or search service is bundled, and live connectivity requires valid provider credentials and may incur cost. Payments, user accounts, production monitoring, and independent security review are not implemented.


## Version 1.1.0 additions
- Lightweight in-process rate limit for chat, search, model-check, and PDF endpoints (default 30 requests/minute per client IP; configurable via `API_RATE_LIMIT_PER_MINUTE`).
- HTTP 429 responses include `Retry-After`.
- The limit is per process and resets on restart; it is a basic abuse guard only. Production needs a shared limiter, proxy-aware IP handling, monitoring, and a security review.


## Version 1.4.0 additions
- PDF uploads are read in bounded chunks and rejected as soon as they exceed 5 MB, instead of loading an arbitrarily large file into memory first.
- Web research input now uses a validated request schema with a maximum 400-character query.
- These improvements reduce some input-abuse risk but do not replace a production reverse proxy, shared rate limiter, malware scanning, or independent security review.


## Launch preflight (v1.4.0)

`GET /api/preflight` reports which environment integrations are configured and explicitly marks features that are not yet implemented or externally verified. It never returns secret values. A `launch_ready: false` result is expected for this MVP until real provider calls, authentication, persistence, security review, and deployment checks are completed.


## Version 1.4.0 verification notes
- UI version label now matches the backend version.
- The PDF endpoint rejects unexpected declared MIME types in addition to checking the filename and file size.
- The browser UI surfaces missing server configuration using the preflight endpoint.
- These changes do not mean the external AI/search providers are connected. Run `/api/model-check` after configuring server-side environment variables.


## Version 1.6.0: connection testing
- Added a visible **Test AI connection** button to the web interface. It calls `/api/model-check` and reports success or setup/provider failure without displaying credentials.
- Added mocked automated tests for a successful compatible-provider connection check and a successful chat response. These tests validate app behavior without making paid external API calls.
- A mocked test is not proof that a real provider key, account, quota, or live deployment works. Run the connection check in the deployed service after configuring credentials privately.


## v1.6.0 update
Adds /api/privacy explaining what this prototype stores and does not store; no chat history persistence.

These endpoints are diagnostic aids, not proof of a live model or public deployment.


## v1.7.0 update
Adds /api/limits documenting message, history, document and research limits in one machine-readable place.

These endpoints are diagnostic aids, not proof of a live model or public deployment.


## v1.8.0 update
Adds /api/ready to distinguish process liveness from required configuration readiness without claiming public launch.

These endpoints are diagnostic aids, not proof of a live model or public deployment.


## v1.9.0 update
Adds per-response X-Request-ID for troubleshooting without logging message content or secrets.

These endpoints are diagnostic aids, not proof of a live model or public deployment.


## v2.0.0 update
Adds a consolidated /api/diagnostics view combining version, readiness, privacy, and feature flags; still does not claim live deployment.

These endpoints are diagnostic aids, not proof of a live model or public deployment.


## Version 2.1.0: provider configuration safety
- Validates the configured model provider URL before sending requests. Remote providers must use HTTPS; HTTP is allowed only for loopback hosts used for local development.
- Rejects URLs containing embedded credentials, query strings, fragments, or an already-appended `/chat/completions` path.
- Adds a configurable `AI_TIMEOUT_SECONDS` (default 45 seconds, clamped to 5–90 seconds) to prevent unbounded waiting.
- Adds tests for rejected insecure URLs, allowed local URLs, secret non-disclosure, and timeout bounds.

These checks reduce common configuration mistakes; they are not a full security audit. Provider access and deployment still need a real external test.


## v2.2.0 database and feedback notes

- Optional feedback can use local SQLite or managed PostgreSQL (`DATABASE_URL`) only after the operator enables `ENABLE_FEEDBACK_STORAGE=true` and the submitter explicitly sets `consent_to_store: true`.
- Feedback is limited to `bug`, `idea`, or `other` and up to 1,000 characters. Do not submit personal details, passwords, API keys, or tokens.
- Chat history and uploaded PDFs are still not saved server-side.
- `GET /api/database-status` checks the selected database. `DATABASE_URL` selects managed PostgreSQL; otherwise `DATABASE_PATH` controls local SQLite (default: `vishwa_ai.db`).
- A successful local SQLite check does **not** prove durable storage on a cloud host. Some free hosts erase local files on restart; configure a persistent disk or managed database before relying on saved feedback.
- This release does not add user accounts or login. Public launch still requires a real provider test, deployment verification, security review, and mobile-device testing.


## Version 2.3.0: pre-launch verification tools
- Adds `scripts/smoke_test.py` to verify a deployed base URL's public health, modes, privacy, limits, preflight and diagnostics endpoints. It does not send chat content or test paid model calls by default.
- Adds a Hindi launch checklist and corrects privacy status so feedback-database availability is reported from an actual local check.
- Removes a duplicate allocation in the bounded PDF reader.
- This release is still not a claim of production readiness: live model credentials, persistent cloud storage, accounts, independent security review, device testing, and public deployment must be verified separately.


## v2.7.0 — safer default storage behavior
- Feedback database writes are disabled by default (`ENABLE_FEEDBACK_STORAGE=false`).
- The feedback API returns HTTP 503 until the operator deliberately enables storage after configuring durable storage.
- Database availability is reported separately from whether feedback writes are enabled.
- This avoids implying that a local SQLite file on ephemeral hosting is durable. Set `ENABLE_FEEDBACK_STORAGE=true` only after checking the hosting provider's persistent-disk/database configuration. For PostgreSQL, set `DATABASE_URL` only in the host environment dashboard; never commit it to Git.


## Release 2.8.0 notes
- GitHub Actions runs Python compile checks and pytest on pushes and pull requests.
- The release ZIP does not contain a generated local database.
- Read `SECURITY.md` and `RELEASE_STATUS_HI.md` before public use. This remains an MVP and is not security-audited production software.
