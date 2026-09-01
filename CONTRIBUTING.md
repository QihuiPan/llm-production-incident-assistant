# Contributing

## Language policy

All code comments, annotations, API descriptions, commit messages, and review notes must be written in English.

## Required changelog update

Every pull request that changes code, behavior, configuration, documentation, dependencies, or deployment assets must add a concise entry under `Unreleased` in `CHANGELOG.md`. CI runs `scripts/check_changelog.py` and rejects changes that omit the log entry.

## Local checks

```bash
python -m ruff check .
python -m pytest
python -m evals.runner --dataset evals/datasets/synthetic_incidents.jsonl --strict
python -m evals.runner --dataset evals/datasets/synthetic_incidents.jsonl --compare --strict
cd web && pnpm install --frozen-lockfile && pnpm test && pnpm build
cd web && pnpm exec playwright install chromium && pnpm e2e
```

Use Conventional Commits for commit subjects. Never add a write-capable production tool without a threat-model update and explicit human approval controls.
