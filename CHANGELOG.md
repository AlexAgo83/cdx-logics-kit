# Changelog

All notable changes to `cdx-logics-kit` are documented in this file.

## [1.0.0] - 2026-03-14

First stable release of the kit.

### Added

- Product companion-doc support with `logics/product` and the new `logics-product-brief-writer` skill.
- Architecture decision enrichment for ADR/DAT documents, including `Overview` sections and Mermaid direction diagrams.
- Decision framing in `logics-flow-manager` with optional companion-doc generation for product briefs and ADRs.
- Companion-doc propagation through requests and external imports.
- Bootstrap coverage for product and architecture directories and instructions.
- Test coverage for product briefs, workflow audit, bootstrap behavior, progress/confidence updates, and duplicate detection.

### Changed

- Expanded the documented Logics workflow to support optional companion product and architecture docs alongside the core request/backlog/task/spec flow.
- Updated fixers, linters, duplicate detection, index generation, relationship linking, and global review scripts to understand product and architecture docs.
- Improved connector imports so imported requests and backlog items can carry companion-doc framing instead of leaving unresolved placeholders.
- Normalized status handling and reinforced release-readiness documentation in the README.

### Fixed

- Added lint coverage for normalized `Status` usage on managed docs.
- Improved repair/update helpers so companion-doc indicators and references stay consistent when docs are touched.
- Hardened workflow audit coverage around companion-doc links, Mermaid presence, and placeholder detection.

## [0.2.0] - 2026-03-09

- Refreshed README and repository metadata.
- Published the `v0.2.0` tagged release before the stable companion-doc workflow expansion.

[1.0.0]: https://github.com/AlexAgo83/cdx-logics-kit/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/AlexAgo83/cdx-logics-kit/releases/tag/v0.2.0
