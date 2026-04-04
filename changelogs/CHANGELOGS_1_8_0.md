# Changelog (`1.7.1 -> 1.8.0`)

## Major Highlights

- New `flow assist prepare-release` composite command that orchestrates the full release readiness check and optional publication in one step.
- `release-changelog-status` now falls back to the `VERSION` file when no `package.json` is present, making it work correctly for kit-style repositories.

## New Assist: `prepare-release`

- Added `cmd_assist_prepare_release` to `logics_flow.py` as a composite command that chains `release-changelog-status`, `validation-checklist`, and `diff-risk` checks.
- Git snapshot is captured before any assist calls so audit log creation does not pollute the working-tree status check.
- `release-changelog-status` is forced to `auto` backend internally regardless of the operator's `--backend` flag, as it is always deterministic.
- `--execution-mode execute` invokes `publish_version_release.py`; blocked with a structured error when `ready` is `false` (missing changelog or uncommitted changes).
- `--push` flag creates the annotated tag, pushes `main` and the tag, and publishes the GitHub release.
- `--draft` flag creates a draft GitHub release instead of publishing immediately.
- `--version` flag overrides the detected version.
- Added route guard in `_run_hybrid_assist` for the `prepare-release` flow name.
- 4 new integration tests covering: readiness reporting, missing changelog detection, execute dry-run, and blocked execution on uncommitted changes.

## `release-changelog-status` VERSION Fallback

- `_resolve_release_changelog_status` now reads `VERSION` when `package.json` is absent or contains `0.0.0`.
- Priority order: `package.json` → `VERSION` → `0.0.0` default.
- Result payload includes a `version_source` field (`"package.json"`, `"VERSION"`, or `"default"`).

## SKILL.md Updates

- `logics-hybrid-delivery-assistant`: documented `prepare-release` alias, `--push`/`--draft` flags, and risky-execution guidance.
- `logics-version-release-manager`: replaced the previous manual workflow with `flow assist prepare-release` as the canonical end-to-end release helper; kept individual alias docs as a fallback reference.
- `logics-version-changelog-manager`: added `release-changelog-status` to the post-generation review surface.
- `logics-changelog-curator`: clarified kit-vs-project scope.
- `logics-flow-manager`: updated template and boundary docs.

## Validation

- `python3 logics/skills/logics.py lint`
- `python3 logics/skills/logics.py audit --group-by-doc`
- `python3 logics/skills/tests/test_logics_flow.py` (70 tests, all passing)
