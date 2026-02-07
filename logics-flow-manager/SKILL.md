---
name: logics-flow-manager
description: Manage this repository's Logics workflow (logics/request → logics/backlog → logics/tasks): create new request/backlog/task docs, promote between stages, keep From version/Understanding/Confidence/Progress indicators consistent, and generate correctly-numbered filenames. Use when a user asks to triage an idea, write a request, promote it to a backlog item, or create an executable task plan.
---

# Logics flow

## Conventions

- Keep docs in `logics/request/`, `logics/backlog/`, `logics/tasks/`.
- Use numeric IDs and slugs in filenames: `req_001_my_title.md`, `item_002_some_scope.md`, `task_003_do_the_work.md`.
- Keep indicators at the top:
  - `From version: X.X.X`
  - `Understanding: ??%`
  - `Confidence: ??%`
  - `Progress: ??%` (mainly tasks; optionally backlog)
  - `Complexity: Low | Medium | High`
  - `Theme: Combat | Items | Economy | UI | ...`

If unsure, open `logics/instructions.md` and follow the workflow described there.

## Create a new doc (recommended)

Use the generator script (picks the next available ID, creates a file from templates):

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new request --title "Offline recap UI"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog --title "Offline recap UI"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new task --title "Implement offline recap UI"
```

After creation, run **logics-confidence-booster** to raise Understanding/Confidence above 90%:

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/request/req_001_example.md
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/backlog/item_002_example.md
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/tasks/task_003_example.md
```

Optional flags:

- `--from-version 0.14.3`
- `--understanding 60% --confidence 40%`
- `--progress 0%` (task/backlog)
- `--dry-run` (show path + content preview, no writes)

## Promote between stages

Create the next-stage doc and link back to the source:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/req_001_offline_recap_ui.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/item_002_offline_recap_ui.md
```

After promotion:

- Ensure the backlog item has clear acceptance criteria + priority.
- Ensure the task has a step-by-step plan and at least 1–2 validation commands relevant to the work.
- Ensure the source request lists any generated backlog items in its Backlog section.

Before promotion:

- If `Understanding` or `Confidence` is below 90% in the source doc, run the **logics-confidence-booster** skill first to clarify and update indicators.
