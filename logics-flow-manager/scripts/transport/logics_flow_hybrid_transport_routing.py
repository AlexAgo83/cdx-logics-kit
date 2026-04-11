from __future__ import annotations

from typing import Any, Callable

from logics_flow_hybrid_transport import HybridProviderDefinition


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
