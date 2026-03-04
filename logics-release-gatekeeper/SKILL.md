---
name: logics-release-gatekeeper
description: Run release-readiness gate checks on Logics docs and produce a pass/fail report. Use when Codex should verify completed work has validation evidence, report sections, rollback coverage for risky changes, and changelog readiness.
---

# Release Gatekeeper

## Run gate checks

```bash
python3 logics/skills/logics-release-gatekeeper/scripts/release_gate_check.py
python3 logics/skills/logics-release-gatekeeper/scripts/release_gate_check.py --out logics/external/release/gate.md --require-release-notes
```

## Do

- Scan completed tasks and completed backlog items.
- Enforce minimum release gates:
  - completed tasks contain validation and report sections
  - risky completed tasks include rollback coverage
  - completed backlog items still expose acceptance criteria
  - changelog exists before release
- Return non-zero on gate failure for CI usage.

## Output

- A Markdown gate report with actionable failures and warnings.
