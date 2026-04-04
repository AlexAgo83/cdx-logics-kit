from __future__ import annotations

from datetime import datetime, timezone
import json
import socket
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request


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
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(
        f"{host.rstrip('/')}{request_path}",
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


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
    build_flow_backend_policy: Callable[[str], dict[str, str]],
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


def build_hybrid_messages_impl(flow_name: str, context_bundle: dict[str, Any]) -> list[dict[str, str]]:
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
        f"Context bundle:\n{json.dumps(context_bundle, indent=2, sort_keys=True)}"
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
