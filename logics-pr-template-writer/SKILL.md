---
name: logics-pr-template-writer
description: Generate a pull request description from a Logics task. Use when Codex should read `logics/tasks/*.md` and produce a PR template (summary, scope, validation, risks) suitable for GitHub/GitLab.
---

# PR template

## Generate from a task

```bash
python3 logics/skills/logics-pr-template-writer/scripts/generate_pr_template.py logics/tasks/task_000_example.md --out PR.md
```

