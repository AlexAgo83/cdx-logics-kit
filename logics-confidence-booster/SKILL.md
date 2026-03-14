---
name: logics-confidence-booster
description: Ask clarifying questions with suggested defaults to raise Understanding/Confidence above 90% for Logics request/backlog/task docs, and to strengthen product or architecture companion docs with a clarified `# Clarifications` section plus optional status updates.
---

# Confidence booster (Logics)

Use this skill to quickly raise Understanding/Confidence on `logics/request|backlog|tasks/*.md` by asking a short set of high‑signal questions, applying suggested defaults when acceptable, and updating indicators.

For `logics/product/*.md` and `logics/architecture/*.md`, use it to strengthen decision framing: it appends a `# Clarifications` section and can update `Status`, but it does not invent `Understanding`/`Confidence` indicators for those doc families.

## Run (interactive)

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/request/req_001_example.md
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/product/prod_001_example.md --apply-defaults --status Active
```

## Run (apply defaults, no prompts)

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py \
  logics/request/req_001_example.md \
  --apply-defaults
```

## Notes
- The script appends a `# Clarifications` section (or updates it if present).
- For request/backlog/task docs, indicators are auto‑computed from answered questions when you don’t supply explicit values.
- You can override indicators with `--understanding` and `--confidence`.
- For product/architecture docs, use `--status` if the clarification changes document maturity.
- Use for requests, backlog items, tasks, product briefs, and architecture docs.
