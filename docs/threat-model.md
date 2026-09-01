# Threat Model

## Assets

- Production credentials, logs, service metadata, and personal data.
- Operator identity and tool-approval records.
- Incident evidence integrity and source provenance.
- Evaluation datasets, prompts, and configuration versions.

## Trust boundaries

Uploaded documents, retrieved chunks, alerts, and tool output are untrusted data. Browser requests cross an authentication boundary that a production deployment must enforce at the reverse proxy or API gateway. Tool adapters and the database are server-side components; the model and browser cannot call them directly.

## Primary threats and controls

| Threat | Control | Verification |
| --- | --- | --- |
| Prompt injection in a runbook | Pattern scan, trust label, ranking penalty, system/data separation | `tests/test_security.py` |
| Invented or stale citation | Stable evidence IDs and pre-save citation validation | `tests/test_orchestrator.py` |
| Secret exfiltration through logs | Recursive redaction before tool output becomes evidence | `tests/test_security.py` |
| Unauthorized production mutation | No mutation adapter; exact allowlist; read-only containers | `tests/test_tools.py` |
| Tool argument smuggling | Strict schemas with unknown fields forbidden | `tests/test_tools.py` |
| Excessive query or cost | Time-window, row, call-count, token, and timeout budgets | Gateway and configuration tests |
| Cross-service data access | Tool service/environment must match the incident | `tests/test_tools.py` |
| Malicious file | Type allowlist, size limit, UTF-8 requirement, passive PDF extraction | API and ingestion tests |
| Dataset path traversal | Evaluation path constrained to `evals/datasets` | `tests/test_api.py` |

## Non-goals

This repository does not provide identity federation, production network access, autonomous remediation, or a compliance certification. Simulator data is non-sensitive. Real adapters require organization-specific authorization and data-retention reviews.

## Safe extension checklist

1. Add a typed read-only schema and bounded adapter.
2. Document data classification and authorization scope.
3. Add allowlist, budget, redaction, audit, and adversarial tests.
4. Update this threat model and `CHANGELOG.md`.
5. Run the offline regression suite before deployment.
