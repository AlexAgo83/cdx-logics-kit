---
name: logics-version-changelog-manager
description: Generate versioned release changelogs for the kit under `changelogs/CHANGELOGS_<version>.md` from git history. Use when preparing or refreshing a release changelog before publishing a tag or GitHub release.
---

# Versioned changelog generation

Use this skill when the kit needs a new changelog entry for a released or upcoming version.

The canonical kit version lives in `VERSION`.
Versioned release notes live in `changelogs/`.

## Generate the changelog for the current version

```bash
python logics-version-changelog-manager/scripts/generate_version_changelog.py
```

## Generate for an explicit version and previous tag

```bash
python logics-version-changelog-manager/scripts/generate_version_changelog.py \
  --version 1.0.1 \
  --previous-tag v1.0.0
```

## Review with the shared AI runtime

Keep the deterministic script as the source of truth for the file generation, then use the shared hybrid assist runtime to review the result:

```bash
python logics/skills/logics.py flow assist summarize-changelog --format json
python logics/skills/logics.py flow assist release-changelog-status --format json
```

## Notes

- The script writes `changelogs/CHANGELOGS_<version>.md`.
- It generates a deterministic scaffold from git commits in the selected range.
- The generated file can be curated further before a GitHub release is published.
- The AI runtime is a review and curation layer around the generated file, not a replacement for the deterministic changelog scaffold.
