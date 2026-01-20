---
name: logics-estimation-helper
description: Estimate effort and complexity for Logics backlog items and tasks. Use when Codex should propose a rough estimate (S/M/L or points), identify unknowns/risks, and recommend splitting work.
---

# Estimation

## Output format

- Estimate: `S` / `M` / `L` (or points if you use them)
- Drivers: 3–6 bullets (unknowns, integration points, migration risk)
- Split suggestion: when the work should be multiple tasks

## Heuristics

- `S`: isolated change, low risk, clear acceptance criteria.
- `M`: cross-cutting change, moderate unknowns, needs tests/UX iteration.
- `L`: architectural change, migrations, multiple systems, high uncertainty.

