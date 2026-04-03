# Changelog (`1.6.1 -> 1.6.2`)

## Major Highlights

- Normalized repo-local file references so generated workflow docs and curated changelog outputs stop leaking absolute `/Users/...` paths when a relative repo path is sufficient.
- Added regression coverage for both workflow-doc promotion and changelog curation so path normalization stays enforced in future kit changes.
- Simplified the default GitHub release title for the kit so release publication now uses the raw tag (`vX.Y.Z`) instead of the redundant `Stable vX.Y.Z` prefix.

## Reference path normalization

- Updated `logics-flow-manager` reference normalization so absolute markdown links that point back into the repository are rewritten as repo-relative paths before being stored under `# References`.
- Updated `logics-changelog-curator` so project changelog generation also rewrites repo-local absolute markdown links to relative targets.
- Added regression tests covering both promoted workflow docs and curated changelog output to keep absolute path leakage from reappearing.

## Release title cleanup

- Updated `logics-version-release-manager` so the default GitHub release title now matches the tag directly.
- Refreshed kit release metadata for `1.6.2` by aligning `VERSION`, the README version badge, and the changelog indexes with the new version.

## Validation and Regression Evidence

- `python3 -m pytest tests/test_logics_flow.py`
- `python3 -m pytest tests/test_changelog_curator.py`
- `python3 -m pytest tests/test_version_release_manager.py`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --dry-run`
