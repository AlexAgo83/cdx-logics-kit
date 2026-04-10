from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path

from logics_flow_config import get_config_value
from logics_flow_hybrid import (
    DEFAULT_HYBRID_AUDIT_LOG,
    DEFAULT_HYBRID_BACKEND,
    DEFAULT_HYBRID_HOST,
    DEFAULT_HYBRID_MEASUREMENT_LOG,
    DEFAULT_HYBRID_MODEL,
    DEFAULT_HYBRID_MODEL_PROFILE,
    DEFAULT_HYBRID_RESULT_CACHE,
    DEFAULT_HYBRID_RESULT_CACHE_TTL_SECONDS,
    DEFAULT_HYBRID_TIMEOUT_SECONDS,
    HybridAssistError,
    HybridBackendStatus,
    apply_legacy_default_model,
    build_flow_contract,
    merge_hybrid_model_profiles,
    resolve_hybrid_model_selection,
    select_hybrid_backend,
)
from logics_flow_hybrid_transport_core import _normalize_hybrid_diff_signals

NEXT_STEP_AUTO_BACKEND_CHOICES = ("openai", "gemini")


def _hybrid_default_backend(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_backend", default=DEFAULT_HYBRID_BACKEND))


def _next_step_auto_backend(config: dict[str, object]) -> str | None:
    configured = str(get_config_value(config, "hybrid_assist", "next_step_auto_backend", default="")).strip().lower()
    if configured in NEXT_STEP_AUTO_BACKEND_CHOICES:
        return configured
    return None


def _configured_flow_contract(flow_name: str, config: dict[str, object]) -> dict[str, object]:
    contract = deepcopy(build_flow_contract(flow_name))
    if flow_name != "next-step":
        return contract
    configured_backend = _next_step_auto_backend(config)
    if configured_backend is None:
        return contract
    backend_policy = deepcopy(contract.get("backend_policy", {}))
    backend_policy["auto_backend"] = configured_backend
    backend_policy["provider_order"] = [configured_backend, "codex"]
    backend_policy["selection_summary"] = (
        "Allow `next-step` auto routing to use the configured remote provider first, "
        "then fall back to Codex with a logged warning if the configured provider is unavailable."
    )
    contract["backend_policy"] = backend_policy
    return contract


def _select_hybrid_backend_for_flow(
    *,
    requested_backend: str,
    flow_name: str,
    repo_root: Path,
    config: dict[str, object],
    requested_model: str | None,
    host: str,
    model_profile: str,
    model_family: str,
    configured_model: str,
    model: str,
    timeout_seconds: float,
) -> tuple[HybridBackendStatus, list[str]]:
    configured_auto_backend = _next_step_auto_backend(config) if flow_name == "next-step" and requested_backend == "auto" else None
    if configured_auto_backend is None:
        return (
            select_hybrid_backend(
                requested_backend=requested_backend,
                flow_name=flow_name,
                repo_root=repo_root,
                config=config,
                requested_model=requested_model,
                host=host,
                model_profile=model_profile,
                model_family=model_family,
                configured_model=configured_model,
                model=model,
                timeout_seconds=timeout_seconds,
            ),
            [],
        )

    try:
        configured_status = select_hybrid_backend(
            requested_backend=configured_auto_backend,
            flow_name=flow_name,
            repo_root=repo_root,
            config=config,
            requested_model=requested_model,
            host=host,
            model_profile=model_profile,
            model_family=model_family,
            configured_model=configured_model,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    except HybridAssistError as exc:
        fallback_status = select_hybrid_backend(
            requested_backend="codex",
            flow_name=flow_name,
            repo_root=repo_root,
            config=config,
            requested_model=requested_model,
            host=host,
            model_profile=model_profile,
            model_family=model_family,
            configured_model=configured_model,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        return (
            HybridBackendStatus(
                requested_backend="auto",
                selected_backend=fallback_status.selected_backend,
                host=fallback_status.host,
                model_profile=fallback_status.model_profile,
                model_family=fallback_status.model_family,
                configured_model=fallback_status.configured_model,
                model=fallback_status.model,
                ollama_reachable=fallback_status.ollama_reachable,
                model_available=fallback_status.model_available,
                healthy=fallback_status.healthy,
                reasons=[f"next-step-auto-backend-{configured_auto_backend}-fallback", exc.code],
                response_time_ms=fallback_status.response_time_ms,
                version=fallback_status.version,
                selection_reason="config-auto-backend-fallback",
                policy_mode=fallback_status.policy_mode,
            ),
            [f"next-step-auto-backend-{configured_auto_backend}-fallback", exc.code],
        )

    return (
        HybridBackendStatus(
            requested_backend="auto",
            selected_backend=configured_status.selected_backend,
            host=configured_status.host,
            model_profile=configured_status.model_profile,
            model_family=configured_status.model_family,
            configured_model=configured_status.configured_model,
            model=configured_status.model,
            ollama_reachable=configured_status.ollama_reachable,
            model_available=configured_status.model_available,
            healthy=configured_status.healthy,
            reasons=[],
            response_time_ms=configured_status.response_time_ms,
            version=configured_status.version,
            selection_reason="config-auto-backend",
            policy_mode=configured_status.policy_mode,
        ),
        [],
    )


def _hybrid_default_model(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_model", default=DEFAULT_HYBRID_MODEL))


def _hybrid_default_model_profile(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_model_profile", default=DEFAULT_HYBRID_MODEL_PROFILE))


def _hybrid_model_profiles(config: dict[str, object]) -> dict[str, dict[str, object]]:
    configured = merge_hybrid_model_profiles(get_config_value(config, "hybrid_assist", "model_profiles", default={}))
    return apply_legacy_default_model(
        configured,
        default_profile=_hybrid_default_model_profile(config),
        legacy_default_model=(
            str(get_config_value(config, "hybrid_assist", "default_model", default="")).strip() or None
            if _hybrid_default_model_profile(config) == DEFAULT_HYBRID_MODEL_PROFILE
            else None
        ),
    )


def _hybrid_model_selection(
    config: dict[str, object],
    *,
    requested_model_profile: str | None,
    requested_model: str | None,
) -> dict[str, object]:
    profiles = _hybrid_model_profiles(config)
    selection = resolve_hybrid_model_selection(
        configured_profiles=profiles,
        default_profile=_hybrid_default_model_profile(config),
        requested_profile=requested_model_profile,
        requested_model=requested_model,
    )
    selection["supported_profiles"] = profiles
    return selection


def _hybrid_default_host(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "ollama_host", default=DEFAULT_HYBRID_HOST))


def _hybrid_default_timeout(config: dict[str, object]) -> float:
    return float(get_config_value(config, "hybrid_assist", "timeout_seconds", default=DEFAULT_HYBRID_TIMEOUT_SECONDS))


def _hybrid_audit_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "audit_log", default=DEFAULT_HYBRID_AUDIT_LOG))


def _hybrid_measurement_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "measurement_log", default=DEFAULT_HYBRID_MEASUREMENT_LOG))


