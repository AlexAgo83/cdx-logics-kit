---
name: logics-connector-linear
description: Connect Linear (GraphQL) to the Logics workflow: list issues and import a Linear issue into `logics/backlog/` as a new `item_###_*.md` with a link back to Linear.
---

# Linear connector

## Environment variables
- `LINEAR_API_KEY` (Linear Personal API key). Header is `Authorization: $LINEAR_API_KEY` (no `Bearer` prefix).
- `LINEAR_API_URL` (optional, default `https://api.linear.app/graphql`)
- `LINEAR_API_TEAM_ID` (optional default teamId; can be overridden via CLI)

## List issues for a team
```bash
python3 logics/skills/logics-connector-linear/scripts/linear_list_issues.py \
  --team-id "$LINEAR_API_TEAM_ID" --limit 50
```

## Import a Linear issue into Logics backlog
```bash
python3 logics/skills/logics-connector-linear/scripts/linear_to_backlog.py \
  --issue "CIR-42"
```

Notes:
- `--issue` accepts an identifier (`CIR-42`) or a Linear issue URL.
- The created backlog item follows the kit template + linter conventions.
