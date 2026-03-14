# Changelog (`0.2.0 -> 1.0.0`)

## Major Highlights

- Promoted the kit to its first stable release.
- Added companion-doc support for `logics/product` and `logics/architecture`.
- Expanded the flow manager, fixers, linters, audits, and connectors so companion docs travel through the workflow instead of staying disconnected.
- Strengthened validation with normalized status coverage and broader automated tests.

## Workflow and Skill Changes

- Added `logics-product-brief-writer` for product framing documents in `logics/product`.
- Enriched `logics-architecture-decision-writer` so ADR/DAT docs include `Overview`, Mermaid direction diagrams, migration, and follow-up sections.
- Extended `logics-flow-manager` with:
  - decision framing for backlog and task docs;
  - optional auto-creation of product briefs and ADRs;
  - companion-doc propagation through requests, backlog items, and tasks.
- Updated bootstrap instructions and generated project structure to include product and architecture directories.
- Expanded fixers, linters, duplicate detection, index generation, relation linking, and global review scripts to understand companion docs.

## Validation and Reliability

- Added normalized `Status` lint coverage for managed docs.
- Added workflow-audit coverage around companion-doc links, Mermaid presence, and placeholder detection.
- Added automated tests for companion-doc generation, bootstrap behavior, doc fixing, duplicate detection, progress/confidence updates, and workflow audit.

## Documentation

- Refreshed the README to describe the core workflow plus optional companion product and architecture docs.
- Published the stable `v1.0.0` release and documented tag-pinning guidance.
