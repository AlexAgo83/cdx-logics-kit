---
name: logics-metrics-owner
description: Add ownership and success metrics to Logics backlog/spec docs. Use when Codex should define an owner, success metric/KPI, and instrumentation notes for a backlog item or spec to make outcomes measurable.
---

# Ownership & metrics

## Add a section automatically

```bash
python3 logics/skills/logics-metrics-owner/scripts/add_owner_metrics.py logics/backlog/item_001_foo.md --owner \"@name\"
python3 logics/skills/logics-metrics-owner/scripts/add_owner_metrics.py logics/specs/spec_003_baz.md
```

## Add to backlog/spec

- Owner: who is accountable for shipping and follow-up
- KPI / success signal: how you know it worked
- Instrumentation: events/logging needed to measure it
