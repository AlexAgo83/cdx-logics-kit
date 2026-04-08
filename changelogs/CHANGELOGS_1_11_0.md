# Changelog (`1.10.0 -> 1.11.0`)

## Major Highlights

- The flow-manager runtime has been broken into smaller command, core, hybrid-runtime, transport, and workflow-support modules, making the kit easier to maintain and extend without leaning on giant entrypoint files.
- Coverage is materially stronger across the highest-risk areas: core flow-manager behavior, sandbox lifecycle paths, and opt-in live provider integration now all have dedicated regression suites.
- Release and operator ergonomics are more reliable: coverage output no longer conflicts with the Python `coverage` package, RTK guidance is documented for Codex flows, and late release fixes close dispatch/helper export gaps.

## Flow-Manager Modularization

- Completed a broad modularization wave across `logics_flow.py`, hybrid runtime, transport, workflow support, and audit entrypoints.
- Split large orchestration surfaces into clearer command-oriented modules such as main commands, doc commands, assist commands, runtime support, and transport routing/core helpers.
- Preserved the canonical `python logics.py ...` operator flow while reducing the maintenance burden of oversized script files.

## Coverage And Validation Expansion

- Added CI-level kit coverage reporting.
- Added 112 unit tests for the highest-risk flow-manager modules.
- Added 9 sandbox lifecycle tests covering bootstrap, doctor, and schema migration paths.
- Added 13 opt-in live provider integration tests to exercise remote provider flows without forcing them into the default local test path.
- Added shared test utilities and split the monolithic flow test surface into multiple focused suites for better debugging and safer future refactors.

## Reliability Fixes

- Fixed the `coverage/` output directory collision that could shadow the Python `coverage` package.
- Fixed the mapped dispatch command entrypoint.
- Fixed Logics flow helper exports for downstream command wiring.

## Contributor And Release Workflow

- Added RTK guidance for Codex operators in the kit repository.
- Refreshed release artifacts for the `1.10.1` and `1.11.0` preparation steps.
- Updated the changelog index and repository docs to reflect the new release line.

## Validation

- `python3 tests/run_test_coverage.py`
- `python3 -m unittest tests.test_kit_unit -v`
- `python3 -m unittest tests.test_kit_lifecycle -v`
- `python3 -m unittest tests.test_live_provider_integration -v`
