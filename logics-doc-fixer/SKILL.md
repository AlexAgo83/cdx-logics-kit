---
name: logics-doc-fixer
description: Validate and repair Logics request/backlog/task/product/architecture docs (structure, indicators, and cross‑references) without deleting existing metadata. Use when Codex should audit `logics/request`, `logics/backlog`, `logics/tasks`, `logics/product`, or `logics/architecture` for missing sections/indicators, auto-update Progress from checkboxes, backfill linked refs when safe, or restore dropped indicator lines.
---

# Logics Doc Fixer

## Quick start

Run a dry scan first, then apply fixes:

```bash
python logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py
python logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py --write
```

To target specific docs:

```bash
python logics/skills/logics-doc-fixer/scripts/fix_logics_docs.py logics/request/req_001_example.md --write
```

## What it fixes

- Ensures minimum **indicators** exist:
  - Requests: `From version`, `Understanding`, `Confidence`
  - Backlog/tasks: plus `Progress`
  - Product briefs: `Date`, `Status`, related refs, `Reminder`
  - Architecture docs: `Date`, `Status`, `Drivers`, related refs, `Reminder`
- Preserves all existing indicator lines (for example `Status`, `Complexity`, `Theme`, `Reminder`) and never removes them.
- Auto‑updates **Progress** from checkbox completion in `# Plan` (or `# Acceptance criteria` for backlog if checkboxes exist).
- Ensures required **sections** exist and adds placeholders when missing.
- Repairs **references** when possible:
  - Backlog item notes include `Derived from` the matching request (slug match).
  - Request `# Backlog` section lists derived backlog items (slug match).
  - Task `# Context` includes `Derived from` the matching backlog item (slug match).
  - Product briefs and architecture docs backfill matching `Related ...` refs when there is a unique slug match.

## Options

- `--write`: apply changes (default is dry-run)
- `--no-progress`: do not auto-update `Progress`
- `--repo-root`: override repo root detection

## Notes

- Matching is **slug-based** (e.g., `req_005_my_feature` ↔ `item_012_my_feature`).
- If multiple matches exist, references are **not** auto-added to avoid bad links.
- Safety rule: do not perform destructive rewrites of indicator blocks. If indicators appear missing after a previous run, restore from git history (`HEAD`) before any new edits.
