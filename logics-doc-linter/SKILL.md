---
name: logics-doc-linter
description: Lint and validate the Logics Markdown conventions. Use when Codex should verify filenames, top headings, and required indicators across `logics/request`, `logics/backlog`, `logics/tasks`, `logics/product`, and `logics/architecture`, and report inconsistencies.
---

# Lint Logics docs

## Run

```bash
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py --require-status
```

## What it checks

- Filename patterns (`req_###_*.md`, `item_###_*.md`, `task_###_*.md`, `prod_###_*.md`, `adr_###_*.md`).
- First heading format: `## <doc_ref> - <Title>`.
- Required indicators:
  - requests: `From version`, `Understanding`, `Confidence`
  - backlog/tasks: plus `Progress`
  - product briefs: `Date`, `Status`, related refs, `Reminder`
  - architecture docs: `Date`, `Status`, `Drivers`, related refs, `Reminder`
- `Status` value validation when present using the allowed values for each doc family.
- Optional strict mode (`--require-status`) to enforce `Status` on every supported doc type.
