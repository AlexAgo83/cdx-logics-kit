# Changelog (`1.2.0 -> 1.3.0`)

## Highlights

- Added a deterministic local dispatcher for Logics workflow orchestration so local models can propose bounded `new`, `promote`, `split`, `finish`, and safe `sync` actions without direct file-write authority.
- Added the shared hybrid assist runtime for repetitive delivery operations such as `commit-all`, `next-step`, `summarize-validation`, `summarize-pr`, `triage`, and `handoff`, with `ollama -> codex` fallback, audit logs, and bounded execution policy.
- Added repo-native runtime configuration, unified `logics.py` entrypoints, transactional bulk-mutation safety, and incremental indexing so repeated kit operations stay predictable and fast.
- Expanded local model support from a DeepSeek-only default to curated `deepseek-coder` and `qwen-coder` profiles, with aligned runtime status reporting and Ollama specialist guidance.

## Deterministic dispatcher and runtime foundations

- Added `flow sync dispatch-context` and `flow sync dispatch` so a local model can consume a compact structured workflow bundle and return a strict decision contract validated by a deterministic runner.
- Added shared repo-native runtime configuration in `logics.yaml`, centralized policy resolution, and unified operator entrypoints through `python logics/skills/logics.py ...`.
- Added incremental runtime indexing, machine-readable status surfaces, and transaction-aware bulk apply or rollback behavior to improve automation safety and repeatability.
- Extended workflow audit, registry export, and surrounding runtime metadata so downstream plugin and agent surfaces can rely on one shared contract instead of duplicating logic.

## Hybrid assist delivery flows

- Added shared hybrid assist flows for bounded repetitive delivery work, including `runtime-status`, `commit-all`, `summarize-pr`, `summarize-validation`, `next-step`, `triage`, and `handoff`.
- Added governance surfaces for backend provenance, degraded-mode reporting, audit JSONL, and measurement JSONL so integrations can explain when Ollama was used and when the runtime fell back to Codex.
- Kept risky behavior bounded by default: suggestion-first execution, strict payload validation, and thin-client expectations for Codex, Claude, and plugin surfaces.

## Local model profile support and Ollama guidance

- Added curated local model profiles for `deepseek-coder` and `qwen-coder`, with `--model-profile` support on the shared hybrid runtime surfaces.
- Updated the Ollama specialist skill, environment checks, and integration guidance so operators can use the bounded DeepSeek or Qwen coding paths without drifting into arbitrary unsupported tags by default.
- Improved model-family detection and runtime-status reporting so the selected local profile is visible in health checks and downstream automation.

## Skill packaging and documentation hardening

- Fixed skill-package handling so block-scalar descriptions in `SKILL.md` frontmatter remain supported instead of breaking package discovery or validation.
- Refreshed the kit README, changelog index, and versioned examples for the `1.3.0` release line.

## Validation

- `python3 -m unittest discover -s tests -p "test_*.py" -v`
- `python3 tests/run_cli_smoke_checks.py`
- `python3 logics-doc-linter/scripts/logics_lint.py --require-status`
- `python3 logics-flow-manager/scripts/workflow_audit.py --group-by-doc`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.3.0 --dry-run`
