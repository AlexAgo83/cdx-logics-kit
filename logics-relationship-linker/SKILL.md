---
name: logics-relationship-linker
description: Build and maintain relationships across Logics documents. Use when Codex should discover or summarize links between `logics/request`, `logics/backlog`, `logics/tasks`, and `logics/specs` by scanning references and generating a relationship report.
---

# Relationships

## Generate a relationship report

```bash
python3 logics/skills/logics-relationship-linker/scripts/link_relations.py --out logics/RELATIONSHIPS.md
```

## Conventions

- Prefer referencing docs using their doc ref (e.g. `req_001_some_slug`, `item_002_some_slug`, `task_003_some_slug`, `spec_004_some_slug`).
- Keep relationships lightweight (don’t try to model everything).

