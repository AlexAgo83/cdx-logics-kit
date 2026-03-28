# Changelog (`1.6.0 -> 1.6.1`)

## Highlights

- Fixed progress parsing in the global reviewer so decorated values such as `100% (audit-aligned)` are now bucketed as real progress instead of being reported as invalid.
- Added regression coverage to keep Mermaid signature refresh and lint flows aligned, preventing stale-signature false positives from reappearing after a refresh pass.
- Refreshed the kit release metadata for `1.6.1` by aligning `VERSION`, the README badge, and this versioned changelog.

## Global reviewer progress normalization

- Updated `logics-global-reviewer` to accept numeric-prefix progress values instead of requiring an exact bare `NN%` token.
- Preserved invalid-value reporting for genuinely malformed progress indicators while treating decorated normalized values as valid workflow states.

## Mermaid lint regression coverage

- Added a regression test that runs `refresh-mermaid-signatures` and then lints the resulting workflow doc to ensure the refreshed signature is accepted without a stale-warning false positive.
- Added companion regression coverage for the global reviewer so future progress-format changes do not silently break progress distribution reporting.

## Validation

- `python3 -m unittest tests.test_global_reviewer tests.test_logics_lint -v`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --dry-run`
