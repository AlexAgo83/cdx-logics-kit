---
name: logics-global-reviewer
description: Run a global review of the repository's Logics workflow and documents, then propose concrete optimizations/improvements (hygiene, placeholders, stale indicators, missing links, progress distribution) as a Markdown report. Use when Codex needs to audit `logics/request`, `logics/backlog`, `logics/tasks`, and `logics/specs` and suggest next actions.
---

# Global Logics review

## Run

Print the report to stdout:

```bash
python3 logics/skills/logics-global-reviewer/scripts/logics_global_review.py
```

Write the report to a file:

```bash
python3 logics/skills/logics-global-reviewer/scripts/logics_global_review.py --out logics/REVIEW.md
```

## How to use the output

- Turn high-impact recommendations into backlog items (`logics/backlog/`) and executable tasks (`logics/tasks/`).
- Prefer small, surgical fixes (remove template placeholders, add missing links, clarify acceptance criteria, add validation commands).
- If the review highlights structural gaps (missing index/relationships), generate them via existing scripts:
  - `python3 logics/skills/logics-indexer/scripts/generate_index.py --out logics/INDEX.md`
  - `python3 logics/skills/logics-relationship-linker/scripts/link_relations.py --out logics/RELATIONSHIPS.md`
  - `python3 logics/skills/logics-duplicate-detector/scripts/find_duplicates.py --min-score 0.55`

