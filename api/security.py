"""Security controls for untrusted documents and tool output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions?",
        r"reveal\s+(the\s+)?(system\s+prompt|secrets?|credentials?)",
        r"(?:execute|run|call)\s+(?:the\s+)?(?:tool|command|restart|deploy)",
        r"you\s+are\s+now\s+(?:an?|the)",
        r"bypass\s+(?:the\s+)?(?:policy|authorization|approval)",
    )
]

SECRET_PATTERNS = [
    (re.compile(r"\b(?:sk|pk)[-_][A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "[REDACTED_ACCESS_KEY]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (
        re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]+@", re.IGNORECASE),
        "postgresql://[REDACTED]@",
    ),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|passwd|secret)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
]


@dataclass(frozen=True)
class SecurityScan:
    """A security scan result that never contains hidden instructions."""

    flagged: bool
    matches: tuple[str, ...]


def scan_prompt_injection(text: str) -> SecurityScan:
    """Detect common instruction-override patterns in untrusted content."""

    matches = tuple(pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text))
    return SecurityScan(flagged=bool(matches), matches=matches)


def redact_text(value: str) -> tuple[str, int]:
    """Replace common secrets and personal identifiers before model exposure."""

    redacted = value
    count = 0
    for pattern, replacement in SECRET_PATTERNS:
        redacted, replacements = pattern.subn(replacement, redacted)
        count += replacements
    return redacted, count


def redact_value(value: Any) -> tuple[Any, int]:
    """Recursively redact strings inside JSON-compatible tool results."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        result: list[Any] = []
        count = 0
        for item in value:
            clean, item_count = redact_value(item)
            result.append(clean)
            count += item_count
        return result, count
    if isinstance(value, dict):
        result_dict: dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            clean, item_count = redact_value(item)
            result_dict[str(key)] = clean
            count += item_count
        return result_dict, count
    return value, 0
