# Changelog (`1.8.0 -> 1.9.0`)

## Major Highlights

- `prepare-release` and `publish-release` are now two distinct commands with a clear separation of concerns: prepare handles AI-assisted content generation; publish handles tag creation and GitHub release.
- New `generate-changelog` AI flow (ollama-first, Codex fallback) generates a curated changelog file when one is missing.
- `prepare-release --execution-mode execute` automatically generates the changelog via AI if missing, updates the README version badge if stale, and commits the prep changes before reporting readiness.
- New `publish-release` command handles tag creation, branch push, and GitHub release publication.

## `prepare-release` Refactor

- Removed `--push`, `--draft`, and `--version` flags from `prepare-release` — these are now on `publish-release`.
- Execute pipeline: generate changelog (AI) → update README badge → commit prep → re-check readiness → report.
- Payload now includes `prep_steps` and `prep_errors` instead of `publish_result` and `executed`.
- Route guard added for `publish-release` in `_run_hybrid_assist`.

## New `publish-release` Command

- Checks `release-changelog-status` to verify prerequisites.
- In `suggestion-only` mode: reports readiness and shows the command to run.
- In `execute --push` mode: invokes `publish_version_release.py --create-tag --push`.
- Supports `--draft`, `--version`, and `--dry-run` flags.

## New `generate-changelog` Flow

- Flow contract: `content`, `title`, `entries`, `confidence`, `rationale`.
- Backend policy: `ollama-first` with Codex fallback.
- Context profile: `diff-first`, `normal`.
- Deterministic fallback derives entries from changed-path categories when no AI runtime is available.

## VS Code Plugin

- Added **Publish Release** button to the Assist section of the Tools panel.
- `Prepare Release` button now runs prep-only flow (changelog + README + commit).
- `Publish Release` button checks readiness then confirms before invoking publish with `--push`.
- Updated descriptions in hostApi, toolsPanelLayout, mainInteractions, and viewMessages.

## Type Updates

- `HybridPrepareReleaseResult`: replaced `publish_result` with `prep_steps` and `prep_errors`.
- New `HybridPublishReleaseResult` type with `changelog_status` and `publish_result`.
- `parseHybridPublishReleaseResult` parser added.

## Tests

- 4 existing tests updated to match the new `prepare-release` payload shape (no `executed`, no `publish_result`).
- 2 new tests added for `publish-release`: execute dry-run invokes publish script, blocked when uncommitted changes present.
- 72 tests total, all passing.

## Validation

- `python3 logics/skills/logics.py lint`
- `python3 logics/skills/logics.py audit --group-by-doc`
- `python3 logics/skills/tests/test_logics_flow.py` (72 tests, all passing)
