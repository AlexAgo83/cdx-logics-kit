---
name: logics-spec-writer
description: Create lightweight functional specs inside this repo. Use when Codex should write a structured spec document in `logics/specs/*.md` derived from a backlog item or task, with clear scope, acceptance criteria, and validation/test plan.
---

# Backlog/Task → Spec

## Create a spec doc

```bash
python3 logics/skills/logics-spec-writer/scripts/logics_spec.py new --title "..." --from-version X.X.X
```

## Fill it from inputs

- Start from the backlog acceptance criteria and convert them into spec sections.
- Keep it concise; put implementation details in tasks, not in specs.

