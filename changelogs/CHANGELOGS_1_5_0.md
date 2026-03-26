# Changelog (`1.4.1 -> 1.5.0`)

## Highlights

- Clarified hybrid runtime status semantics so missing Claude bridge files no longer make a healthy runtime look degraded.
- Added explicit per-flow backend policy metadata for shared hybrid assist flows, making `auto` dispatch behavior readable and governable.
- Expanded regression coverage around bridge detection, policy-driven backend routing, and Windows-safe runtime expectations after the move to globally published Codex skills.
- Hardened bootstrap hygiene by ensuring generated hybrid runtime artifacts are ignored automatically in new repositories.

## Hybrid runtime status and bridge semantics

- Reclassified Claude bridge availability as optional adapter metadata instead of degraded runtime health.
- Unified bridge detection across supported Claude bridge variants so the shared runtime and extension-facing status surfaces can agree on availability.
- Kept runtime-status explicit about backend health, adapter availability, and the supported shared entrypoint for hybrid assist commands.

## Explicit per-flow backend policy

- Added backend policy metadata to the shared hybrid contract so each supported flow now declares whether it is `ollama-first` or `codex-only` under `auto`.
- Kept bounded proposal flows such as `diff-risk` eligible for local-first execution while preserving codex-first behavior for `next-step`.
- Preserved audit and measurement provenance so expanded local delegation still reports actual backend used, fallback reasons, and degraded reasons.

## Bootstrap hygiene and generated artifacts

- Updated the bootstrapper so generated runtime artifacts such as hybrid assist audit, measurements, mutation audit, and cache files are added to `.gitignore` automatically.
- Added regression coverage to keep the bootstrap ignore behavior idempotent and safe around existing `.gitignore` content.

## Validation and regression coverage

- Expanded `test_logics_flow.py` coverage for healthy runtimes without Claude bridge, shared bridge-variant detection, explicit flow-policy metadata, Ollama-eligible policy paths, and codex-only policy paths.
- Kept bootstrapper regression coverage aligned with the generated-artifact ignore rules.
- Preserved release automation compatibility by keeping `VERSION`, `changelogs/`, and the publish dry-run flow aligned.

## Validation

- `python3 -m unittest tests/test_bootstrapper.py -v`
- `python3 -m unittest tests.test_logics_flow -v`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.5.0 --dry-run`
