# Logics Context

This repository uses the Logics workflow.

## Workflow

- `logics/request`: incoming requests and ideas.
- `logics/backlog`: scoped items with acceptance criteria and priority.
- `logics/tasks`: execution plans with validation and progress tracking.
- `logics/specs`: lightweight functional specs derived from requests or tasks.
- `logics/product`: product framing docs.
- `logics/architecture`: architecture decisions and supporting diagrams.
- `logics/external`: generated artifacts that do not fit the managed doc folders.

## Commands

- `python logics/skills/logics.py bootstrap`
- `python logics/skills/logics.py lint --require-status`
- `python logics/skills/logics.py flow ...`
