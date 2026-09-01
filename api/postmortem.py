"""Grounded Markdown postmortem drafting."""

from __future__ import annotations

from api.models import Incident, InvestigationOutput


def render_postmortem(incident: Incident, investigation: InvestigationOutput) -> str:
    """Render a draft that keeps every assessment linked to evidence identifiers."""

    hypothesis = investigation.hypotheses[0] if investigation.hypotheses else None
    cause = hypothesis.cause if hypothesis else "Insufficient evidence to identify a root cause."
    citations = ", ".join(hypothesis.supporting_evidence) if hypothesis else "None"
    timeline = (
        "\n".join(
            f"- {event.at}: {event.event} [{', '.join(event.evidence_ids)}]"
            for event in investigation.timeline
        )
        or "- Timeline requires approved telemetry evidence."
    )
    evidence = (
        "\n".join(
            f"- {item.id}: {item.source} v{item.source_version} ({item.trust_level.value})"
            for item in investigation.evidence
        )
        or "- No evidence was retrieved."
    )
    return f"""# Postmortem Draft: {incident.id}

> Draft status: operator review required. This assistant did not perform remediation.

## Incident

- Service: {incident.service}
- Environment: {incident.environment}
- Window: {incident.window_start.isoformat()} to {incident.window_end.isoformat()}
- Alert: {incident.alert}

## Summary

{investigation.summary}

## Timeline

{timeline}

## Preliminary root cause

{cause}

Supporting evidence: {citations}

## Evidence register

{evidence}

## Follow-up actions

- Validate the hypothesis against approved log, metric, and deployment queries.
- Record the confirmed root cause and remediation owner.
- Add a regression case before closing the incident.
"""
