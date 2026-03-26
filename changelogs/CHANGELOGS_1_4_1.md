# Changelog (`1.4.0 -> 1.4.1`)

## Highlights

- Hardened the hybrid Ollama runtime so local assist flows stay on `ollama` more reliably instead of degrading on contract-shape mismatches.
- Added bounded diagnostics and stronger semantic tests for hybrid assist responses, including validation of real `commit-message` and `commit-plan` payloads.
- Updated kit guidance away from overlay-first Codex runtime assumptions so the published global-kit model stays consistent in docs and operator flows.

## Hybrid assist runtime hardening

- Hardened prompt instructions so local models are told to return an instance of the contract, not the contract schema itself.
- Added safer handling for invalid JSON, timeouts, and bounded diagnostic previews when a local run still fails and degrades to Codex.
- Normalized common textual confidence values such as `low`, `medium`, and `high` so healthy Ollama responses do not fall back unnecessarily on minor formatting drift.
- Confirmed the shared runtime can keep `commit-message` and `commit-plan` on `ollama` with valid structured outputs.

## Validation and regression coverage

- Expanded `test_logics_flow.py` coverage for valid local payloads, invalid semantic payloads, transport failures, and textual-confidence normalization.
- Kept runtime diagnostics inspectable in audit and ROI outputs so degraded local runs remain debuggable.
- Preserved release automation compatibility by keeping the kit versioned changelog and publish flow aligned with the kit root contract.

## Documentation and guidance

- Deprecated overlay-first Codex runtime guidance in favor of the current global published-kit direction.
- Kept the kit’s release and operator docs aligned with the bounded hybrid runtime and thin-client plugin model.

## Validation

- `python3 -m pytest tests/test_logics_flow.py -q`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --version 1.4.1 --dry-run`
