---
name: logics-connector-jira
description: Connect Jira (Atlassian) to the Logics workflow: search issues via JQL and import a Jira issue into `logics/backlog/` as a new `item_###_*.md`.
---

# Jira connector

## Environment variables
- `JIRA_BASE_URL` (e.g. `https://<domain>.atlassian.net`)
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Optional:
- `JIRA_DEFAULT_JQL` (default JQL used by the search script if `--jql` is omitted)

## Search issues (JQL)
```bash
python3 logics/skills/logics-connector-jira/scripts/jira_search_issues.py \
  --jql "project = CIR ORDER BY created DESC" --limit 20
```

## Import an issue into Logics backlog
```bash
python3 logics/skills/logics-connector-jira/scripts/jira_to_backlog.py \
  --issue "CIR-123"
```

Notes:
- Uses Jira REST API v3. Descriptions are imported as rendered HTML (when available) and truncated.
