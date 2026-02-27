---
name: logics-doc-linter
description: Lint and validate the Logics Markdown conventions. Use when Codex should verify filenames, top headings, and required indicators across `logics/request`, `logics/backlog`, and `logics/tasks`, and report inconsistencies.
---

# Lint Logics docs

## Run

```bash
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py --require-status
```

## What it checks

- Filename patterns (`req_###_*.md`, `item_###_*.md`, `task_###_*.md`).
- First heading format: `## <doc_ref> - <Title>`.
- Required indicators:
  - requests: `From version`, `Understanding`, `Confidence`, `Complexity`, `Theme`
  - backlog/tasks: plus `Progress`
- `Status` value validation when present (`Draft|Ready|In progress|Blocked|Done|Archived`).
- Optional strict mode (`--require-status`) to enforce `Status` on every request/backlog/task doc.
