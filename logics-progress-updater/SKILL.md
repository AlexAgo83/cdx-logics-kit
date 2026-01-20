---
name: logics-progress-updater
description: Update Logics indicators consistently. Use when Codex should update `From version`, `Understanding`, `Confidence`, and `Progress` in `logics/request|backlog|tasks/*.md`, or when it should bump progress during implementation.
---

# Update indicators

## Use the script

```bash
python3 logics/skills/logics-progress-updater/scripts/update_indicators.py logics/tasks/task_000_example.md --progress 40% --understanding 70% --confidence 60%
```

## Rules

- Update `Understanding` when requirements change or become clearer.
- Update `Confidence` when unknowns are resolved or risks appear.
- Update `Progress` as checkpoints are completed, not as time passes.

