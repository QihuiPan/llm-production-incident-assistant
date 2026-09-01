# Evaluation Rubric

The committed benchmark contains 100 labelled synthetic incidents across database pool exhaustion, downstream dependency failure, and queue-consumer backlog scenarios. Eighty cases form the development split and twenty cases form a fixed held-out split.

| Metric | Definition | Regression gate |
| --- | --- | ---: |
| Root-cause accuracy | Top hypothesis contains a labelled root-cause term | >= 80% |
| Evidence recall@10 | At least one gold source is present in the first ten hits | >= 90% |
| Citation precision | Every emitted citation resolves to returned evidence | >= 95% |
| Unsupported claim rate | Hypotheses without supporting evidence | < 5% |
| Tool selection accuracy | Expected read-only tools are proposed | >= 85% |
| End-to-end latency | p95 local deterministic run latency | < 12 seconds |

The synthetic benchmark is a regression instrument, not evidence of production performance. Production adoption requires representative historical incidents, human review, and separately reported confidence intervals.

The A/B command runs the same cases with vector-only retrieval and the advanced decomposed, reranked, compressed candidate. The candidate must pass every absolute gate and may not regress root-cause accuracy or evidence recall@10. Reports include split metrics and failure counts for retrieval, reasoning, citation, unsupported claims, and tool selection.
