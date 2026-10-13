# Changelog

## 2.0.0
- Operational diagnostics: Adds a consolidated /api/diagnostics view combining version, readiness, privacy, and feature flags; still does not claim live deployment.
- Added regression tests for this feature.

# Changelog

## 1.9.0
- Request correlation IDs: Adds per-response X-Request-ID for troubleshooting without logging message content or secrets.
- Added regression tests for this feature.

# Changelog

## 1.8.0
- Readiness checks: Adds /api/ready to distinguish process liveness from required configuration readiness without claiming public launch.
- Added regression tests for this feature.

# Changelog

## 1.7.0
- Public limits endpoint: Adds /api/limits documenting message, history, document and research limits in one machine-readable place.
- Added regression tests for this feature.

# Changelog

## 1.6.0
- Privacy transparency endpoint: Adds /api/privacy explaining what this prototype stores and does not store; no chat history persistence.
- Added regression tests for this feature.

# Changelog

## 1.0.0
- Added an explicit live AI provider connection-check endpoint.
- Connected web research snippets to the next chat request as untrusted context.
- Clarified that configuration does not equal successful connectivity.
- Added tests for configuration status, secret non-disclosure, and research-to-chat UI wiring.
- Still requires real provider credentials and deployment testing.


## 1.1.0
- Add a basic in-process per-IP rate limit to selected POST APIs.
- Add Retry-After response for throttled requests.
- Update interface version badge and test coverage.
- Note that this is not production-grade distributed rate limiting.

## 1.2.0
- Bound PDF upload reads to the configured 5 MB limit while streaming chunks.
- Validate research request shape and maximum query length.
- Added regression tests for oversized and malformed research requests.


## 1.3.0
- Added `/api/preflight` for a safe, honest launch-readiness checklist.
- Explicitly reports that payments, accounts, persistent database, and public deployment verification are not enabled.
- Added tests for missing settings and secret non-disclosure.


## 1.4.0
- Fixed stale UI version label.
- Added a browser-facing preflight setup reminder.
- Added declared MIME-type validation for PDF uploads.
- Still requires live external-provider verification and deployment testing before launch.


## 1.5.0
- Added a UI button to run the AI provider connection check.
- Added mocked tests for successful provider-check and chat paths, including credential non-disclosure.
- Tests use a fake provider; real external connectivity still requires owner-configured settings and a live check.

## 2.1.0
- Validate provider URL safety before sending credentials.
- Allow HTTP only for loopback/local development hosts.
- Bound configurable provider timeout to 5–90 seconds.
- Add tests for URL validation and timeout handling.


## 2.2.0
- Added SQLite feedback storage with explicit consent and bounded input.
- Added a database availability endpoint without exposing filesystem paths or stored records.
- Added rate limiting for feedback submissions.
- Updated privacy and preflight disclosures to distinguish feedback storage from durable production storage.
- Added tests for consent, storage, secret-like text rejection, and privacy disclosures.

## v2.4.0: cleaner release bundle and optional live model smoke test
- Release ZIP excludes generated SQLite files, Python bytecode, and pytest caches.
- Updated UI and API version label to 2.4.0.
- `scripts/smoke_test.py` can optionally call `/api/model-check` using `--check-model` to verify one actual provider request on the deployed service.
- Basic smoke tests do not prove production readiness; optional model test requires provider settings to be configured on the deployed server.

## 2.5.0 — Release candidate and deployment clarity
- Aligned visible/backend version strings.
- Added a practical Hindi deployment checklist for GitHub, Render, provider configuration and live smoke tests.
- Made the release status explicit about external checks still required; no claim of completed public launch.

## 2.7.0
- Disabled feedback writes by default until an operator explicitly enables them after configuring durable storage.
- Split database reachability from feedback-write enablement in diagnostics.
- Added tests for disabled-by-default behavior.


## 2.7.0
- Added optional managed PostgreSQL support via server-side `DATABASE_URL`; SQLite remains the local fallback.
- Database status now reports the selected engine and only describes persistence as enabled when PostgreSQL is reachable.
- Feedback storage remains disabled by default and requires explicit consent plus operator opt-in.
- Added the psycopg v3 driver for PostgreSQL deployments.


## 2.8.0
- Added GitHub Actions CI for compile checks and the automated test suite.
- Added a security policy with explicit MVP limitations.
- Removed the generated SQLite database from the release archive; database files remain ignored by Git.
- Updated smoke-test user agent and release version metadata.
- Clarified that public demo launch can omit accounts/payments, while a production launch still needs additional controls and verification.
