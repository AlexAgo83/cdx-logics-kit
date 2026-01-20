---
name: logics-changelog-curator
description: Curate user-facing changelog entries from Logics release notes or completed tasks. Use when Codex should turn `logics/RELEASE_NOTES.md` into a cleaner `logics/CHANGELOG.md` and remove internal references/noise.
---

# Changelog curation

## Generate from release notes

```bash
python3 logics/skills/logics-changelog-curator/scripts/curate_changelog.py --in logics/RELEASE_NOTES.md --out logics/CHANGELOG.md
```

