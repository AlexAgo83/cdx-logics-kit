---
name: logics-doc-fixer
description: Validate and repair Logics request/backlog/task docs (structure, required indicators, and cross‑references). Use when Codex should audit `logics/request`, `logics/backlog`, or `logics/tasks` for missing sections/indicators, auto-update Progress from checkboxes, and backfill missing request↔backlog↔task references.
---

# Logics Doc Fixer

## Quick start

Run a dry scan first, then apply fixes:

```bash
python3 logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py
python3 logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py --write
```

To target specific docs:

```bash
python3 logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py logics/request/req_001_example.md --write
```

## What it fixes

- Ensures required **indicators** exist:
  - Requests: `From version`, `Understanding`, `Confidence`, `Complexity`, `Theme`
  - Backlog/tasks: plus `Progress`
- Auto‑updates **Progress** from checkbox completion in `# Plan` (or `# Acceptance criteria` for backlog if checkboxes exist).
- Ensures required **sections** exist and adds placeholders when missing.
- Repairs **references** when possible:
  - Backlog item notes include `Derived from` the matching request (slug match).
  - Request `# Backlog` section lists derived backlog items (slug match).
  - Task `# Context` includes `Derived from` the matching backlog item (slug match).

## Options

- `--write`: apply changes (default is dry-run)
- `--no-progress`: do not auto-update `Progress`
- `--repo-root`: override repo root detection

## Notes

- Matching is **slug-based** (e.g., `req_005_my_feature` ↔ `item_012_my_feature`).
- If multiple matches exist, references are **not** auto-added to avoid bad links.
