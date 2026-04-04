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
python logics-version-release-manager/scripts/publish_version_release.py --dry-run
```

## Publish a release

```bash
python logics-version-release-manager/scripts/publish_version_release.py --create-tag --push
```

## Prepare and publish a release with the shared AI runtime

`flow assist prepare-release` is the preferred end-to-end release helper. It chains `release-changelog-status`, `validation-checklist`, and `diff-risk` checks before invoking the publish script:

```bash
# Check readiness only (default suggestion-only mode)
python logics/skills/logics.py flow assist prepare-release --format json

# Dry-run the publish commands without executing them
python logics/skills/logics.py flow assist prepare-release --execution-mode execute --dry-run --format json

# Publish: create tag, push, and create GitHub release
python logics/skills/logics.py flow assist prepare-release --execution-mode execute --push --format json

# Publish as a draft release
python logics/skills/logics.py flow assist prepare-release --execution-mode execute --push --draft --format json
```

The `ready` key in the JSON output is `true` only when the curated changelog exists and the working tree is clean. The publish script is not invoked when `ready` is `false`.

## Check the release surface individually

```bash
python logics/skills/logics.py flow assist release-changelog-status --format json
python logics/skills/logics.py flow assist commit-all
```

## Notes

- The script reads `VERSION` by default; override with `--version X.Y.Z`.
- It expects a matching changelog entry under `changelogs/`.
- It can create the annotated tag, push `main` and the tag, then publish the GitHub release via `gh`.
- `flow assist prepare-release` is the preferred release helper; the publish script itself stays deterministic.
