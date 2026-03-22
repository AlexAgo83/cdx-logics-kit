# Changelog (`1.0.4 -> 1.1.0`)

## Highlights

- Added a multi-project Codex workspace overlay manager so repositories can project repo-local Logics skills into isolated `CODEX_HOME` overlays without moving the canonical `logics/skills` source tree.
- Hardened overlay diagnostics, lifecycle handling, and concurrent multi-repo validation so operator workflows can detect stale, broken, or moved workspace overlays before launch.
- Added Mermaid signature refresh support and stronger task-wave checkpoint guidance so generated workflow docs stay synchronized and commit-ready during delivery.

## Codex workspace overlays

- Added `logics-flow-manager/scripts/logics_codex_workspace.py` with `register`, `sync`, `status`, `doctor`, `run`, and `clean` commands for overlay-backed Codex sessions.
- Added `logics-flow-manager/scripts/logics_codex_workspace_support.py` to manage overlay manifests, repo-vs-global skill precedence, shared global assets, copy fallback publication, and workspace identity tracking.
- Added regression coverage in `tests/test_codex_workspace_overlay.py` for sync, doctor, copy-mode drift detection, multi-repo isolation, and moved-repository lifecycle behavior.

## Workflow governance maintenance

- Added `logics_flow.py sync refresh-mermaid-signatures` so stale `%% logics-signature` markers can be refreshed without hand-editing managed docs.
- Updated the flow-manager task template and generated task guidance so each delivery wave leaves documentation updated and the repository in a commit-ready state.
- Aligned `logics-doc-linter` with the shared Mermaid-signature computation so signature-only refreshes no longer produce false workflow-maintenance failures.

## Documentation and maintainer guidance

- Updated `README.md`, `CHANGELOG.md`, and versioned examples for the `1.1.0` release.
- Kept the kit release workflow centered on `VERSION`, `changelogs/`, and the existing changelog and release-manager scripts.

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `python tests/run_cli_smoke_checks.py`
- `python logics-version-release-manager/scripts/publish_version_release.py --dry-run`
