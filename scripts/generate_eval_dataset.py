"""Generate the deterministic 50-case benchmark committed with the project."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCENARIOS = [
    {
        "service": "checkout-api",
        "alerts": [
            "HTTP 503 spike with connection pool exhausted errors",
            "Checkout latency increased after pool_acquire_timeout warnings",
            "Database sessions saturated and new requests are failing",
            "Error rate increased after transaction retry deployment",
            "Connection pool wait time exceeded the alert threshold",
        ],
        "terms": ["connection pool"],
        "sources": ["checkout-api-runbook.md", "checkout-db-pool-postmortem.md"],
    },
    {
        "service": "payments-api",
        "alerts": [
            "HTTP 503 returned by downstream payments-db",
            "Payment request errors increased with downstream timeouts",
            "Payments dependency is unavailable in production",
            "Elevated payment errors correlate with database failures",
            "Downstream response failures exceeded the error budget",
        ],
        "terms": ["downstream dependency"],
        "sources": ["payments-api-runbook.md"],
    },
    {
        "service": "inventory-api",
        "alerts": [
            "Inventory queue depth is rising and consumers are slow",
            "Queue backlog exceeded the production threshold",
            "Inventory consumer errors are blocking queue processing",
            "Queue depth increased while request rate stayed stable",
            "Slow consumers caused an inventory backlog",
        ],
        "terms": ["queue consumer"],
        "sources": ["inventory-api-runbook.md"],
    },
]


def build_cases() -> list[dict[str, object]]:
    start = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
    cases: list[dict[str, object]] = []
    for index in range(50):
        scenario = SCENARIOS[index % len(SCENARIOS)]
        case_start = start + timedelta(days=index, minutes=index)
        cases.append(
            {
                "case_id": f"SYN-{index + 1:03d}",
                "service": scenario["service"],
                "environment": "production",
                "alert": scenario["alerts"][index % len(scenario["alerts"])],
                "window_start": case_start.isoformat(),
                "window_end": (case_start + timedelta(hours=1)).isoformat(),
                "gold_root_cause_terms": scenario["terms"],
                "gold_evidence_sources": scenario["sources"],
                "expected_tools": ["get_recent_deployments", "search_logs", "get_metrics"],
                "allowed_next_steps": ["read logs", "read metrics", "read deployments"],
            }
        )
    return cases


def main() -> None:
    destination = (
        Path(__file__).resolve().parents[1] / "evals" / "datasets" / "synthetic_incidents.jsonl"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(case, separators=(",", ":")) for case in build_cases()) + "\n"
    destination.write_text(content, encoding="utf-8")
    print(f"Wrote {len(build_cases())} cases to {destination}")


if __name__ == "__main__":
    main()
