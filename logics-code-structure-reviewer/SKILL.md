---
name: logics-code-structure-reviewer
description: Detect the repository's likely stack/framework (heuristics) and generate an adapted code-structure review (large files, folder hygiene, suggested module/component boundaries) as a Markdown report. Use when Codex needs to check whether code is overly concentrated in single files and propose clearer structure, even when the stack is not yet known.
---

# Code structure review (stack-aware)

## Run

Print a Markdown report to stdout:

```bash
python3 logics/skills/logics-code-structure-reviewer/scripts/code_structure_review.py
```

Write the report to a file:

```bash
python3 logics/skills/logics-code-structure-reviewer/scripts/code_structure_review.py --out logics/CODE_REVIEW.md
```

## Useful flags

- `--max-lines 400`: Threshold for "large file" detection.
- `--top 20`: Number of largest files to list.
- `--include-logics`: Include `logics/**` in the scan (off by default).

