---
name: logics-version-release-manager
description: Automate version release publication for the kit by validating `VERSION`, changelog files in `changelogs/`, tags, and GitHub release creation. Use when preparing or publishing a kit release.
---

# Version release automation

Use this skill to validate release inputs and publish a GitHub release from a versioned changelog.

The canonical version lives in `VERSION`.
The release notes source of truth lives in `changelogs/CHANGELOGS_<version>.md`.

## Dry-run a release

```bash
python3 logics-version-release-manager/scripts/publish_version_release.py --dry-run
```

## Publish a release

```bash
python3 logics-version-release-manager/scripts/publish_version_release.py --create-tag --push
```

## Notes

- The script reads `VERSION` by default.
- It expects a matching changelog entry under `changelogs/`.
- It can create the annotated tag, push `main` and the tag, then publish the GitHub release via `gh`.
