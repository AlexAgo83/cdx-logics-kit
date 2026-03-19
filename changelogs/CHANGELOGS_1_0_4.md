# Changelog (`1.0.3 -> 1.0.4`)

## Highlights

- Hardened the flow-manager finish/close verification path so Mermaid signature refs no longer create false missing backlog or request errors.
- Reworked kit operator guidance around cross-platform Python launchers, Windows-safe command examples, temp paths, and clearly labeled platform-specific helpers.
- Added regression coverage for self-healing workflow directories and kept release-maintainer tooling aligned with the cross-platform documentation contract.

## Workflow and verification

- `finish task` follow-up and verification now ignore refs inside Mermaid blocks, which prevents truncated `logics-signature` markers from being interpreted as real workflow refs.
- Added regression coverage for missing `logics/request`, `logics/backlog`, and `logics/tasks` directories so the documented self-healing behavior stays locked down.
- Preserved the existing request -> backlog -> task generation and promotion flows while removing a false-negative finish-task edge case.

## Windows-safe operator guidance

- Standardized the documented launcher style around `python ...`, with explicit substitution guidance for `python3` and `py -3`.
- Rewrote README, skill examples, and maintainer guidance that previously assumed POSIX-only commands, temp paths, or shell continuations.
- Labeled intentionally platform-specific helpers and shell-specific command variants more explicitly so Windows users can tell what is and is not in the support contract.

## Release and maintainer tooling

- Kept release preview and dry-run commands repository-relative so the maintainer path no longer depends on `/tmp`.
- Updated `VERSION`, the README badge/examples, and the changelog index for `1.0.4`.

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `python tests/run_cli_smoke_checks.py`
- `python logics-version-release-manager/scripts/publish_version_release.py --dry-run`