def _hybrid_result_cache_enabled(config: dict[str, object]) -> bool:
    return bool(get_config_value(config, "hybrid_assist", "result_cache", "enabled", default=True))


def _hybrid_result_cache_path(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "result_cache", "path", default=DEFAULT_HYBRID_RESULT_CACHE))


def _hybrid_result_cache_ttl_seconds(config: dict[str, object]) -> int:
    return max(
        1,
        int(
            get_config_value(
                config,
                "hybrid_assist",
                "result_cache",
                "ttl_seconds",
                default=DEFAULT_HYBRID_RESULT_CACHE_TTL_SECONDS,
            )
        ),
    )


def _load_hybrid_result_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    entries = payload.get("entries") if isinstance(payload, dict) else {}
    return {"entries": entries if isinstance(entries, dict) else {}}


def _write_hybrid_result_cache(path: Path, entries: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": entries}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prune_hybrid_result_cache_entries(entries: dict[str, object], *, now_ts: float) -> dict[str, object]:
    kept: dict[str, object] = {}
    for key, value in entries.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        expires_at = value.get("expires_at")
        if not isinstance(expires_at, (int, float)) or float(expires_at) <= now_ts:
            continue
        if not isinstance(value.get("validated_payload"), dict):
            continue
        kept[key] = value
    return kept


def _build_hybrid_result_cache_key(
    *,
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    context_bundle: dict[str, object],
) -> tuple[str, str]:
    normalized_signals = _normalize_hybrid_diff_signals(context_bundle)
    context_pack = context_bundle.get("context_pack", {})
    fingerprint_payload = {
        "seed_ref": context_bundle.get("seed_ref"),
        "context_profile": context_bundle.get("context_profile"),
        "mode": context_pack.get("mode") if isinstance(context_pack, dict) else None,
        "profile": context_pack.get("profile") if isinstance(context_pack, dict) else None,
        "requested_backend": requested_backend,
        "model_profile": model_selection.get("name"),
        "resolved_model": model_selection.get("resolved_model"),
        "changed_paths": normalized_signals["changed_paths"],
        "unstaged_diff_stat": normalized_signals["unstaged_diff_stat"],
        "staged_diff_stat": normalized_signals["staged_diff_stat"],
    }
    diff_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_key = hashlib.sha256(f"{flow_name}:{diff_fingerprint}".encode("utf-8")).hexdigest()
    return cache_key, diff_fingerprint


def _read_hybrid_result_cache_entry(
    *,
    repo_root: Path,
    config: dict[str, object],
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    context_bundle: dict[str, object],
    dry_run: bool,
) -> tuple[Path, str, str, dict[str, object] | None]:
    cache_path = (repo_root / _hybrid_result_cache_path(config)).resolve()
    cache_key, diff_fingerprint = _build_hybrid_result_cache_key(
        flow_name=flow_name,
        requested_backend=requested_backend,
        model_selection=model_selection,
        context_bundle=context_bundle,
    )
    if not _hybrid_result_cache_enabled(config):
        return cache_path, cache_key, diff_fingerprint, None
    cache_payload = _load_hybrid_result_cache(cache_path)
    entries = cache_payload["entries"] if isinstance(cache_payload, dict) else {}
    now_ts = time.time()
    pruned_entries = _prune_hybrid_result_cache_entries(entries if isinstance(entries, dict) else {}, now_ts=now_ts)
    if not dry_run and pruned_entries != entries:
        _write_hybrid_result_cache(cache_path, pruned_entries)
    cached_entry = pruned_entries.get(cache_key) if isinstance(pruned_entries.get(cache_key), dict) else None
    return cache_path, cache_key, diff_fingerprint, cached_entry


def _write_hybrid_result_cache_entry(
    *,
    cache_path: Path,
    cache_key: str,
    diff_fingerprint: str,
    ttl_seconds: int,
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    backend_status: HybridBackendStatus,
    result_status: str,
    raw_payload: dict[str, object] | None,
    validated_payload: dict[str, object],
    transport: dict[str, object],
    confidence: float | None,
    review_recommended: bool,
) -> None:
    cache_payload = _load_hybrid_result_cache(cache_path)
    entries = cache_payload["entries"] if isinstance(cache_payload, dict) else {}
    now_ts = time.time()
    pruned_entries = _prune_hybrid_result_cache_entries(entries if isinstance(entries, dict) else {}, now_ts=now_ts)
    pruned_entries[cache_key] = {
        "flow": flow_name,
        "diff_fingerprint": diff_fingerprint,
        "stored_at": now_ts,
        "expires_at": now_ts + ttl_seconds,
        "requested_backend": requested_backend,
        "backend_status": backend_status.to_dict(),
        "result_status": result_status,
        "raw_payload": raw_payload,
        "validated_payload": validated_payload,
        "transport": transport,
        "confidence": confidence,
        "review_recommended": review_recommended,
        "active_model_profile": {
            "name": model_selection["name"],
            "family": model_selection["family"],
            "configured_model": model_selection["configured_model"],
            "resolved_model": model_selection["resolved_model"],
            "description": model_selection["description"],
            "example_tags": model_selection["example_tags"],
        },
    }
    _write_hybrid_result_cache(cache_path, pruned_entries)
