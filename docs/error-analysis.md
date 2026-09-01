# Baseline Error Analysis

## Known limitations

1. The local embedding uses feature hashing, so semantic recall is weaker than a trained embedding model. Keyword retrieval and reciprocal rank fusion keep error signatures useful.
2. The deterministic answer composer recognizes a small set of incident patterns. It exists to exercise grounding and safety without requiring a secret.
3. Synthetic tool adapters approximate logs and metrics and are not calibrated to a real telemetry distribution.
4. The committed benchmark shares document vocabulary with the demo corpus and must not be presented as production accuracy.

## Failure attribution workflow

When a case fails, classify it before changing prompts or thresholds:

- Retrieval: gold evidence is absent from top ten results.
- Reasoning: evidence is present but the top cause does not match the labelled cause.
- Tool selection: an expected read-only query is missing or improperly scoped.
- Citation: an evidence ID is absent, invalid, or does not support the adjacent statement.
- Safety: injection text changes behavior, a secret remains, or an unauthorized tool is proposed.

Save the case ID, configuration version, ranked sources, output, metric deltas, and proposed remediation. Add a changelog entry for every behavior-changing correction.
