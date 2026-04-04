# Changelog (`1.6.2 -> 1.7.0`)

## Major Highlights

- Introduced the hybrid-provider runtime architecture needed to dispatch beyond local-only execution, including provider abstraction, remote transports, readiness cooldowns, and expanded observability.
- Hardened commit-message fallback and runtime cache/launcher behavior so degraded provider states stay bounded instead of leaking unstable delivery output.
- Added substantial regression coverage around provider fallback behavior while also aligning task-creation skill entrypoints and release metadata with the new runtime model.

## Hybrid runtime foundations

- Split the hybrid runtime into clearer core, transport, and observability layers so provider dispatch logic is easier to evolve without re-entangling the monolithic runner.
- Introduced a provider abstraction that separates backend selection, transport mechanics, and reporting, which is the base for OpenAI/Gemini-style remote dispatch flows.
- Added remote hybrid provider transports and the configuration scaffolding required to drive them from the flow manager.

## Readiness gating and observability

- Added readiness cooldown gating so unhealthy or unconfigured backends can be skipped deterministically instead of being retried aggressively.
- Expanded hybrid observability reporting to expose richer execution-path and degradation details for higher-level tooling.
- Hardened the hybrid assist commit-message fallback path so degraded provider runs still return bounded, usable output.

## Delivery polish and regression coverage

- Harmonized launcher and runtime cache conventions across the kit, including bootstrap metadata and related skill references.
- Realigned the task-creation skill entrypoints so the documented paths match the current kit structure.
- Added fallback regression coverage in `tests/test_logics_flow.py` to protect the new transport and gating behavior against future breakage.

## Validation and Regression Evidence

- `python3 -m unittest discover -s tests -p "test_*.py" -v`
- `python3 tests/run_cli_smoke_checks.py`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.7.0 --dry-run`
