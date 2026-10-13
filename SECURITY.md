# Security policy

This is an early MVP, not a security-audited production service. Do not use it to process sensitive, health, financial, or government-identification data.

- Never commit `.env`, API keys, access tokens, local databases, or user data.
- Configure `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` only in the host's secret/environment settings.
- Keep feedback storage disabled unless durable storage, access controls, retention, and a privacy notice have been reviewed.
- Accounts, sessions, payment processing, shared rate limiting, backups, and a full security review are not implemented.
- Report a security concern privately to the project owner; do not publish secrets or exploit details.
