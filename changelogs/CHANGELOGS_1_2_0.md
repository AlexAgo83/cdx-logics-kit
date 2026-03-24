# Changelog (`1.1.0 -> 1.2.0`)

## Highlights

- Added a kit-native compact AI context and handoff layer so workflow docs can now expose reusable `# AI Context` metadata, refresh older docs, and generate smaller context-pack artifacts directly from the flow manager.
- Expanded the internal automation contract of the kit with machine-readable flow-manager outputs, explicit workflow schema metadata, graph export, skill validation, governance profiles, and safer multi-file mutation previews.
- Added operator-focused runtime tooling with a kit `doctor`, canonical workflow and skill-package parse models, centralized conventions and capability registries, and regression fixtures or benchmarks for skill-package evolution.
- Hardened skill loading by fixing invalid `SKILL.md` YAML frontmatter across the shipped skills and by validating package structure more explicitly.

## Compact AI context and token hygiene

- Added compact `# AI Context` generation to managed workflow docs and support to refresh or backfill that metadata on existing request, backlog, and task files.
- Added `logics_flow.py sync context-pack` with profile-driven and mode-driven output such as `summary-only`, `diff-first`, and machine-readable JSON payloads.
- Added token-hygiene checks and corpus-maintenance support so oversized or stale workflow sections can be flagged before they turn into noisy AI handoffs.
- Refactored request and backlog import connectors to rely on shared flow-manager workflow assembly helpers instead of drifting per connector.

## Governance, schema, and machine-readable tooling

- Added explicit `Schema version` indicators to generated workflow docs and support to inspect or migrate schema state with flow-manager sync commands.
- Added machine-readable outputs across the core flow-manager surface, including `new`, `promote`, `close`, `finish`, and the new sync operations.
- Added workflow graph export, skill-package validation, registry export, and named governance profiles for downstream automation and repository-level policy control.
- Extended `workflow_audit.py` with structural autofix for missing schema metadata, missing `# AI Context`, and missing DoR/DoD sections.

## Diagnostics, safety, and regression coverage

- Added a kit `doctor` command that reports missing workflow directories, invalid skill packages, and schema drift with actionable remediation guidance.
- Added canonical workflow-doc and skill-package models so multiple kit surfaces share the same read-side parsing and normalization contract.
- Added safe-write mutation planning for bulk workflow operations, including previewable diffs before writes.
- Added reusable skill-package fixtures and expanded automated coverage for JSON outputs, schema migration, graph export, doctor diagnostics, governance behavior, and skill validation.

## Skill and documentation hardening

- Fixed invalid YAML frontmatter in shipped `SKILL.md` files so Codex skill discovery no longer skips those packages.
- Refreshed the kit README to present the project more clearly as a durable AI-context and delivery-memory system, and updated versioned examples for `1.2.0`.

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `python tests/run_cli_smoke_checks.py`
- `python logics-doc-linter/scripts/logics_lint.py --require-status`
- `python logics-flow-manager/scripts/workflow_audit.py --group-by-doc`
- `python logics-version-release-manager/scripts/publish_version_release.py --version 1.2.0 --dry-run`
