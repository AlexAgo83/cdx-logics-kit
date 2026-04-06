# Changelog (`1.9.1 -> 1.10.0`)

## Major Highlights

- Hybrid assist now preclassifies diffs, reuses git snapshots, and caches short-lived results so bounded flows do less repeated work.
- `next-step` can explicitly dispatch to OpenAI or Gemini, and `auto` can opt into a remote backend through `logics.yaml`.
- New bounded authoring flows add `request-draft`, `spec-first-pass`, and `backlog-groom`, each with an `--execution-mode execute` path for writing docs after confirmation.
- Mermaid generation is now centralized in a dedicated `logics-mermaid-generator` skill with hybrid AI generation, validation guardrails, canonical signature management, and deterministic fallback.
- The release also hardens remote-provider normalization, Mermaid fallback reporting, and next-step fallback behavior so degraded runs stay bounded instead of crashing.

## Hybrid Runtime Efficiency

- Added diff preprocessing and cached git snapshot reuse for hybrid assist flows.
- Added a short-lived result cache so repeated bounded flows can reuse recent validated results within a TTL.
- Added profile downgrade handling and deterministic preclassification to reduce unnecessary AI dispatch on obvious diff shapes.
- Added tier metadata to skill manifests so runtime publication can distinguish the minimal core surface from optional skills.

## Remote Backend Coverage

- `next-step` now supports explicit `--backend openai` and `--backend gemini` dispatch with bounded validation and Codex fallback.
- Added `next_step_auto_backend` configuration in `logics.yaml` so `auto` can route through a chosen remote provider when healthy.
- Added `request-draft`, `spec-first-pass`, and `backlog-groom` authoring flows for bounded proposal generation.
- Added `--execution-mode execute` for authoring flows so operators can write the generated docs after explicit confirmation instead of copying outputs manually.
- Hardened remote payload normalization for authoring flows and next-step so malformed provider payloads degrade cleanly instead of failing hard.

## Mermaid Skill and Flow Wiring

- Added a dedicated `logics-mermaid-generator` skill package with deterministic rendering support compatible with the flow manager.
- Added hybrid AI Mermaid generation with safety validation and canonical fallback behavior.
- Wired all flow-manager Mermaid call sites through the dedicated skill so `new`, `promote`, and signature refresh use the same entry point.
- Restored remote-provider fallback in the Mermaid generator and normalized provider output into canonical managed Mermaid blocks.
- Adjusted Mermaid telemetry so fallback runs report the backend that actually produced the final result.

## Quality and Regression Hardening

- `next-step` now ignores extra provider fields for `action=new` and degrades cleanly when a remote decision is incomplete.
- Newly created workflow docs no longer seed placeholder values like `X.X.X` or `??%`.
- AC Traceability blocks now carry actionable proof guidance instead of raw TODO placeholders.
- Added regression coverage for remote backend dispatch, authoring execute mode, Mermaid canonicalization, and hybrid fallback reporting.

## Validation

- `python3 logics.py lint`
- `python3 logics.py audit --group-by-doc`
- `python3 -m unittest discover -s tests -p "test_*.py" -v`
