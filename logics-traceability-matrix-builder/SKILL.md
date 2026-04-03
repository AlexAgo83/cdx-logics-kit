---
name: logics-traceability-matrix-builder
description: Build and refresh acceptance-criteria traceability matrices for Logics backlog/task/spec docs. Use when Codex should map each acceptance criterion to test types, likely test files, and concrete validation commands.
---

# Traceability Matrix Builder

## Generate or refresh a matrix

```bash
python logics/skills/logics-traceability-matrix-builder/scripts/build_traceability_matrix.py logics/tasks/task_001_example.md
python logics/skills/logics-traceability-matrix-builder/scripts/build_traceability_matrix.py logics/backlog/item_010_example.md --update-doc
python logics/skills/logics-traceability-matrix-builder/scripts/build_traceability_matrix.py logics/specs/spec_003_example.md --out logics/external/traceability/spec_003_matrix.md
```

## Do

- Extract acceptance criteria from the source doc.
- Build a matrix row per criterion (`AC-01`, `AC-02`, ...).
- Classify each row as Unit, Integration, or E2E.
- Suggest likely matching test files from `tests/` and `src/**/__tests__/` style paths.
- Attach validation commands derived from `package.json` scripts.

## Output

- A Markdown matrix ready for task/spec review.
- Optionally upsert a `## Traceability matrix` section in the source doc.
