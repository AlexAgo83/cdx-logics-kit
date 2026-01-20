---
name: logics-triage-assistant
description: Triage raw ideas into the Logics flow. Use when a user drops an unstructured feature/bug idea and Codex should clarify scope, ask the right questions, and produce a well-formed `logics/request/*.md` using this repo’s conventions.
---

# Triage → Request

## Do

- Ask 3–7 clarifying questions (user, problem, constraints, success signal, urgency).
- Decide whether this is a request, a bug report, or an architecture note.
- Create a request doc using `logics-flow-manager`:
  - `python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new request --title "..."`.
- Fill `# Needs` with 1–5 bullet needs.
- Fill `# Context` with constraints, references, and any relevant links.
- Set `Understanding` and `Confidence` realistically; keep them updated as you learn.

## Avoid

- Writing tasks before the request is clear.
- Mixing multiple unrelated needs in a single request (split if needed).

