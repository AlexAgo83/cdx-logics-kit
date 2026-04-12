---
name: logics-progress-updater
description: Update Logics indicators consistently. Use when Codex should update request/backlog/task indicators (`From version`, `Understanding`, `Confidence`, `Progress`, `Complexity`, `Theme`) or companion doc indicators in `logics/product|architecture/*.md` such as `Date`, `Status`, `Drivers`, related refs, and `Reminder`.
---

# Update indicators

## Use the script

```bash
python logics/skills/logics-progress-updater/scripts/update_indicators.py logics/tasks/task_000_example.md --progress 40% --understanding 70% --confidence 60%
python logics/skills/logics-progress-updater/scripts/update_indicators.py logics/product/prod_000_example.md --status Active --related-backlog '`item_000_example`'
python logics/skills/logics-progress-updater/scripts/update_indicators.py logics/architecture/adr_000_example.md --status Accepted --drivers "Security and cache strategy"
```

## Rules

- Update `Understanding` when requirements change or become clearer.
- Update `Confidence` when unknowns are resolved or risks appear.
- Update `Progress` as checkpoints are completed, not as time passes.
- Set `Complexity` when scope changes (Low/Medium/High).
- Set `Theme` when the epic/theme classification changes.
- If the edit is explicitly non-semantic, you can keep the indicators stable and add a `> Maintenance edit:` or `> Non-semantic edit:` note so the linter does not force a false bump.
- For `product` and `architecture` docs, update `Status`, linked refs, `Drivers`, and `Reminder` when the framing changes.
