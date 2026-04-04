# Changelog (`1.7.0 -> 1.7.1`)

## Major Highlights

- Hardened the bootstrap and provider credential loading so new repos get `.env.local` placeholders automatically and the hybrid runtime merges credentials from both `.env` and `.env.local`.

## Bootstrap credential scaffolding

- The bootstrapper now generates `.env.local` with empty `OPENAI_API_KEY` and `GEMINI_API_KEY` placeholders when neither key is present in the repo, so providers can be activated without touching `.env`.
- Bootstrap also appends `.env.local` and the hybrid assist audit/measurement log paths to `.gitignore` so sensitive credentials and runtime outputs are never accidentally committed.
- When `.env` already exists and neither key has been set yet, the bootstrapper appends the missing placeholders to `.env` directly instead of creating a redundant `.env.local`.

## Provider credential loading fix

- The hybrid transport env loader now reads from both `.env` and `.env.local` when `env_file` is set to `.env` or `.env.local`, merging values so that `.env.local` overrides take effect without requiring a separate config path.

## Regression coverage

- Added bootstrapper tests covering `.env.local` creation, idempotent re-run behavior, and the case where `.env` already holds one of the provider keys.
- Added a `runtime-status` integration test verifying that credentials stored exclusively in `.env.local` are picked up correctly by the provider readiness probe.

## Validation and Regression Evidence

- `python3 -m unittest discover -s tests -p "test_*.py" -v`
- `python3 tests/run_cli_smoke_checks.py`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.7.1 --dry-run`
