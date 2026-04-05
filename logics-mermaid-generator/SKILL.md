---
name: logics-mermaid-generator
description: Generate Logics workflow Mermaid blocks with a deterministic fallback that stays compatible with the flow manager.
---

# Generate Logics Mermaid

This skill is for repositories importing the kit under `logics/skills/`.

It renders bounded Mermaid blocks for Logics `request`, `backlog`, and `task` docs.
The deterministic renderer is the compatibility baseline used by the flow manager.

## Run

```bash
python logics/skills/logics-mermaid-generator/scripts/generate_mermaid.py \
  --kind request \
  --title "Demo request" \
  --values-json '{"NEEDS_PLACEHOLDER":"- Demo need","CONTEXT_PLACEHOLDER":"- Demo context","ACCEPTANCE_PLACEHOLDER":"- AC1: Demo"}'
```
