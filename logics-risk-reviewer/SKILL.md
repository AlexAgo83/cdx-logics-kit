---
name: logics-risk-reviewer
description: Add a risk/rollback review to Logics docs. Use when Codex should identify risks, mitigations, rollbacks, and operational considerations for a backlog item or task, and update the Markdown accordingly.
---

# Risk review

## Add sections automatically

```bash
python3 logics/skills/logics-risk-reviewer/scripts/add_risk_sections.py logics/backlog/item_001_foo.md
python3 logics/skills/logics-risk-reviewer/scripts/add_risk_sections.py logics/tasks/task_002_bar.md
```

## For backlog items

- Add a short `Risks` subsection under `# Notes`:
  - Risk
  - Mitigation
  - Dependencies

## For tasks

- Add a `# Risks & rollback` section when the change is risky:
  - What can break
  - How to detect regressions
  - How to rollback safely
