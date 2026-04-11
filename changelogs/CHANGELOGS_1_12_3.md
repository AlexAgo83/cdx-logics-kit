# Changelog (`1.12.2 -> 1.12.3`)

## Major Highlights

- Replaced the remaining numbered flow-manager test suites with domain-named suites.
- Extended the kit coverage work so the main `workflow/` and `transport/` cores are exercised by targeted branch tests.
- Kept the compatibility shims in place so the flow-manager entry points continue to work after the test and coverage reorganization.

## Structure And Compatibility

- Renamed the remaining numbered test files to domain-oriented names to make the coverage surface easier to navigate.
- Preserved the existing script entry points while the test layout became more focused.

## Validation

- `python3 -m pytest logics/skills/tests/test_hybrid_runtime.py logics/skills/tests/test_hybrid_runtime_aliases.py logics/skills/tests/test_workflow_assist_aliases.py logics/skills/tests/test_workflow_release.py logics/skills/tests/test_workflow_requests.py -q`
- `npm run coverage:kit`
