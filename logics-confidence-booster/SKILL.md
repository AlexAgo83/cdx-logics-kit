---
name: logics-confidence-booster
description: Ask clarifying questions with suggested defaults to raise Understanding/Confidence above 90% for Logics request/backlog/task docs and update indicators accordingly.
---

# Confidence booster (Logics)

Use this skill to quickly raise Understanding/Confidence on `logics/request|backlog|tasks/*.md` by asking a short set of high‑signal questions, applying suggested defaults when acceptable, and updating indicators.

## Run (interactive)

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/request/req_001_example.md
```

## Run (apply defaults, no prompts)

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py \
  logics/request/req_001_example.md \
  --apply-defaults
```

## Notes
- The script appends a `# Clarifications` section (or updates it if present).
- Indicators are auto‑computed from answered questions when you don’t supply explicit values.
- You can override indicators with `--understanding` and `--confidence`.
- Use for requests, backlog items, and tasks.
