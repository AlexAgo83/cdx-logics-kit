from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request


NOISY_DIFF_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "Cargo.lock",
    "Pipfile.lock",
    "poetry.lock",
}


@dataclass(frozen=True)
class HybridProviderDefinition:
    name: str
    execution_kind: str
    endpoint: str
    model_profile: str
    model_family: str
    configured_model: str
    model: str
    credential_env: str | None = None
    credential_value: str | None = None
    credential_present: bool = False
    enabled: bool = True


def _is_noisy_diff_path(path_value: Any) -> bool:
    if not isinstance(path_value, str):
        return False
    normalized = path_value.strip()
    if " | " in normalized:
        normalized = normalized.split(" | ", 1)[0].strip()
    normalized = normalized.replace("\\", "/")
    if not normalized:
        return False
    return normalized.rsplit("/", 1)[-1] in NOISY_DIFF_FILENAMES


def _is_binary_diff_stub(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    compact = " ".join(value.strip().split())
    return bool(compact) and (" | Bin " in compact or compact.startswith("Binary files "))


def _sanitize_hybrid_context_bundle_for_prompt(context_bundle: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(context_bundle)
    git_snapshot = sanitized.get("git_snapshot")
    if isinstance(git_snapshot, dict):
        git_snapshot["changed_paths"] = [
            path for path in git_snapshot.get("changed_paths", []) if not _is_noisy_diff_path(path)
        ]
        git_snapshot["unstaged_diff_stat"] = [
            line
            for line in git_snapshot.get("unstaged_diff_stat", [])
            if not _is_noisy_diff_path(line) and not _is_binary_diff_stub(line)
        ]
        git_snapshot["staged_diff_stat"] = [
            line
            for line in git_snapshot.get("staged_diff_stat", [])
            if not _is_noisy_diff_path(line) and not _is_binary_diff_stub(line)
        ]
    context_pack = sanitized.get("context_pack")
    if isinstance(context_pack, dict):
        context_pack["changed_paths"] = [
            path for path in context_pack.get("changed_paths", []) if not _is_noisy_diff_path(path)
        ]
    return sanitized


def bounded_diagnostic_value_impl(
    value: Any,
    *,
    max_depth: int = 3,
    max_items: int = 8,
    max_string: int = 240,
) -> Any:
    if max_depth <= 0:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        collapsed = " ".join(value.split())
        return collapsed[:max_string]
    if isinstance(value, list):
        limited = [
            bounded_diagnostic_value_impl(item, max_depth=max_depth - 1, max_items=max_items, max_string=max_string)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            limited.append(f"... {len(value) - max_items} more item(s)")
        return limited
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        bounded = {
            str(key): bounded_diagnostic_value_impl(item, max_depth=max_depth - 1, max_items=max_items, max_string=max_string)
            for key, item in items
        }
        if len(value) > max_items:
            bounded["_truncated_keys"] = len(value) - max_items
        return bounded
    return repr(value)[:max_string]


def json_request_impl(
    host: str,
    request_path: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib_request.Request(
        f"{host.rstrip('/')}{request_path}",
        data=encoded,
        headers=request_headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_provider_endpoint_impl(endpoint: str, *, default_scheme: str = "https://") -> str:
    normalized = endpoint.strip()
    if not normalized:
        return normalized
    if not normalized.startswith(("http://", "https://")):
        normalized = f"{default_scheme}{normalized}"
    return normalized.rstrip("/")


def load_dotenv_values_impl(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        value = raw_value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        values[normalized_key] = value
    return values


def load_hybrid_provider_environment_impl(
    *,
    repo_root: Path | None,
    dotenv_path: str,
    environ: dict[str, str],
) -> dict[str, str]:
    resolved = dict(environ)
    if repo_root is None:
        return resolved
    normalized_dotenv_path = dotenv_path.strip()
    if normalized_dotenv_path in {"", ".env", ".env.local"}:
        dotenv_paths = [(repo_root / ".env").resolve(), (repo_root / ".env.local").resolve()]
    else:
        dotenv_paths = [(repo_root / normalized_dotenv_path).resolve()]
    dotenv_values: dict[str, str] = {}
    for path in dotenv_paths:
        dotenv_values.update(load_dotenv_values_impl(path))
    for key, value in dotenv_values.items():
        resolved.setdefault(key, value)
    return resolved


def load_provider_health_state_impl(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    if not path.is_file():
        return {"providers": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"providers": {}}
    providers = payload.get("providers", {}) if isinstance(payload, dict) else {}
    if not isinstance(providers, dict):
        return {"providers": {}}
    active: dict[str, Any] = {}
    for provider_name, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        skip_until_raw = str(entry.get("skip_until", "")).strip()
        if not skip_until_raw:
            continue
        normalized = skip_until_raw[:-1] + "+00:00" if skip_until_raw.endswith("Z") else skip_until_raw
        try:
            skip_until = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if skip_until.tzinfo is None:
            skip_until = skip_until.replace(tzinfo=timezone.utc)
        if skip_until > current_time:
            active[str(provider_name)] = entry
    return {"providers": active}


def save_provider_health_state_impl(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe_ollama_backend_impl(
    *,
    requested_backend: str,
    flow_name: str | None,
    host: str,
    model_profile: str,
    model_family: str,
    configured_model: str,
    model: str,
    timeout_seconds: float,
    default_hybrid_host: str,
    backend_policy_deterministic: str,
    backend_policy_codex_only: str,
    error_cls: type[Exception],
    backend_status_cls: type[Any],
    build_flow_backend_policy: Callable[[str], dict[str, Any]],
    json_request: Callable[[str, str], dict[str, Any]],
) -> Any:
    normalized_host = host.strip() or default_hybrid_host
    if not normalized_host.startswith(("http://", "https://")):
        normalized_host = f"http://{normalized_host}"
    normalized_host = normalized_host.rstrip("/")
    reasons: list[str] = []
    version: str | None = None
    response_time_ms: float | None = None
    reachable = False
    model_available = False
    flow_policy = build_flow_backend_policy(flow_name) if flow_name else None
    policy_mode = flow_policy["mode"] if flow_policy else None

    if policy_mode == backend_policy_deterministic:
        return backend_status_cls(
            requested_backend=requested_backend,
            selected_backend="deterministic",
            host=normalized_host,
            model_profile=model_profile,
            model_family=model_family,
            configured_model=configured_model,
            model=model,
            ollama_reachable=False,
            model_available=False,
            healthy=True,
            reasons=[],
            response_time_ms=None,
            version=None,
            selection_reason="policy-deterministic",
            policy_mode=policy_mode,
        )

    try:
        started = datetime.now(timezone.utc)
        version_payload = json_request(normalized_host, "/api/version")
        elapsed = datetime.now(timezone.utc) - started
        response_time_ms = round(elapsed.total_seconds() * 1000, 3)
        version = str(version_payload.get("version", "")) or None
        reachable = True
        tags_payload = json_request(normalized_host, "/api/tags")
        models = tags_payload.get("models", [])
        names = {
            str(item.get("name", "")).strip()
            for item in models
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        model_available = model in names
        if not model_available:
            reasons.append("ollama-model-missing")
    except urllib_error.URLError:
        reasons.append("ollama-unreachable")
    except urllib_error.HTTPError as exc:
        reasons.append(f"ollama-http-{exc.code}")
    except Exception:
        reasons.append("ollama-probe-failed")

    effective_reasons = list(reasons)
    selection_reason = None
    selected_backend = requested_backend
    healthy = reachable and model_available
    if policy_mode == backend_policy_codex_only and requested_backend == "ollama":
        raise error_cls(
            "hybrid_backend_policy_violation",
            f"Flow `{flow_name}` is policy-routed away from Ollama.",
            details={"flow": flow_name, "policy_mode": policy_mode, "requested_backend": requested_backend},
        )
    if requested_backend == "auto":
        if policy_mode == backend_policy_codex_only:
            selected_backend = "codex"
            selection_reason = "policy-codex-only"
            effective_reasons = []
        else:
            selected_backend = "ollama" if healthy else "codex"
            if selected_backend == "ollama":
                selection_reason = "auto-healthy-ollama"
                effective_reasons = []
            else:
                selection_reason = "auto-fallback-codex"
    elif requested_backend == "ollama" and not healthy:
        raise error_cls(
            "hybrid_ollama_unavailable",
            f"Ollama backend was requested explicitly but `{model}` is not healthy at {normalized_host}.",
            details={"host": normalized_host, "model": model, "reasons": reasons},
        )
    elif requested_backend in {"ollama", "codex"}:
        selected_backend = requested_backend
        selection_reason = "explicit-backend"
        effective_reasons = []

    if selected_backend == "codex" and requested_backend == "auto" and policy_mode != backend_policy_codex_only and not effective_reasons:
        effective_reasons.append("ollama-not-selected")
    return backend_status_cls(
        requested_backend=requested_backend,
        selected_backend=selected_backend,
        host=normalized_host,
        model_profile=model_profile,
        model_family=model_family,
        configured_model=configured_model,
        model=model,
        ollama_reachable=reachable,
        model_available=model_available,
        healthy=healthy,
        reasons=effective_reasons,
        response_time_ms=response_time_ms,
        version=version,
        selection_reason=selection_reason,
        policy_mode=policy_mode,
    )


def build_hybrid_provider_registry_impl(
    *,
    repo_root: Path | None,
    config: dict[str, Any] | None,
    requested_backend: str,
    requested_model: str | None,
    host: str,
    default_hybrid_host: str,
    model_profile: str,
    model_family: str,
    configured_model: str,
    model: str,
    default_dotenv_path: str = ".env",
    environ: dict[str, str] | None = None,
) -> dict[str, HybridProviderDefinition]:
    provider_config = config.get("hybrid_assist", {}).get("providers", {}) if isinstance(config, dict) else {}
    hybrid_config = config.get("hybrid_assist", {}) if isinstance(config, dict) else {}
    dotenv_path = str(hybrid_config.get("env_file", default_dotenv_path)).strip() or default_dotenv_path
    resolved_environ = load_hybrid_provider_environment_impl(
        repo_root=repo_root,
        dotenv_path=dotenv_path,
        environ=dict(os.environ) if environ is None else dict(environ),
    )

    ollama_config = provider_config.get("ollama", {}) if isinstance(provider_config, dict) else {}
    openai_config = provider_config.get("openai", {}) if isinstance(provider_config, dict) else {}
    gemini_config = provider_config.get("gemini", {}) if isinstance(provider_config, dict) else {}

    ollama_host = normalize_provider_endpoint_impl(
        host.strip() or str(ollama_config.get("host", "")).strip() or default_hybrid_host,
        default_scheme="http://",
    )
    openai_model = (
        str(requested_model).strip()
        if requested_backend == "openai" and str(requested_model or "").strip()
        else str(openai_config.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
    )
    gemini_model = (
        str(requested_model).strip()
        if requested_backend == "gemini" and str(requested_model or "").strip()
        else str(gemini_config.get("model", "gemini-2.0-flash")).strip() or "gemini-2.0-flash"
    )
    openai_key_env = str(openai_config.get("api_key_env", "OPENAI_API_KEY")).strip() or "OPENAI_API_KEY"
    gemini_key_env = str(gemini_config.get("api_key_env", "GEMINI_API_KEY")).strip() or "GEMINI_API_KEY"

    return {
        "ollama": HybridProviderDefinition(
            name="ollama",
            execution_kind="transport",
            endpoint=ollama_host,
            model_profile=model_profile,
            model_family=model_family,
            configured_model=configured_model,
            model=model,
            enabled=bool(ollama_config.get("enabled", True)),
        ),
        "openai": HybridProviderDefinition(
            name="openai",
            execution_kind="transport",
            endpoint=normalize_provider_endpoint_impl(
                str(openai_config.get("base_url", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1"
            ),
            model_profile="openai",
            model_family="openai",
            configured_model=str(openai_config.get("model", openai_model)).strip() or openai_model,
            model=openai_model,
            credential_env=openai_key_env,
            credential_value=resolved_environ.get(openai_key_env, "").strip() or None,
            credential_present=bool(resolved_environ.get(openai_key_env, "").strip()),
            enabled=bool(openai_config.get("enabled", False)),
        ),
        "gemini": HybridProviderDefinition(
            name="gemini",
            execution_kind="transport",
            endpoint=normalize_provider_endpoint_impl(
                str(gemini_config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")).strip()
                or "https://generativelanguage.googleapis.com/v1beta"
            ),
            model_profile="gemini",
            model_family="gemini",
            configured_model=str(gemini_config.get("model", gemini_model)).strip() or gemini_model,
            model=gemini_model,
            credential_env=gemini_key_env,
            credential_value=resolved_environ.get(gemini_key_env, "").strip() or None,
            credential_present=bool(resolved_environ.get(gemini_key_env, "").strip()),
            enabled=bool(gemini_config.get("enabled", False)),
        ),
        "codex": HybridProviderDefinition(
            name="codex",
            execution_kind="fallback",
            endpoint="",
            model_profile="codex",
            model_family="codex",
            configured_model="codex",
            model="codex",
        ),
        "deterministic": HybridProviderDefinition(
            name="deterministic",
            execution_kind="fallback",
            endpoint="",
            model_profile="deterministic",
            model_family="deterministic",
            configured_model="deterministic",
            model="deterministic",
        ),
    }


def probe_remote_provider_impl(
    *,
    provider: HybridProviderDefinition,
    requested_backend: str,
    timeout_seconds: float,
    provider_health_path: Path | None,
    cooldown_seconds: int,
    backend_status_cls: type[Any],
    error_cls: type[Exception],
    json_request: Callable[..., dict[str, Any]],
) -> Any:
    now = datetime.now(timezone.utc)
    health_state = load_provider_health_state_impl(provider_health_path, now=now) if provider_health_path is not None else {"providers": {}}
    cached_entry = health_state.get("providers", {}).get(provider.name) if isinstance(health_state.get("providers"), dict) else None
    reasons: list[str] = []
    response_time_ms: float | None = None
    version: str | None = None
    reachable = False
    model_available = False

    if not provider.enabled:
        reasons.append(f"{provider.name}-disabled")
    if provider.credential_env and not provider.credential_present:
        reasons.append(f"{provider.name}-missing-credentials")
    if (
        not reasons
        and isinstance(cached_entry, dict)
        and str(cached_entry.get("endpoint", "")).strip() == provider.endpoint
        and str(cached_entry.get("model", "")).strip() == provider.model
    ):
        cached_reasons = [str(reason).strip() for reason in cached_entry.get("reasons", []) if str(reason).strip()]
        if cached_reasons:
            reasons.append(f"{provider.name}-cooldown-active")
            reasons.extend(cached_reasons)

    if not reasons:
        try:
            started = datetime.now(timezone.utc)
            if provider.name == "openai":
                payload = json_request(
                    provider.endpoint,
                    f"/models/{provider.model}",
                    headers={"Authorization": f"Bearer {provider.credential_value or ''}"},
                    payload=None,
                    timeout_seconds=timeout_seconds,
                )
                version = str(payload.get("id", "")).strip() or None
            elif provider.name == "gemini":
                model_path = provider.model if provider.model.startswith("models/") else f"models/{provider.model}"
                payload = json_request(
                    provider.endpoint,
                    f"/{model_path}?key={provider.credential_value or ''}",
                    payload=None,
                    timeout_seconds=timeout_seconds,
                )
                version = str(payload.get("name", "")).strip() or None
            else:
                raise error_cls("hybrid_unknown_backend", f"Unknown remote provider `{provider.name}`.")
            elapsed = datetime.now(timezone.utc) - started
            response_time_ms = round(elapsed.total_seconds() * 1000, 3)
            reachable = True
            model_available = True
        except urllib_error.HTTPError as exc:
            if exc.code in {401, 403}:
                reasons.append(f"{provider.name}-auth-failed")
            elif exc.code == 404:
                reasons.append(f"{provider.name}-model-missing")
            else:
                reasons.append(f"{provider.name}-http-{exc.code}")
        except urllib_error.URLError:
            reasons.append(f"{provider.name}-unreachable")
        except socket.timeout:
            reasons.append(f"{provider.name}-timeout")
        except Exception:
            reasons.append(f"{provider.name}-probe-failed")

    healthy = reachable and model_available and not reasons
    should_persist_health = bool(reasons) and reasons[0] not in {
        f"{provider.name}-disabled",
        f"{provider.name}-missing-credentials",
        f"{provider.name}-cooldown-active",
    }
    if provider_health_path is not None:
        providers_state = health_state.setdefault("providers", {})
        if healthy:
            providers_state.pop(provider.name, None)
            save_provider_health_state_impl(provider_health_path, health_state)
        elif should_persist_health:
            providers_state[provider.name] = {
                "provider": provider.name,
                "endpoint": provider.endpoint,
                "model": provider.model,
                "reasons": reasons,
                "recorded_at": now.isoformat(),
                "skip_until": (now + timedelta(seconds=max(1, cooldown_seconds))).isoformat(),
            }
            save_provider_health_state_impl(provider_health_path, health_state)
    if requested_backend == provider.name and not healthy:
        raise error_cls(
            "hybrid_provider_unavailable",
            f"{provider.name} backend is not healthy for model `{provider.model}`.",
            details={"provider": provider.name, "endpoint": provider.endpoint, "model": provider.model, "reasons": reasons},
        )
    return backend_status_cls(
        requested_backend=requested_backend,
        selected_backend=provider.name if healthy or requested_backend == provider.name else "codex",
        host=provider.endpoint,
        model_profile=provider.model_profile,
        model_family=provider.model_family,
        configured_model=provider.configured_model,
        model=provider.model,
        ollama_reachable=False,
        model_available=model_available,
        healthy=healthy,
        reasons=[] if healthy else reasons,
        response_time_ms=response_time_ms,
        version=version,
        selection_reason=(
            "explicit-backend"
            if requested_backend == provider.name and healthy
            else (f"auto-healthy-{provider.name}" if requested_backend == "auto" and healthy else None)
        ),
        policy_mode=None,
    )


def select_hybrid_backend_impl(
    *,
    requested_backend: str,
    flow_name: str,
    host: str,
    default_hybrid_host: str,
    model_profile: str,
    model_family: str,
    configured_model: str,
    model: str,
    timeout_seconds: float,
    provider_registry: dict[str, HybridProviderDefinition],
    build_flow_backend_policy: Callable[[str], dict[str, Any]],
    probe_ollama_backend: Callable[..., Any],
    probe_remote_provider: Callable[..., Any],
    backend_status_cls: type[Any],
    error_cls: type[Exception],
) -> Any:
    flow_policy = build_flow_backend_policy(flow_name)
    allowed_backends = [str(value) for value in flow_policy.get("allowed_backends", [])]
    provider_order = [str(value) for value in flow_policy.get("provider_order", [])]
    normalized_host = host.strip() or default_hybrid_host
    if not normalized_host.startswith(("http://", "https://")):
        normalized_host = f"http://{normalized_host}"
    normalized_host = normalized_host.rstrip("/")

    def build_selected_status(
        provider_name: str,
        *,
        reasons: list[str],
        selection_reason: str,
    ) -> Any:
        provider = provider_registry.get(provider_name)
        return backend_status_cls(
            requested_backend=requested_backend,
            selected_backend=provider_name,
            host=provider.endpoint if provider is not None else normalized_host,
            model_profile=provider.model_profile if provider is not None else model_profile,
            model_family=provider.model_family if provider is not None else model_family,
            configured_model=provider.configured_model if provider is not None else configured_model,
            model=provider.model if provider is not None else model,
            ollama_reachable=False,
            model_available=provider_name != "ollama",
            healthy=len(reasons) == 0 or provider_name == "deterministic",
            reasons=reasons,
            response_time_ms=None,
            version=None,
            selection_reason=selection_reason,
            policy_mode=str(flow_policy.get("mode", "")) or None,
        )

    if requested_backend != "auto":
        if requested_backend not in provider_registry:
            raise error_cls(
                "hybrid_unknown_backend",
                f"Unknown hybrid backend `{requested_backend}`.",
                details={"known_backends": sorted(provider_registry.keys())},
            )
        if allowed_backends and requested_backend not in allowed_backends:
            raise error_cls(
                "hybrid_backend_policy_violation",
                f"Flow `{flow_name}` is policy-routed away from `{requested_backend}`.",
                details={"flow": flow_name, "requested_backend": requested_backend, "allowed_backends": allowed_backends},
            )
        if requested_backend == "ollama":
            return probe_ollama_backend(
                requested_backend="ollama",
                flow_name=flow_name,
                host=provider_registry["ollama"].endpoint,
                model_profile=provider_registry["ollama"].model_profile,
                model_family=provider_registry["ollama"].model_family,
                configured_model=provider_registry["ollama"].configured_model,
                model=provider_registry["ollama"].model,
                timeout_seconds=timeout_seconds,
            )
        if requested_backend in {"openai", "gemini"}:
            return probe_remote_provider(
                provider=provider_registry[requested_backend],
                requested_backend=requested_backend,
                timeout_seconds=timeout_seconds,
            )
        return build_selected_status(requested_backend, reasons=[], selection_reason="explicit-backend")

    accumulated_reasons: list[str] = []
    for provider_name in provider_order:
        provider = provider_registry.get(provider_name)
        if provider is None:
            accumulated_reasons.append(f"unknown-provider-{provider_name}")
            continue
        if provider.name == "ollama":
            try:
                status = probe_ollama_backend(
                    requested_backend="auto",
                    flow_name=flow_name,
                    host=provider.endpoint,
                    model_profile=provider.model_profile,
                    model_family=provider.model_family,
                    configured_model=provider.configured_model,
                    model=provider.model,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                error_code = getattr(exc, "code", "ollama-selection-failed")
                accumulated_reasons.append(str(error_code))
                continue
            if status.selected_backend == "ollama" and status.healthy:
                return status
            accumulated_reasons.extend(list(getattr(status, "reasons", [])))
            continue
        if provider.name in {"openai", "gemini"}:
            try:
                status = probe_remote_provider(
                    provider=provider,
                    requested_backend="auto",
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                error_code = getattr(exc, "code", f"{provider.name}-selection-failed")
                accumulated_reasons.append(str(error_code))
                continue
            if status.selected_backend == provider.name and status.healthy:
                return status
            accumulated_reasons.extend(list(getattr(status, "reasons", [])))
            continue
        if provider.execution_kind == "fallback":
            if provider.name == "deterministic":
                selection_reason = "policy-deterministic"
            elif str(flow_policy.get("mode", "")) == "codex-only" and provider.name == "codex":
                selection_reason = "policy-codex-only"
            else:
                selection_reason = "auto-provider-fallback"
            return build_selected_status(provider.name, reasons=accumulated_reasons, selection_reason=selection_reason)

    return build_selected_status("codex", reasons=accumulated_reasons, selection_reason="auto-provider-fallback")


def build_hybrid_messages_impl(flow_name: str, context_bundle: dict[str, Any]) -> list[dict[str, str]]:
    sanitized_context_bundle = _sanitize_hybrid_context_bundle_for_prompt(context_bundle)
    contract = context_bundle["contract"]
    required_keys = ", ".join(contract["required_keys"])
    contract_metadata_keys = [
        key
        for key in sorted(contract)
        if key not in {"required_keys"} and key not in contract["required_keys"]
    ]
    instruction_lines = [
        f"Flow: {flow_name}.",
        f"Return exactly one JSON object with only these top-level keys: {required_keys}.",
        "The contract block below describes the required answer shape. It is not the answer itself.",
        "Do not echo the contract or copy metadata field names into the answer.",
        "`confidence` must be a numeric value between 0.0 and 1.0. Do not use words like low, medium, or high.",
    ]
    if contract_metadata_keys:
        instruction_lines.append(
            "Do not include contract metadata keys such as: " + ", ".join(contract_metadata_keys) + "."
        )
    if flow_name == "commit-message":
        instruction_lines.extend(
            [
                "Set `scope` to one of: " + ", ".join(contract["scope_enum"]) + ".",
                "`subject` must be a concise commit subject line.",
                "`body` must be a short explanatory paragraph and may be empty if the diff is trivial.",
            ]
        )
    elif flow_name == "commit-plan":
        instruction_lines.extend(
            [
                "Set `strategy` to one of: " + ", ".join(contract["strategy_enum"]) + ".",
                "`steps` must be a non-empty JSON array of objects with keys: scope, summary, paths.",
                "Each step `scope` must be `root` or `submodule` and `paths` must be a non-empty array of strings.",
            ]
        )
    system = (
        "You are a bounded hybrid delivery assistant for the Logics workflow. "
        "Reply with one JSON object only. "
        "Do not use markdown fences. "
        "Stay within the supplied contract. "
        "Prefer conservative short outputs over speculative ones."
    )
    user = (
        "Return a JSON instance that satisfies the contract.\n\n"
        f"Answer rules:\n{chr(10).join('- ' + line for line in instruction_lines)}\n\n"
        f"Hybrid contract:\n{json.dumps(contract, indent=2, sort_keys=True)}\n\n"
        f"Context bundle:\n{json.dumps(sanitized_context_bundle, indent=2, sort_keys=True)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_ollama_hybrid_impl(
    *,
    host: str,
    model: str,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float,
    error_cls: type[Exception],
    json_request: Callable[..., dict[str, Any]],
    extract_json_object: Callable[[str], dict[str, Any]],
    build_hybrid_messages: Callable[[str, dict[str, Any]], list[dict[str, str]]],
) -> dict[str, Any]:
    messages = build_hybrid_messages(flow_name, context_bundle)
    request_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        response_payload = json_request(host, "/api/chat", payload=request_payload, timeout_seconds=timeout_seconds)
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise error_cls(
            "hybrid_ollama_http_error",
            f"Ollama returned HTTP {exc.code}: {body or exc.reason}",
            details={"host": host, "model": model, "flow": flow_name},
        ) from exc
    except urllib_error.URLError as exc:
        raise error_cls(
            "hybrid_ollama_unreachable",
            f"Could not reach Ollama at {host}: {exc.reason}",
            details={"host": host, "model": model, "flow": flow_name},
        ) from exc
    except socket.timeout as exc:
        raise error_cls(
            "hybrid_ollama_timeout",
            f"Ollama request to {host} timed out after {timeout_seconds:.1f}s.",
            details={"host": host, "model": model, "flow": flow_name, "timeout_seconds": timeout_seconds},
        ) from exc

    content = ""
    if isinstance(response_payload, dict):
        message = response_payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
    if not content:
        raise error_cls(
            "hybrid_ollama_empty_response",
            "Ollama returned an empty hybrid assist response.",
            details={"host": host, "model": model, "flow": flow_name},
        )
    try:
        result_payload = extract_json_object(content)
    except Exception as exc:  # noqa: BLE001
        message = exc.args[0] if exc.args else str(exc)
        raise error_cls(
            "hybrid_invalid_json",
            f"Ollama returned a response that did not decode to a JSON object: {message}",
            details={
                "host": host,
                "model": model,
                "flow": flow_name,
                "raw_content_preview": bounded_diagnostic_value_impl(content),
            },
        ) from exc
    return {
        "transport": "ollama",
        "host": host,
        "model": model,
        "messages": messages,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "raw_content": content,
        "result_payload": result_payload,
    }


def build_gemini_contents_impl(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    system_parts = [message["content"] for message in messages if message.get("role") == "system" and message.get("content")]
    user_parts = [message["content"] for message in messages if message.get("role") != "system" and message.get("content")]
    if system_parts:
        contents.append({"role": "user", "parts": [{"text": "\n\n".join(system_parts)}]})
    if user_parts:
        contents.append({"role": "user", "parts": [{"text": "\n\n".join(user_parts)}]})
    return contents


def run_openai_hybrid_impl(
    *,
    provider: HybridProviderDefinition,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float,
    error_cls: type[Exception],
    json_request: Callable[..., dict[str, Any]],
    extract_json_object: Callable[[str], dict[str, Any]],
    build_hybrid_messages: Callable[[str, dict[str, Any]], list[dict[str, str]]],
) -> dict[str, Any]:
    messages = build_hybrid_messages(flow_name, context_bundle)
    request_payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": 0,
    }
    try:
        response_payload = json_request(
            provider.endpoint,
            "/chat/completions",
            headers={"Authorization": f"Bearer {provider.credential_value or ''}"},
            payload=request_payload,
            timeout_seconds=timeout_seconds,
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise error_cls(
            "hybrid_openai_http_error",
            f"OpenAI returned HTTP {exc.code}: {body or exc.reason}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        ) from exc
    except urllib_error.URLError as exc:
        raise error_cls(
            "hybrid_openai_unreachable",
            f"Could not reach OpenAI at {provider.endpoint}: {exc.reason}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        ) from exc
    except socket.timeout as exc:
        raise error_cls(
            "hybrid_openai_timeout",
            f"OpenAI request to {provider.endpoint} timed out after {timeout_seconds:.1f}s.",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name, "timeout_seconds": timeout_seconds},
        ) from exc

    content = ""
    if isinstance(response_payload, dict):
        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = str(message.get("content", "")).strip()
    if not content:
        raise error_cls(
            "hybrid_openai_empty_response",
            "OpenAI returned an empty hybrid assist response.",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        )
    try:
        result_payload = extract_json_object(content)
    except Exception as exc:  # noqa: BLE001
        message = exc.args[0] if exc.args else str(exc)
        raise error_cls(
            "hybrid_invalid_json",
            f"OpenAI returned a response that did not decode to a JSON object: {message}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name, "raw_content_preview": bounded_diagnostic_value_impl(content)},
        ) from exc
    return {
        "transport": "openai",
        "host": provider.endpoint,
        "model": provider.model,
        "messages": messages,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "raw_content": content,
        "result_payload": result_payload,
    }


def run_gemini_hybrid_impl(
    *,
    provider: HybridProviderDefinition,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float,
    error_cls: type[Exception],
    json_request: Callable[..., dict[str, Any]],
    extract_json_object: Callable[[str], dict[str, Any]],
    build_hybrid_messages: Callable[[str, dict[str, Any]], list[dict[str, str]]],
) -> dict[str, Any]:
    messages = build_hybrid_messages(flow_name, context_bundle)
    request_payload = {
        "contents": build_gemini_contents_impl(messages),
        "generationConfig": {"temperature": 0},
    }
    model_path = provider.model if provider.model.startswith("models/") else f"models/{provider.model}"
    try:
        response_payload = json_request(
            provider.endpoint,
            f"/{model_path}:generateContent?key={provider.credential_value or ''}",
            payload=request_payload,
            timeout_seconds=timeout_seconds,
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise error_cls(
            "hybrid_gemini_http_error",
            f"Gemini returned HTTP {exc.code}: {body or exc.reason}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        ) from exc
    except urllib_error.URLError as exc:
        raise error_cls(
            "hybrid_gemini_unreachable",
            f"Could not reach Gemini at {provider.endpoint}: {exc.reason}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        ) from exc
    except socket.timeout as exc:
        raise error_cls(
            "hybrid_gemini_timeout",
            f"Gemini request to {provider.endpoint} timed out after {timeout_seconds:.1f}s.",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name, "timeout_seconds": timeout_seconds},
        ) from exc

    content = ""
    if isinstance(response_payload, dict):
        candidates = response_payload.get("candidates")
        if isinstance(candidates, list) and candidates:
            candidate_content = candidates[0].get("content")
            if isinstance(candidate_content, dict):
                parts = candidate_content.get("parts")
                if isinstance(parts, list):
                    text_parts = [str(part.get("text", "")).strip() for part in parts if isinstance(part, dict) and str(part.get("text", "")).strip()]
                    content = "\n".join(text_parts).strip()
    if not content:
        raise error_cls(
            "hybrid_gemini_empty_response",
            "Gemini returned an empty hybrid assist response.",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name},
        )
    try:
        result_payload = extract_json_object(content)
    except Exception as exc:  # noqa: BLE001
        message = exc.args[0] if exc.args else str(exc)
        raise error_cls(
            "hybrid_invalid_json",
            f"Gemini returned a response that did not decode to a JSON object: {message}",
            details={"host": provider.endpoint, "model": provider.model, "flow": flow_name, "raw_content_preview": bounded_diagnostic_value_impl(content)},
        ) from exc
    return {
        "transport": "gemini",
        "host": provider.endpoint,
        "model": provider.model,
        "messages": messages,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "raw_content": content,
        "result_payload": result_payload,
    }


def execute_hybrid_backend_impl(
    *,
    backend_status: Any,
    requested_backend: str,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float,
    docs_by_ref: dict[str, Any],
    validation_payload: dict[str, Any] | None,
    provider_registry: dict[str, HybridProviderDefinition],
    run_ollama_hybrid: Callable[..., dict[str, Any]],
    run_openai_hybrid: Callable[..., dict[str, Any]],
    run_gemini_hybrid: Callable[..., dict[str, Any]],
    validate_hybrid_result: Callable[..., dict[str, Any]],
    build_hybrid_failure_raw_payload: Callable[..., dict[str, Any] | None],
    build_hybrid_failure_transport: Callable[..., dict[str, Any]],
    build_fallback_result: Callable[..., dict[str, Any]],
    backend_status_cls: type[Any],
    error_cls: type[Exception],
) -> dict[str, Any]:
    degraded_reasons = list(getattr(backend_status, "reasons", []))
    raw_payload: dict[str, Any] | None = None
    transport: dict[str, Any] | None = None
    provider = provider_registry.get(backend_status.selected_backend)
    if provider is None:
        raise error_cls(
            "hybrid_unknown_backend",
            f"Unknown selected backend `{backend_status.selected_backend}`.",
            details={"known_backends": sorted(provider_registry.keys())},
        )

    if provider.execution_kind == "transport":
        try:
            if provider.name == "ollama":
                transport = run_ollama_hybrid(
                    host=backend_status.host,
                    model=backend_status.model,
                    flow_name=flow_name,
                    context_bundle=context_bundle,
                    timeout_seconds=timeout_seconds,
                )
            elif provider.name == "openai":
                transport = run_openai_hybrid(
                    provider=provider,
                    flow_name=flow_name,
                    context_bundle=context_bundle,
                    timeout_seconds=timeout_seconds,
                )
            elif provider.name == "gemini":
                transport = run_gemini_hybrid(
                    provider=provider,
                    flow_name=flow_name,
                    context_bundle=context_bundle,
                    timeout_seconds=timeout_seconds,
                )
            else:
                raise error_cls(
                    "hybrid_unknown_backend",
                    f"Unknown transport provider `{provider.name}`.",
                    details={"known_backends": sorted(provider_registry.keys())},
                )
            raw_payload = transport["result_payload"]
            validated = validate_hybrid_result(flow_name, raw_payload, docs_by_ref, context_bundle=context_bundle)
        except error_cls as exc:
            if requested_backend != "auto" and flow_name != "next-step":
                raise
            degraded_reasons.append(exc.code)
            raw_payload = build_hybrid_failure_raw_payload(exc=exc, transport=transport, raw_payload=raw_payload)
            transport = build_hybrid_failure_transport(exc=exc, transport=transport)
            validated = build_fallback_result(
                flow_name,
                context_bundle=context_bundle,
                docs_by_ref=docs_by_ref,
                validation_payload=validation_payload,
            )
            backend_status = backend_status_cls(
                requested_backend=requested_backend,
                selected_backend="codex",
                host=backend_status.host,
                model_profile=backend_status.model_profile,
                model_family=backend_status.model_family,
                configured_model=backend_status.configured_model,
                model=backend_status.model,
                ollama_reachable=backend_status.ollama_reachable,
                model_available=backend_status.model_available,
                healthy=False,
                reasons=degraded_reasons,
                response_time_ms=backend_status.response_time_ms,
                version=backend_status.version,
                selection_reason="provider-validation-fallback",
                policy_mode=backend_status.policy_mode,
            )
        return {
            "backend_status": backend_status,
            "degraded_reasons": degraded_reasons,
            "raw_payload": raw_payload,
            "transport": transport,
            "validated": validated,
        }

    reason = "policy-deterministic" if backend_status.selected_backend == "deterministic" else (
        degraded_reasons[0] if degraded_reasons else (backend_status.selection_reason or "selected-codex")
    )
    transport = {
        "transport": "deterministic" if backend_status.selected_backend == "deterministic" else "fallback",
        "reason": reason,
        "selected_backend": backend_status.selected_backend,
    }
    validated = build_fallback_result(
        flow_name,
        context_bundle=context_bundle,
        docs_by_ref=docs_by_ref,
        validation_payload=validation_payload,
    )
    raw_payload = validated.copy() if backend_status.selected_backend == "deterministic" else None
    return {
        "backend_status": backend_status,
        "degraded_reasons": degraded_reasons,
        "raw_payload": raw_payload,
        "transport": transport,
        "validated": validated,
    }
