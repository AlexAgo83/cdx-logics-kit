---
name: logics-task-breakdown
description: Break down a Logics backlog item into executable tasks. Use when Codex should turn `logics/backlog/*.md` into one or more `logics/tasks/*.md` with step-by-step plans, validation commands, and progress tracking.
---

# Backlog → Tasks

## Do

- Start from the backlog item’s acceptance criteria; group work by deliverable.
- If the scope includes UI changes and no mockup exists yet, propose creating mockups (mobile + desktop) before writing tasks.
- Prefer 1–3 tasks per backlog item (split only if needed for parallelism or risk).
- For each task, include:
  - A minimal `# Plan` with checkboxes (implementation order).
  - A `# Validation` section using relevant commands (`npm run lint`, `npm run tests`, `npm run typecheck`, `npm run build`).
  - A short `# Report` updated as work progresses.
- Generate tasks:
  - `python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/<item_file>.md`
  - Or `python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new task --title "..."`

## Avoid

- Vague plans (“do the thing”) without concrete steps.
- Missing validation commands for the area being changed.
