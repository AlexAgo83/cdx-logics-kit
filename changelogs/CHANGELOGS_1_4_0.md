# Changelog (`1.3.0 -> 1.4.0`)

## Highlights

- Added a governed hybrid assist runtime foundation that exposes bounded delivery actions through the flow manager instead of pushing integrations toward ad hoc scripting.
- Added explicit hybrid assist activation surfaces and aliases so operators and downstream tooling can call the shared runtime through stable entrypoints.
- Added bounded commit execution support for hybrid assist flows, including commit planning and guarded execution paths in the flow manager.
- Expanded curated local-model support so hybrid assist runtime flows can select aligned DeepSeek or Qwen profiles with clearer operator guidance.

## Hybrid assist runtime foundation

- Added the shared `logics_flow_hybrid.py` runtime foundation and integrated it into the flow manager so hybrid assist actions can share one implementation surface.
- Added governance-oriented runtime behavior around bounded execution, structured outputs, and safer handoff semantics for downstream consumers.
- Kept hybrid delivery behavior anchored in the flow manager contract instead of duplicating runtime logic across multiple thin clients.

## Activation surfaces and bounded delivery flows

- Added explicit hybrid assist activation surfaces and aliases in `logics_flow.py` so operators can reach the runtime through stable flow-manager commands.
- Added the `logics-hybrid-delivery-assistant` skill package and matching agent metadata so the new hybrid flows are discoverable from the kit itself.
- Extended commit-oriented delivery flows so the runtime can propose and execute a bounded commit path instead of stopping at suggestion-only wiring.

## Curated model-profile support

- Added configurable hybrid model profiles for curated DeepSeek and Qwen paths so local runtime usage stays within supported defaults.
- Updated the Ollama specialist guidance and runtime configuration handling so model-family expectations stay aligned with the selected hybrid profile.
- Improved operator documentation so the preferred runtime entrypoints and supported local-model paths remain visible in the kit docs.

## Validation

- `python3 -m unittest discover -s tests -p "test_*.py" -v`
- `python3 tests/run_cli_smoke_checks.py`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.4.0 --dry-run`
