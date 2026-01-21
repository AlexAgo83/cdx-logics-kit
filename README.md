# cdx-logics-kit

A reusable “Logics skills” kit (guides + scripts) to import into your projects under `logics/skills/`.

Goal: standardize a lightweight Markdown-based workflow (`logics/request` → `logics/backlog` → `logics/tasks` → `logics/specs`) and provide commands to create/promote/lint/index/review.

## Prerequisites

- `python3` (scripts have no external dependencies)
- `git`

## Install (recommended: submodule)

In a new project repo:

```bash
mkdir -p logics
git submodule add -b main git@github.com:AlexAgo83/cdx-logics-kit.git logics/skills
git submodule update --init --recursive
```

Then bootstrap the Logics tree (creates missing folders + `.gitkeep`, and a default `logics/instructions.md` if missing):

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py
```

## Usage (inside the project repo)

Create a request/backlog/task with auto-incremented IDs:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new request --title "My first need"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog --title "My first need"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new task --title "Implement my first need"
```

Promote between stages:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/req_001_my_first_need.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/item_002_my_first_need.md
```

Check Logics conventions:

```bash
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py
```

## Connectors

### Linear connector (issues → Logics backlog)

Prereqs: `LINEAR_API_KEY` (and optionally `LINEAR_API_URL`, `LINEAR_API_TEAM_ID`). For Linear API keys, use `Authorization: $LINEAR_API_KEY` (no `Bearer` prefix).

List issues:

```bash
python3 logics/skills/logics-connector-linear/scripts/linear_list_issues.py --team-id "$LINEAR_API_TEAM_ID"
```

Import an issue as a backlog item:

```bash
python3 logics/skills/logics-connector-linear/scripts/linear_to_backlog.py --issue "CIR-42"
```

### Figma connector (nodes → export / Logics backlog)

Prereqs: `FIGMA_TOKEN_PAT` (header `X-Figma-Token`) and a `FIGMA_FILE_KEY`.

List pages:

```bash
python3 logics/skills/logics-connector-figma/scripts/figma_list_pages.py --file-key "$FIGMA_FILE_KEY"
```

Export a node as PNG:

```bash
python3 logics/skills/logics-connector-figma/scripts/figma_export_node.py \
  --file-key "$FIGMA_FILE_KEY" --node-id "1744:4185" --format png --scale 2 \
  --out "output/figma/weekly.png"
```

Import a node reference as a backlog item:

```bash
python3 logics/skills/logics-connector-figma/scripts/figma_to_backlog.py \
  --file-key "$FIGMA_FILE_KEY" --node-id "1744:4185" --export
```

### Confluence connector (pages → Logics requests)

Prereqs: `CONFLUENCE_DOMAINE`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`.

Search pages (CQL):

```bash
python3 logics/skills/logics-connector-confluence/scripts/confluence_search_pages.py \
  --cql "space=dt AND text~\\\"flotauto\\\"" --limit 10
```

Import a page as a request (stores Confluence HTML as context):

```bash
python3 logics/skills/logics-connector-confluence/scripts/confluence_to_request.py --page-id 234913873
```

### Jira connector (issues → Logics backlog)

Prereqs: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.

Search issues (JQL):

```bash
python3 logics/skills/logics-connector-jira/scripts/jira_search_issues.py \
  --jql "project = CIR ORDER BY created DESC" --limit 20
```

Import an issue as a backlog item:

```bash
python3 logics/skills/logics-connector-jira/scripts/jira_to_backlog.py --issue "CIR-123"
```

## Update the kit (inside an existing project)

Update the submodule to the latest `main`:

```bash
git submodule update --remote --merge
git add logics/skills
git commit -m "Update Logics kit"
```

Pin to a tag (recommended if you want controlled upgrades):

```bash
cd logics/skills
git fetch --tags
git checkout v0.1.1
cd -
git add logics/skills
git commit -m "Pin Logics kit to v0.1.1"
```

## Notes

- This repo is meant to be executed from the **project repo** (where `logics/skills` points to this kit).
- `req_*`, `item_*`, `task_*`, `spec_*` docs stay in the project repo, so there’s no cross-project “pollution”.
