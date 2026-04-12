# Changelog (`1.12.3 -> 1.13.0`)

## Major Highlights

- Strengthened release readiness around task 133 with early workflow validation.
- Tightened flow-manager relationship handling by deriving task links from the source data instead of relying on manual wiring.
- Preserved mermaid label coverage after the Unicode regression fix, keeping the generator tests stable and explicit.

## Validation and CI

- Added early workflow validation for task 133.
- Reworked the mermaid generator test label coverage so the Unicode path remains exercised.
- Restored the non-ASCII character in the unsafe mermaid label test block.
- Updated flow-manager task links to use derived-from relationships.

## Scope Notes

- This release is focused on internal tooling, validation, and workflow hygiene.
- No user-facing API surface changes were introduced in this cycle.

## Validation

- `python3 -m pytest tests/test_version_changelog_manager.py tests/test_version_release_manager.py tests/test_workflow_release.py tests/test_mermaid_generator.py tests/test_logics_flow_06.py -q`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --dry-run --version 1.13.0`
