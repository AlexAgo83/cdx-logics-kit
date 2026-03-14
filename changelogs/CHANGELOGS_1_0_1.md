# Changelog (`1.0.0 -> 1.0.1`)

## Major Highlights

- Added GitHub CI for the kit with unit tests, CLI smoke checks, changelog generation, and release automation dry-runs.
- Introduced versioned changelogs under `changelogs/` and made release notes consumable directly by GitHub releases.
- Added dedicated release-automation skills for changelog management and version publishing.

## Release and Changelog Automation

- Added a canonical `VERSION` file for the kit.
- Introduced `changelogs/CHANGELOGS_<version>.md` as the release-note source of truth.
- Added `logics-version-changelog-manager` to generate versioned changelog files from git history.
- Added `logics-version-release-manager` to validate version/tag/changelog inputs and automate GitHub release publication.
- Converted the root `CHANGELOG.md` into an index pointing to versioned changelog entries.

## Validation and CI

- Added GitHub Actions CI for:
  - Python unit tests;
  - CLI smoke checks against a temporary imported-project fixture;
  - versioned changelog generation dry-runs;
  - release-automation dry-runs.

## Documentation and Operating Model

- Updated the README with versioning, changelog, and release workflow guidance.
- Updated contribution guidance to reference versioned changelogs and release tooling.
