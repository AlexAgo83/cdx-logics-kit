---
name: logics-connector-confluence
description: Connect Confluence (Atlassian) to the Logics workflow: search pages via CQL and import a page into `logics/request/` as a new `req_###_*.md` with the page content as context.
---

# Confluence connector

## Environment variables
- `CONFLUENCE_DOMAINE` (e.g. `https://<domain>.atlassian.net/wiki`)
- `CONFLUENCE_EMAIL`
- `CONFLUENCE_API_TOKEN`

## Search pages (CQL)
```bash
python3 logics/skills/logics-connector-confluence/scripts/confluence_search_pages.py \
  --cql "space=dt AND text~\\\"flotauto\\\"" --limit 10
```

## Import a page into Logics requests
```bash
python3 logics/skills/logics-connector-confluence/scripts/confluence_to_request.py \
  --page-id 234913873
```

Notes:
- The imported content is stored in the request `# Context` as an HTML block (storage format, truncated).
