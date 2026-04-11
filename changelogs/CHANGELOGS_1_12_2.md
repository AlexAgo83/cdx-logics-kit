# Changelog (`1.12.1 -> 1.12.2`)

## Major Highlights

- Reorganized the flow-manager scripts into `workflow/`, `hybrid/`, `transport/`, and `audit/` subdomains.
- Kept backwards-compatible root shims so existing CLI entry points and direct module imports continue to work.
- Verified the new layout with the `flow new request --title smoke` smoke test and the workflow audit.

## Structure And Compatibility

- Moved the flow-manager implementation into domain subdirectories while preserving the public root module names.
- Added path bootstrapping so the compatibility layer can resolve shared modules and templates after the move.

## Validation

- `python3 logics/skills/logics.py flow new request --title smoke`
- `python3 logics/skills/logics.py audit`
- `python3 -m pytest logics/skills/tests/test_mermaid_generator.py logics/skills/tests/test_kit_unit.py logics/skills/tests/test_live_provider_integration.py logics/skills/tests/test_workflow_audit.py logics/skills/tests/test_codex_workspace_overlay.py -q`
