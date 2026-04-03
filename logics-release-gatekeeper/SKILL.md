---
name: logics-release-gatekeeper
description: Run project release-readiness gate checks on Logics docs and produce a pass/fail report. Use when Codex should verify completed work has validation evidence, report sections, rollback coverage for risky changes, and project changelog readiness.
---

# Release Gatekeeper

This skill primarily targets project repositories importing the kit.

It validates project-level release artifacts such as:

- `logics/CHANGELOG.md`
- `logics/RELEASE_NOTES.md`

It does not replace the kit repository release flow based on `VERSION` and `changelogs/`.

## Run gate checks

```bash
python logics/skills/logics-release-gatekeeper/scripts/release_gate_check.py
python logics/skills/logics-release-gatekeeper/scripts/release_gate_check.py --out logics/external/release/gate.md --require-release-notes
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
