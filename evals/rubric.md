# Evaluation Rubric

The committed benchmark contains 50 labelled synthetic incidents across database pool exhaustion, downstream dependency failure, and queue-consumer backlog scenarios.

| Metric | Definition | Regression gate |
| --- | --- | ---: |
| Root-cause accuracy | Top hypothesis contains a labelled root-cause term | >= 80% |
| Evidence recall@10 | At least one gold source is present in the first ten hits | >= 90% |
| Citation precision | Every emitted citation resolves to returned evidence | >= 95% |
| Unsupported claim rate | Hypotheses without supporting evidence | < 5% |
| Tool selection accuracy | Expected read-only tools are proposed | >= 85% |
| End-to-end latency | p95 local deterministic run latency | < 12 seconds |

The synthetic benchmark is a regression instrument, not evidence of production performance. Production adoption requires representative historical incidents, human review, and separately reported confidence intervals.
