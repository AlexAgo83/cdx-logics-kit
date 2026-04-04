from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from logics_flow_models import WorkflowDocModel


def default_context_spec_impl(
    flow_name: str,
    *,
    flow_context_profiles: dict[str, dict[str, Any]],
    error_cls: type[Exception],
) -> dict[str, Any]:
    if flow_name not in flow_context_profiles:
        raise error_cls("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    return dict(flow_context_profiles[flow_name])


def build_flow_backend_policy_impl(
    flow_name: str,
    *,
    flow_contracts: dict[str, dict[str, Any]],
    flow_backend_policies: dict[str, dict[str, str]],
    backend_policy_modes: tuple[str, ...],
    supported_backend_names: tuple[str, ...],
    error_cls: type[Exception],
) -> dict[str, Any]:
    if flow_name not in flow_contracts:
        raise error_cls("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    policy = flow_backend_policies.get(flow_name)
    if policy is None:
        raise error_cls("hybrid_missing_backend_policy", f"Missing backend policy for flow `{flow_name}`.")
    mode = str(policy.get("mode", "")).strip()
    auto_backend = str(policy.get("auto_backend", "")).strip()
    if mode not in backend_policy_modes:
        raise error_cls(
            "hybrid_invalid_backend_policy",
            f"Flow `{flow_name}` uses unsupported backend policy mode `{mode}`.",
        )
    if auto_backend not in supported_backend_names:
        raise error_cls(
            "hybrid_invalid_backend_policy",
            f"Flow `{flow_name}` uses unsupported auto backend `{auto_backend}`.",
        )
    if mode == "deterministic":
        provider_order = ["deterministic"]
    elif mode == "codex-only":
        provider_order = ["codex"]
    else:
        provider_order = ["ollama", "codex"]

    configured_provider_order = policy.get("provider_order")
    if isinstance(configured_provider_order, list):
        normalized_provider_order = [
            str(provider_name).strip()
            for provider_name in configured_provider_order
            if str(provider_name).strip()
        ]
        if normalized_provider_order:
            provider_order = normalized_provider_order

    configured_allowed_backends = policy.get("allowed_backends")
    if isinstance(configured_allowed_backends, list):
        allowed_backends = [
            str(provider_name).strip()
            for provider_name in configured_allowed_backends
            if str(provider_name).strip()
        ]
    else:
        allowed_backends = list(provider_order)

    return {
        "mode": mode,
        "auto_backend": auto_backend,
        "fallback_policy": str(policy.get("fallback_policy", "")).strip(),
        "selection_summary": str(policy.get("selection_summary", "")).strip(),
        "provider_order": provider_order,
        "allowed_backends": allowed_backends,
    }


def default_hybrid_model_profiles_impl(
    *,
    default_profiles: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return deepcopy(default_profiles)


def infer_model_family_impl(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("deepseek"):
        return "deepseek"
    if normalized.startswith("qwen"):
        return "qwen"
    return "custom"


def merge_hybrid_model_profiles_impl(
    overrides: dict[str, Any] | None,
    *,
    default_profiles: dict[str, dict[str, Any]],
    infer_model_family: Callable[[str], str],
) -> dict[str, dict[str, Any]]:
    profiles = deepcopy(default_profiles)
    if not isinstance(overrides, dict):
        return profiles
    for raw_name, raw_profile in overrides.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        profile_name = raw_name.strip()
        current = deepcopy(profiles.get(profile_name, {}))
        if not isinstance(raw_profile, dict):
            profiles[profile_name] = current
            continue
        model = str(raw_profile.get("model", current.get("model", ""))).strip()
        family = str(raw_profile.get("family", current.get("family", infer_model_family(model)))).strip() or infer_model_family(model)
        description = str(raw_profile.get("description", current.get("description", ""))).strip()
        example_tags = raw_profile.get("example_tags", current.get("example_tags", []))
        if not isinstance(example_tags, list):
            example_tags = []
        profiles[profile_name] = {
            "family": family or "custom",
            "model": model,
            "description": description or f"{profile_name} local model profile.",
            "example_tags": [str(tag).strip() for tag in example_tags if str(tag).strip()],
        }
    return profiles


def apply_legacy_default_model_impl(
    profiles: dict[str, dict[str, Any]],
    *,
    default_profile: str,
    legacy_default_model: str | None,
    infer_model_family: Callable[[str], str],
) -> dict[str, dict[str, Any]]:
    if not legacy_default_model:
        return profiles
    resolved = deepcopy(profiles)
    profile = deepcopy(resolved.get(default_profile, {}))
    profile["family"] = str(profile.get("family") or infer_model_family(legacy_default_model))
    profile["model"] = legacy_default_model
    profile["description"] = str(profile.get("description") or f"{default_profile} local model profile.")
    example_tags = profile.get("example_tags", [])
    if not isinstance(example_tags, list):
        example_tags = []
    if legacy_default_model not in example_tags:
        example_tags = [legacy_default_model, *example_tags]
    profile["example_tags"] = [str(tag).strip() for tag in example_tags if str(tag).strip()]
    resolved[default_profile] = profile
    return resolved


def resolve_hybrid_model_selection_impl(
    *,
    configured_profiles: dict[str, dict[str, Any]],
    default_profile: str,
    requested_profile: str | None,
    requested_model: str | None,
    infer_model_family: Callable[[str], str],
    error_cls: type[Exception],
) -> dict[str, Any]:
    profile_name = (requested_profile or default_profile).strip()
    if profile_name not in configured_profiles:
        raise error_cls(
            "hybrid_unknown_model_profile",
            f"Unknown hybrid model profile `{profile_name}`.",
            details={"known_profiles": sorted(configured_profiles.keys())},
        )
    spec = deepcopy(configured_profiles[profile_name])
    configured_model = str(spec.get("model", "")).strip()
    if not configured_model:
        raise error_cls(
            "hybrid_invalid_model_profile",
            f"Hybrid model profile `{profile_name}` is missing a configured model tag.",
        )
    resolved_model = (requested_model or configured_model).strip()
    if not resolved_model:
        raise error_cls("hybrid_invalid_model", "Hybrid model selection resolved to an empty model tag.")
    family = str(spec.get("family") or infer_model_family(resolved_model)).strip() or infer_model_family(resolved_model)
    return {
        "name": profile_name,
        "family": family,
        "configured_model": configured_model,
        "resolved_model": resolved_model,
        "description": str(spec.get("description", "")).strip(),
        "example_tags": [str(tag).strip() for tag in spec.get("example_tags", []) if str(tag).strip()],
    }


def build_shared_hybrid_contract_impl(
    *,
    schema_version: str,
    supported_backend_names: tuple[str, ...],
    safety_classes: tuple[str, ...],
    backend_policy_modes: tuple[str, ...],
    result_statuses: tuple[str, ...],
    flow_contracts: dict[str, dict[str, Any]],
    default_hybrid_model_profiles: Callable[[], dict[str, dict[str, Any]]],
    build_flow_backend_policy: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "backends": list(supported_backend_names),
        "safety_classes": list(safety_classes),
        "backend_policy_modes": list(backend_policy_modes),
        "result_statuses": list(result_statuses),
        "model_profiles": default_hybrid_model_profiles(),
        "flows": {
            flow: {
                "summary": contract["summary"],
                "safety_class": contract["safety_class"],
                "required_keys": list(contract["required_keys"]),
                "backend_policy": build_flow_backend_policy(flow),
            }
            for flow, contract in sorted(flow_contracts.items())
        },
    }


def build_flow_contract_impl(
    flow_name: str,
    *,
    schema_version: str,
    flow_contracts: dict[str, dict[str, Any]],
    allowed_dispatch_actions: tuple[str, ...],
    safe_sync_kinds: tuple[str, ...],
    build_flow_backend_policy: Callable[[str], dict[str, Any]],
    error_cls: type[Exception],
) -> dict[str, Any]:
    contract = flow_contracts.get(flow_name)
    if contract is None:
        raise error_cls("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    payload = {
        "schema_version": schema_version,
        "flow": flow_name,
        "summary": contract["summary"],
        "safety_class": contract["safety_class"],
        "required_keys": list(contract["required_keys"]),
        "backend_policy": build_flow_backend_policy(flow_name),
    }
    for key in ("scope_enum", "overall_enum", "classification_enum", "risk_enum", "strategy_enum"):
        if key in contract:
            payload[key] = list(contract[key])
    if flow_name == "next-step":
        payload["allowed_actions"] = list(allowed_dispatch_actions)
        payload["safe_sync_kinds"] = list(safe_sync_kinds)
    return payload


def normalize_confidence_impl(raw_value: Any, *, error_cls: type[Exception]) -> float:
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        string_confidence_map = {
            "low": 0.4,
            "medium": 0.65,
            "med": 0.65,
            "high": 0.85,
        }
        if normalized in string_confidence_map:
            raw_value = string_confidence_map[normalized]
        else:
            try:
                raw_value = float(normalized)
            except ValueError as exc:
                raise error_cls(
                    "hybrid_invalid_confidence",
                    "Confidence must be numeric or one of low, medium, high.",
                ) from exc
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise error_cls("hybrid_invalid_confidence", "Confidence must be numeric.")
    value = float(raw_value)
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    if value < 0.0 or value > 1.0:
        raise error_cls("hybrid_invalid_confidence", "Confidence must be between 0.0 and 1.0.")
    return round(value, 4)


def normalize_string_list_impl(
    value: Any,
    key: str,
    *,
    min_items: int,
    error_cls: type[Exception],
) -> list[str]:
    if not isinstance(value, list):
        raise error_cls("hybrid_invalid_list", f"`{key}` must be an array of strings.")
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise error_cls("hybrid_invalid_list", f"`{key}` must contain only non-empty strings.")
        normalized.append(" ".join(item.split()))
    if len(normalized) < min_items:
        raise error_cls("hybrid_invalid_list", f"`{key}` must contain at least {min_items} item(s).")
    return normalized


def looks_generic_commit_subject_impl(subject: str, *, generic_commit_subjects: set[str]) -> bool:
    normalized = " ".join(subject.split()).strip().lower()
    if normalized in generic_commit_subjects:
        return True
    if "surfaces" in normalized:
        return True
    return False


def infer_commit_focus_from_paths_impl(changed_paths: list[str]) -> str | None:
    lowered_paths = [path.lower() for path in changed_paths]
    if any("tools" in path or "toolbar" in path for path in lowered_paths):
        return "tools panel navigation"
    if any("activity" in path for path in lowered_paths):
        return "activity panel rendering"
    if any("webview" in path for path in lowered_paths):
        return "plugin webview behavior"
    if any("environment" in path for path in lowered_paths):
        return "environment diagnostics"
    if any(path.startswith("tests/") or "/tests/" in path for path in lowered_paths):
        return "test coverage"
    return None


def build_deterministic_commit_subject_impl(
    git_snapshot: dict[str, Any],
    *,
    infer_commit_focus_from_paths: Callable[[list[str]], str | None],
) -> str:
    changed_paths = list(git_snapshot.get("changed_paths", []))
    if changed_paths and all(path.startswith("logics/skills/") or path == "logics/skills" for path in changed_paths):
        return "Update Logics skills submodule pointer"

    focus = infer_commit_focus_from_paths(changed_paths)
    if focus:
        if git_snapshot.get("touches_tests") and focus != "test coverage":
            return f"Refine {focus} and test coverage"
        return f"Refine {focus}"

    if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
        return "Update hybrid assist runtime and plugin integration"
    if git_snapshot.get("touches_plugin") and git_snapshot.get("touches_tests"):
        return "Refine plugin webview and test coverage"
    if git_snapshot.get("touches_plugin"):
        return "Refine plugin webview behavior"
    if git_snapshot.get("touches_runtime"):
        return "Update hybrid assist runtime flows"
    if git_snapshot.get("doc_only"):
        return "Update Logics planning and workflow docs"
    return "Update repository files"


def validate_hybrid_result_impl(
    flow_name: str,
    payload: dict[str, Any],
    docs_by_ref: dict[str, WorkflowDocModel],
    *,
    context_bundle: dict[str, Any] | None,
    flow_contracts: dict[str, dict[str, Any]],
    error_cls: type[Exception],
    validate_dispatcher_decision: Callable[[dict[str, Any], dict[str, WorkflowDocModel]], Any],
    normalize_confidence: Callable[[Any], float],
    normalize_string_list: Callable[[Any, str], list[str]],
    looks_generic_commit_subject: Callable[[str], bool],
) -> dict[str, Any]:
    contract = flow_contracts.get(flow_name)
    if contract is None:
        raise error_cls("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    required = set(contract["required_keys"])
    missing = sorted(required - set(payload))
    if missing:
        raise error_cls(
            "hybrid_missing_field",
            f"Hybrid assist payload is missing required field(s): {', '.join(missing)}.",
            details={"missing_fields": missing, "flow": flow_name},
        )

    if flow_name == "next-step":
        decision = validate_dispatcher_decision(payload, docs_by_ref)
        return decision.to_dict()

    normalized: dict[str, Any] = {}
    for key in required:
        normalized[key] = payload[key]
    normalized["confidence"] = normalize_confidence(payload["confidence"])
    rationale = payload["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise error_cls("hybrid_invalid_rationale", "`rationale` must be a non-empty string.")
    normalized["rationale"] = " ".join(rationale.split())[:500]

    if flow_name == "commit-message":
        subject = payload["subject"]
        if not isinstance(subject, str) or not subject.strip():
            raise error_cls("hybrid_invalid_subject", "`subject` must be a non-empty string.")
        normalized["subject"] = " ".join(subject.split())[:72]
        if looks_generic_commit_subject(normalized["subject"]):
            details: dict[str, Any] = {"subject": normalized["subject"]}
            if context_bundle is not None:
                details["changed_paths"] = list(context_bundle.get("git_snapshot", {}).get("changed_paths", []))[:8]
            raise error_cls(
                "hybrid_generic_subject",
                "`subject` is too generic for a commit message; name the real changed area.",
                details=details,
            )
        body = payload["body"]
        if not isinstance(body, str):
            raise error_cls("hybrid_invalid_body", "`body` must be a string.")
        normalized["body"] = body.strip()[:400]
        scope = payload["scope"]
        if scope not in contract["scope_enum"]:
            raise error_cls("hybrid_invalid_scope", f"`scope` must be one of {', '.join(contract['scope_enum'])}.")
        normalized["scope"] = scope
        return normalized

    if flow_name in {"pr-summary", "changelog-summary"}:
        title = payload["title"]
        if not isinstance(title, str) or not title.strip():
            raise error_cls("hybrid_invalid_title", "`title` must be a non-empty string.")
        normalized["title"] = " ".join(title.split())[:120]
        list_key = "highlights" if flow_name == "pr-summary" else "entries"
        normalized[list_key] = normalize_string_list(payload[list_key], list_key)
        if flow_name == "pr-summary":
            summary = payload["summary"]
            if not isinstance(summary, str) or not summary.strip():
                raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
            normalized["summary"] = " ".join(summary.split())[:500]
        return normalized

    if flow_name == "validation-summary":
        overall = payload["overall"]
        if overall not in contract["overall_enum"]:
            raise error_cls("hybrid_invalid_overall", f"`overall` must be one of {', '.join(contract['overall_enum'])}.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["overall"] = overall
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["highlights"] = normalize_string_list(payload["highlights"], "highlights")
        normalized["commands"] = normalize_string_list(payload["commands"], "commands")
        return normalized

    if flow_name == "triage":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise error_cls("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        classification = payload["classification"]
        if classification not in contract["classification_enum"]:
            raise error_cls(
                "hybrid_invalid_classification",
                f"`classification` must be one of {', '.join(contract['classification_enum'])}.",
            )
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["target_ref"] = target_ref
        normalized["classification"] = classification
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["next_actions"] = normalize_string_list(payload["next_actions"], "next_actions")
        return normalized

    if flow_name == "handoff-packet":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise error_cls("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        normalized["target_ref"] = target_ref
        for key in ("goal", "why_now"):
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise error_cls("hybrid_invalid_field", f"`{key}` must be a non-empty string.")
            normalized[key] = " ".join(value.split())[:400]
        normalized["files_of_interest"] = normalize_string_list(payload["files_of_interest"], "files_of_interest")
        normalized["validation_targets"] = normalize_string_list(payload["validation_targets"], "validation_targets")
        normalized["risks"] = normalize_string_list(payload["risks"], "risks")
        return normalized

    if flow_name == "suggest-split":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise error_cls("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["target_ref"] = target_ref
        normalized["suggested_titles"] = normalize_string_list(payload["suggested_titles"], "suggested_titles")
        normalized["summary"] = " ".join(summary.split())[:500]
        return normalized

    if flow_name in {"diff-risk", "windows-compat-risk"}:
        risk = payload["risk"]
        if risk not in contract["risk_enum"]:
            raise error_cls("hybrid_invalid_risk", f"`risk` must be one of {', '.join(contract['risk_enum'])}.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["risk"] = risk
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["drivers"] = normalize_string_list(payload["drivers"], "drivers")
        return normalized

    if flow_name == "commit-plan":
        strategy = payload["strategy"]
        if strategy not in contract["strategy_enum"]:
            raise error_cls(
                "hybrid_invalid_strategy",
                f"`strategy` must be one of {', '.join(contract['strategy_enum'])}.",
            )
        steps = payload["steps"]
        if not isinstance(steps, list) or not steps:
            raise error_cls("hybrid_invalid_steps", "`steps` must be a non-empty array.")
        normalized_steps = []
        for step in steps:
            if not isinstance(step, dict):
                raise error_cls("hybrid_invalid_steps", "Each commit-plan step must be a JSON object.")
            scope = step.get("scope")
            summary = step.get("summary")
            paths = step.get("paths")
            if scope not in {"root", "submodule"}:
                raise error_cls("hybrid_invalid_steps", "Each commit-plan step requires scope=root|submodule.")
            if not isinstance(summary, str) or not summary.strip():
                raise error_cls("hybrid_invalid_steps", "Each commit-plan step requires a non-empty summary.")
            normalized_steps.append(
                {
                    "scope": scope,
                    "summary": " ".join(summary.split())[:240],
                    "paths": normalize_string_list(paths, "paths"),
                }
            )
        normalized["strategy"] = strategy
        normalized["steps"] = normalized_steps
        return normalized

    if flow_name == "closure-summary":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise error_cls("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["target_ref"] = target_ref
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["delivered"] = normalize_string_list(payload["delivered"], "delivered")
        normalized["validations"] = normalize_string_list(payload["validations"], "validations")
        normalized["remaining_risks"] = normalize_string_list(payload["remaining_risks"], "remaining_risks")
        return normalized

    if flow_name in {"validation-checklist", "review-checklist"}:
        profile = payload["profile"]
        if not isinstance(profile, str) or not profile.strip():
            raise error_cls("hybrid_invalid_profile", "`profile` must be a non-empty string.")
        normalized["profile"] = " ".join(profile.split())[:120]
        normalized["checks"] = normalize_string_list(payload["checks"], "checks")
        return normalized

    if flow_name == "doc-consistency":
        overall = payload["overall"]
        if overall not in contract["overall_enum"]:
            raise error_cls("hybrid_invalid_overall", f"`overall` must be one of {', '.join(contract['overall_enum'])}.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["overall"] = overall
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["issues"] = normalize_string_list(payload["issues"], "issues")
        normalized["follow_up"] = normalize_string_list(payload["follow_up"], "follow_up")
        return normalized

    if flow_name == "changed-surface-summary":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["changed_paths"] = normalize_string_list(payload["changed_paths"], "changed_paths")
        normalized["categories"] = normalize_string_list(payload["categories"], "categories")
        return normalized

    if flow_name == "release-changelog-status":
        for key in ("tag", "version", "relative_path", "summary"):
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise error_cls("hybrid_invalid_field", f"`{key}` must be a non-empty string.")
            normalized[key] = " ".join(value.split())[:240]
        exists = payload["exists"]
        if not isinstance(exists, bool):
            raise error_cls("hybrid_invalid_field", "`exists` must be a boolean.")
        normalized["exists"] = exists
        return normalized

    if flow_name == "test-impact-summary":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["commands"] = normalize_string_list(payload["commands"], "commands")
        normalized["targeted_tests"] = normalize_string_list(payload["targeted_tests"], "targeted_tests")
        return normalized

    if flow_name == "hybrid-insights-explainer":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise error_cls("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["strengths"] = normalize_string_list(payload["strengths"], "strengths")
        normalized["concerns"] = normalize_string_list(payload["concerns"], "concerns")
        normalized["next_actions"] = normalize_string_list(payload["next_actions"], "next_actions")
        return normalized

    if flow_name == "doc-link-suggestion":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise error_cls("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        normalized["target_ref"] = target_ref
        normalized["missing_links"] = normalize_string_list(payload["missing_links"], "missing_links")
        normalized["suggested_follow_up"] = normalize_string_list(payload["suggested_follow_up"], "suggested_follow_up")
        return normalized

    raise error_cls("hybrid_unhandled_flow", f"Unhandled hybrid assist flow `{flow_name}`.")
