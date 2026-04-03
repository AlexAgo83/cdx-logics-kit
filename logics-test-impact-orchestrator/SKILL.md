---
name: logics-test-impact-orchestrator
description: Analyze repository changes and produce a pragmatic test impact plan. Use when Codex should convert a git diff into a minimal but safe validation sequence (targeted tests first, then broader safety net).
---

# Test Impact Orchestrator

## Build a test impact plan

```bash
python logics/skills/logics-test-impact-orchestrator/scripts/plan_test_impact.py
python logics/skills/logics-test-impact-orchestrator/scripts/plan_test_impact.py --base origin/main --out logics/external/test-impact/latest.md
```

## Do

- Read changed files from Git (committed diff + local staged/unstaged deltas).
- Map changed areas to likely validation commands.
- Suggest targeted test files for fast feedback.
- Produce an execution order: fast checks first, safety net after.

## Output

- A Markdown test impact report that can be copied into task `# Validation` sections or PR descriptions.
