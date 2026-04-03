---
name: logics-architecture-decision-writer
description: Write architecture decision records (ADR) in `logics/architecture`. Use when Codex identifies a non-trivial decision (trade-offs, alternatives) and should create a concise ADR document with context and consequences.
---

# ADR

## Create a new ADR

```bash
python logics/skills/logics-architecture-decision-writer/scripts/new_adr.py --title "Choose cache strategy" --out-dir logics/architecture
```

## DAT-style structure

- Use the generated `# Overview` section to state the direction in 3 to 5 short lines.
- Keep the Mermaid in `# Overview` macro-level only: current state -> chosen direction -> impacted areas.
- Follow the same Mermaid safety rules used by `logics-flow-manager`: ASCII labels only, short labels, no Markdown formatting in nodes.

## Update discipline

- When you edit an existing ADR, update `Status` and every impacted linked ref (`request`, `backlog`, `task`).
- Keep `# Decision`, `# Consequences`, `# Migration and rollout`, and `# Follow-up work` synchronized with the current architecture direction.
- Replace stale placeholders and refresh the `# Overview` Mermaid whenever the structural direction changes.
