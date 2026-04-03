---
name: logics-release-notes
description: Generate project-level release notes from completed Logics tasks. Use when Codex should scan `logics/tasks` and produce a Markdown release notes file grouped by completed work (e.g., Progress 100%).
---

# Generate release notes

This skill is for project repositories importing the kit under `logics/skills/`.

It generates `logics/RELEASE_NOTES.md` for project delivery tracking.
It is separate from the kit repository release flow, which now uses `VERSION` and `changelogs/`.

## Run

```bash
python logics/skills/logics-release-notes/scripts/generate_release_notes.py --out logics/RELEASE_NOTES.md
```
