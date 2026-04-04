---
name: logics-changelog-curator
description: Curate user-facing project changelog entries from Logics release notes or completed tasks. Use when Codex should turn `logics/RELEASE_NOTES.md` into a cleaner project-level `logics/CHANGELOG.md` and remove internal references/noise.
---

# Changelog curation

This skill is for project repositories importing the kit under `logics/skills/`.

It is not the canonical release workflow for the kit repository itself.
For kit releases, use:

- `logics-version-changelog-manager` for `VERSION` + `changelogs/CHANGELOGS_<version>.md`
- `logics-version-release-manager` for tag and GitHub release publication

## Generate from release notes

```bash
python logics/skills/logics-changelog-curator/scripts/curate_changelog.py --in logics/RELEASE_NOTES.md --out logics/CHANGELOG.md
```

## Review with the shared AI runtime

The curation script stays deterministic. When you want a bounded wording review after generation, use:

```bash
python logics/skills/logics.py flow assist summarize-changelog --format json
```
