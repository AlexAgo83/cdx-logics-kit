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
python3 logics-version-changelog-manager/scripts/generate_version_changelog.py
```

## Generate for an explicit version and previous tag

```bash
python3 logics-version-changelog-manager/scripts/generate_version_changelog.py \
  --version 1.0.1 \
  --previous-tag v1.0.0
```

## Notes

- The script writes `changelogs/CHANGELOGS_<version>.md`.
- It generates a deterministic scaffold from git commits in the selected range.
- The generated file can be curated further before a GitHub release is published.
