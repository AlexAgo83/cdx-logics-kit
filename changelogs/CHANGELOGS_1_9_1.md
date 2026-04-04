# Changelog (`1.9.0 -> 1.9.1`)

## Major Highlights

- `prepare-release` now detects when the current version is already tagged or published and can move the kit to the next patch version before preparing the release.
- Release readiness now surfaces version drift between `package.json` and `VERSION`, and `publish-release` blocks until those artifacts are aligned.
- Bootstrap now updates every `.env*` file found at the repository root instead of assuming only `.env` or `.env.local`.

## Release Flow Hardening

- `release-changelog-status` now reports `already_published`, `tag_exists_local`, `tag_exists_remote`, `next_version`, `next_tag`, `package_version`, `version_file_version`, and `version_mismatch`.
- The deterministic release summary now warns explicitly when the target tag already exists and points operators toward the next patch release instead of incorrectly treating the current version as reusable.
- `prepare-release --execution-mode execute` now bumps the next patch version automatically when the current one is already published, then re-evaluates readiness against that new version.
- The release prep flow now updates all version artifacts consistently, including `package.json`, `package-lock.json`, and `VERSION` when those files exist in the target repository.
- `publish-release` now blocks on already-published tags and on `VERSION` / `package.json` drift instead of attempting a release with stale metadata.

## Version Resolution Consistency

- `generate_version_changelog.py` now resolves the active release version from `package.json` first when present, then falls back to `VERSION`.
- `publish_version_release.py` now uses the same version resolution order, so changelog generation and publishing no longer disagree on the release version in hybrid repositories.
- This closes the common failure mode where `package.json` had already moved forward but `VERSION` was left behind.

## Bootstrap Improvements

- The bootstrapper now scans every root-level `.env*` file, appends missing provider placeholders to each one that needs them, and creates `.env.local` only when no env file exists at all.
- This makes provider remediation safer on older repositories that already rely on custom env file layouts.

## Tests

- Added regression coverage for:
  - `prepare-release` auto-bumping when the current version is already tagged
  - blocking publish when `VERSION` is out of sync with `package.json`
  - preferring `package.json` over stale `VERSION` in both changelog generation and release publication
  - updating all matching `.env*` files during bootstrap

## Validation

- `python3 logics.py lint`
- `python3 logics.py audit --group-by-doc`
- `python3 -m unittest logics.skills.tests.test_logics_flow -v`
