from __future__ import annotations

import socket
from typing import Any, Callable
from urllib import error as urllib_error

from logics_flow_hybrid_transport_core import *  # noqa: F401,F403

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
