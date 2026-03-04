---
name: logics-migration-compat-guardian
description: Enforce migration and backward-compatibility guardrails in Logics docs. Use when Codex should ensure backlog/tasks/specs explicitly cover schema/data evolution, import-export compatibility, and rollback strategy.
---

# Migration & Compatibility Guardian

## Add compatibility guardrails sections

```bash
python3 logics/skills/logics-migration-compat-guardian/scripts/add_migration_guardrails.py logics/backlog/item_001_example.md
python3 logics/skills/logics-migration-compat-guardian/scripts/add_migration_guardrails.py logics/tasks/task_010_example.md logics/specs/spec_005_example.md
```

## Do

- Ensure docs explicitly state migration expectations.
- Add a compatibility checklist when missing.
- Require import/export impact and rollback notes for persisted data.

## Output

- Updated Markdown docs with a reusable `# Migration & compatibility` section.
