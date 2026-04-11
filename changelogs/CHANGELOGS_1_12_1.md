# Changelog (`1.12.0 -> 1.12.1`)

## Major Highlights

- Hardened hybrid provider serialization so credential values are not emitted by `HybridProviderDefinition.to_dict()`.
- Added workflow-audit scanning for poisoned hybrid cache JSONL files that contain `credential_value`.
- Added regression coverage for the new serialization contract and the audit secret scan.

## Security And Audit Hardening

- The provider definition now exposes a `to_dict()` view that intentionally omits `credential_value`.
- The workflow audit exits non-zero when the hybrid audit or measurement cache includes `credential_value`.

## Validation

- `python3 -m unittest tests.test_kit_unit tests.test_workflow_audit -v`
- `python3 -m unittest tests.test_kit_lifecycle -v`
- `python3 tests/run_test_coverage.py`
