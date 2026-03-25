---
name: logics-hybrid-delivery-assistant
description: >-
  Use when an operator asks for repetitive delivery help such as `commit all
  changes`, `summarize this PR`, `summarize validation`, `what should we do
  next?`, `triage this request`, or `prepare a handoff`. Prefer the shared
  hybrid assist runtime so Ollama can be used opportunistically when healthy
  and the flow can degrade cleanly otherwise.
---

# Hybrid assist

Use the shared runtime instead of inventing one-off prompts or shell logic.

Cross-platform launcher:

- canonical: `python logics/skills/logics.py flow assist ...`
- substitute `python3` on Unix when needed
- substitute `py -3` on Windows when that is the installed launcher

## Use when

- The user says `commit all changes` or asks for a commit message plan.
- The user wants a PR summary, changelog summary, or validation summary.
- The user asks what the next workflow step should be.
- The user wants to triage a request or backlog item.
- The user wants a compact handoff packet or a bounded split suggestion.

## Rules

- Prefer the runtime aliases first:
  - `python logics/skills/logics.py flow assist commit-all`
  - `python logics/skills/logics.py flow assist summarize-pr`
  - `python logics/skills/logics.py flow assist summarize-validation`
  - `python logics/skills/logics.py flow assist next-step <ref>`
  - `python logics/skills/logics.py flow assist triage <ref>`
  - `python logics/skills/logics.py flow assist handoff <ref>`
- Keep risky execution bounded:
  - default to `suggestion-only`
  - use `--execution-mode execute` only when the operator intent is explicit
- Keep the runtime shared:
  - do not reimplement hybrid logic in agent-specific prompts
  - keep Codex and Claude paths thin over the same command surface
- Preserve Windows-safe examples:
  - document `python ...` as the canonical launcher
  - avoid POSIX-only command examples unless they are labeled as such

## Checks

- Inspect runtime health with:
  - `python logics/skills/logics.py flow assist runtime-status --format json`
- Build a shared context bundle with:
  - `python logics/skills/logics.py flow assist context next-step req_001_example --format json`
- Use the generic runner when no alias exists:
  - `python logics/skills/logics.py flow assist run doc-consistency --format json`
