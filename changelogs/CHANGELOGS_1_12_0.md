# Changelog (`1.11.0 -> 1.12.0`)

## Major Highlights

- Added generated Logics index and relationship guardrails so the corpus is easier to navigate and missing links are more visible.
- Smoothed workflow-doc generation by aligning Mermaid signatures with the workflow docs and making generated diagrams more contextual.
- Reduced repeated token churn in the runtime by caching context packs and normalizing cache keys.
- Clarified doc-specific reminders so generated request, backlog, and task docs stay closer to the kit conventions.

## Workflow And Navigation

- Added Logics index and relationship guardrails to keep the corpus navigable and to flag unresolved references earlier.
- Aligned Mermaid signatures with workflow docs so generated diagrams stay consistent with the workflow contract.

## Runtime And Diagram Quality

- Cached Logics context packs and normalized cache keys to reduce repeated work during workflow operations.
- Made Mermaid diagrams more contextual for the current workflow slice.

## Documentation And Reminder Cleanup

- Clarified Logics doc-specific reminders to better guide request, backlog, and task edits.

## Validation And Regression Evidence

- `python3 -m unittest tests.test_indexer_links`
- `python3 -m unittest tests.test_version_changelog_manager tests.test_version_release_manager`
- `python3 logics.py flow assist release-changelog-status --format json`
