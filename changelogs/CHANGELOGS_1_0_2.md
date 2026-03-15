# Changelog (`1.0.1 -> 1.0.2`)

## Highlights

- Added structured-reference support for companion docs so product briefs and ADRs can link primary-flow items through both indicators and canonical `# References`.
- Updated companion-doc generators and fixer flows to emit canonical managed-doc references by default.
- Refreshed kit documentation to reflect the new companion-doc linking contract.

## Companion-doc linking

- `new_product_brief.py` now accepts linked workflow refs and writes them into both indicators and `# References`.
- `new_adr.py` now accepts linked workflow refs and writes them into both indicators and `# References`.
- The doc fixer now backfills `# References` for product briefs and ADRs from their related indicators.

## Documentation

- Updated the kit README with generator examples that include linked workflow refs.
- Clarified bootstrap instructions so companion docs do not rely only on prose indicators for managed relationships.
