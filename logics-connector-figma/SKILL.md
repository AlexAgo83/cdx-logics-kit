---
name: logics-connector-figma
description: Connect Figma to the Logics workflow: list pages/nodes, export node images, and import a Figma node reference into `logics/backlog/` as a new `item_###_*.md`.
---

# Figma connector

## Environment variables
- `FIGMA_TOKEN_PAT` (Figma Personal Access Token). Use header `X-Figma-Token: $FIGMA_TOKEN_PAT`.
- `FIGMA_FILE_KEY` (default fileKey).

## List pages of a file
```bash
python3 logics/skills/logics-connector-figma/scripts/figma_list_pages.py \
  --file-key "$FIGMA_FILE_KEY"
```

## Export a node as an image
```bash
python3 logics/skills/logics-connector-figma/scripts/figma_export_node.py \
  --file-key "$FIGMA_FILE_KEY" --node-id "1744:4185" --format png --scale 2 \
  --out "output/figma/weekly.png"
```

## Import a node reference into Logics backlog
```bash
python3 logics/skills/logics-connector-figma/scripts/figma_to_backlog.py \
  --file-key "$FIGMA_FILE_KEY" --node-id "1744:4185" \
  --export --image-out-dir "output/figma"
```
