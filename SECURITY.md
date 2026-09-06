# Security Policy

Report vulnerabilities privately through GitHub Security Advisories. Do not include secrets, production log excerpts, or personal data in a public issue.

The assistant is deliberately read-only. Tool additions must be allowlisted, schema-validated, authorized server-side, covered by adversarial tests, and documented in `docs/threat-model.md`.

The hosted public demo accepts only synthetic incident scenarios through a separately rate-limited endpoint. Do not submit real logs, credentials, customer data, or personal information. Administrative and operational routes require an API key.
