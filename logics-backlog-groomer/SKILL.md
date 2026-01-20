---
name: logics-backlog-groomer
description: Groom and promote a Logics request into a backlog item. Use when a request is clear enough to define scope, acceptance criteria, and priority, and Codex should create `logics/backlog/*.md` aligned with the Logics format.
---

# Request → Backlog

## Do

- Read the source request and extract: problem, users impacted, constraints, and success signal.
- Define `# Scope` (In/Out) to reduce ambiguity.
- Write objective `# Acceptance criteria` (testable checks).
- Set `# Priority` (Impact/Urgency) and add dependencies/risks in `# Notes`.
- Create the backlog doc:
  - `python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/<req_file>.md`
  - Or `python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog --title "..."`

## Outcome

A backlog item is “ready” when an engineer could implement it without guessing the intended behavior.

