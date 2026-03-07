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
  - `Status: Draft | Ready | In progress | Blocked | Done | Archived`
  - `Understanding: ??%`
  - `Confidence: ??%`
  - `Progress: ??%` (mainly tasks; optionally backlog)
  - `Complexity: Low | Medium | High`
  - `Theme: Combat | Items | Economy | UI | ...`
- When writing a request, the `# Context` section must include a Mermaid diagram that visualizes the need.
- Prefer a compact business-readable `flowchart TD` or `flowchart LR` showing inputs, decision points, outputs, and feedback loops.
- Backlog items should include a Mermaid diagram that makes the delivery slice explicit: request/source -> problem -> scope -> acceptance criteria -> task(s).
- Tasks should include a Mermaid diagram that shows the execution path: backlog/source -> implementation steps -> validation -> done/report.

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
- `--status Draft|Ready|In progress|Blocked|Done|Archived`
- `--complexity Low|Medium|High --theme UI`
- `--progress 0%` (task/backlog)
- `--dry-run` (show path + content preview, no writes)

## Promote between stages

Create the next-stage doc and link back to the source:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/req_001_offline_recap_ui.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/item_002_offline_recap_ui.md
```

Close docs with automatic transition propagation:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close task logics/tasks/task_003_example.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close backlog logics/backlog/item_002_example.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close request logics/request/req_001_example.md
```

When a task is actually finished, prefer the kit-native guarded flow instead of editing indicators manually:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py finish task logics/tasks/task_003_example.md
```

`finish task` closes the task, propagates closure to linked backlog/request docs when eligible, and verifies that the linked chain stayed synchronized. Use `close` only when you explicitly want the lower-level primitive.

Run workflow coherence audit:

```bash
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --stale-days 30
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --group-by-doc
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --format json
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --autofix-ac-traceability
```

After promotion:

- Ensure the backlog item has clear acceptance criteria + priority.
- Ensure the task has a step-by-step plan and at least 1–2 validation commands relevant to the work.
- Ensure the source request lists any generated backlog items in its Backlog section.

Before promotion:

- If `Understanding` or `Confidence` is below 90% in the source doc, run the **logics-confidence-booster** skill first to clarify and update indicators.
- For request docs, replace the default Mermaid scaffold with a diagram specific to the need before considering the request ready.
- For backlog/task docs, replace the default Mermaid scaffold with a doc-specific diagram whenever the default no longer reflects the real flow.
