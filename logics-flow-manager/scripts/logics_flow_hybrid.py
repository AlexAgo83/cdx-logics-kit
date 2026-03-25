#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from logics_flow_dispatcher import (
    ALLOWED_DISPATCH_ACTIONS,
    SAFE_SYNC_KINDS,
    DispatcherDecision,
    extract_json_object,
    validate_dispatcher_decision,
)
from logics_flow_models import WorkflowDocModel


HYBRID_ASSIST_SCHEMA_VERSION = "1.0"
DEFAULT_HYBRID_BACKEND = "auto"
DEFAULT_HYBRID_MODEL_PROFILE = "deepseek-coder"
DEFAULT_HYBRID_MODEL = "deepseek-coder-v2:16b"
DEFAULT_HYBRID_HOST = "http://127.0.0.1:11434"
DEFAULT_HYBRID_TIMEOUT_SECONDS = 20.0
DEFAULT_HYBRID_AUDIT_LOG = "logics/hybrid_assist_audit.jsonl"
DEFAULT_HYBRID_MEASUREMENT_LOG = "logics/hybrid_assist_measurements.jsonl"
DEFAULT_HYBRID_MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "deepseek-coder": {
        "family": "deepseek",
        "model": "deepseek-coder-v2:16b",
        "description": "DeepSeek Coder V2 profile for shared local coding and hybrid assist work.",
        "example_tags": ["deepseek-coder-v2:16b", "deepseek-coder-v2:latest"],
    },
    "qwen-coder": {
        "family": "qwen",
        "model": "qwen2.5-coder:14b",
        "description": "Qwen coder profile for bounded local coding and hybrid assist work.",
        "example_tags": ["qwen2.5-coder:14b", "qwen2.5-coder:7b"],
    },
}

SAFETY_CLASS_PROPOSAL_ONLY = "proposal-only"
SAFETY_CLASS_DETERMINISTIC_RUNNER = "deterministic-runner"
SAFETY_CLASS_CODEX_ONLY = "codex-only"
SAFETY_CLASSES = (
    SAFETY_CLASS_PROPOSAL_ONLY,
    SAFETY_CLASS_DETERMINISTIC_RUNNER,
    SAFETY_CLASS_CODEX_ONLY,
)
BACKEND_CHOICES = ("auto", "ollama", "codex")
RESULT_STATUSES = ("ok", "degraded", "error")

FLOW_CONTRACTS: dict[str, dict[str, Any]] = {
    "commit-message": {
        "summary": "Generate a bounded commit message proposal from the current git diff.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("subject", "body", "scope", "confidence", "rationale"),
        "scope_enum": ("single", "root", "submodule"),
    },
    "pr-summary": {
        "summary": "Generate a compact PR summary from the current diff and workflow context.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("title", "summary", "highlights", "confidence", "rationale"),
    },
    "changelog-summary": {
        "summary": "Generate short changelog entries from the current diff and workflow context.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("title", "entries", "confidence", "rationale"),
    },
    "validation-summary": {
        "summary": "Summarize lint, audit, doctor, and optional command results into a bounded operator report.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("overall", "summary", "highlights", "commands", "confidence", "rationale"),
        "overall_enum": ("pass", "warning", "fail"),
    },
    "next-step": {
        "summary": "Choose the next bounded workflow action for a target request, backlog item, or task.",
        "safety_class": SAFETY_CLASS_DETERMINISTIC_RUNNER,
        "required_keys": ("action", "target_ref", "proposed_args", "rationale", "confidence"),
    },
    "triage": {
        "summary": "Classify the target workflow doc as ready, blocked, needing clarification, or needing split.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("target_ref", "classification", "summary", "next_actions", "confidence", "rationale"),
        "classification_enum": ("ready", "needs-clarification", "needs-split", "blocked"),
    },
    "handoff-packet": {
        "summary": "Prepare a compact handoff packet for Codex or Claude without mutating the repo.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": (
            "target_ref",
            "goal",
            "why_now",
            "files_of_interest",
            "validation_targets",
            "risks",
            "confidence",
            "rationale",
        ),
    },
    "suggest-split": {
        "summary": "Suggest a bounded split proposal for a broad request or backlog item.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("target_ref", "suggested_titles", "summary", "confidence", "rationale"),
    },
    "diff-risk": {
        "summary": "Classify the risk level of the current diff.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("risk", "summary", "drivers", "confidence", "rationale"),
        "risk_enum": ("low", "medium", "high"),
    },
    "commit-plan": {
        "summary": "Suggest the minimal coherent git commit plan for the current diff.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("strategy", "steps", "confidence", "rationale"),
        "strategy_enum": ("single", "submodule-then-root", "multi"),
    },
    "closure-summary": {
        "summary": "Summarize what was delivered for a target request, backlog item, or task.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("target_ref", "summary", "delivered", "validations", "remaining_risks", "confidence", "rationale"),
    },
    "validation-checklist": {
        "summary": "Produce a bounded checklist of recommended validations for the current change surface.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("profile", "checks", "confidence", "rationale"),
    },
    "doc-consistency": {
        "summary": "Review workflow docs for consistency issues without mutating them.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("overall", "summary", "issues", "follow_up", "confidence", "rationale"),
        "overall_enum": ("clean", "issues-found"),
    },
}

FLOW_CONTEXT_PROFILES: dict[str, dict[str, Any]] = {
    "commit-message": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "pr-summary": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
    "changelog-summary": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "validation-summary": {"mode": "summary-only", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": True},
    "next-step": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": True, "include_doctor": True},
    "triage": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
    "handoff-packet": {"mode": "diff-first", "profile": "deep", "include_graph": True, "include_registry": True, "include_doctor": True},
    "suggest-split": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
    "diff-risk": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "commit-plan": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "closure-summary": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
    "validation-checklist": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": True, "include_doctor": True},
    "doc-consistency": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": True},
}


class HybridAssistError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class HybridBackendStatus:
    requested_backend: str
    selected_backend: str
    host: str
    model_profile: str
    model_family: str
    configured_model: str
    model: str
    ollama_reachable: bool
    model_available: bool
    healthy: bool
    reasons: list[str]
    response_time_ms: float | None
    version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "selected_backend": self.selected_backend,
            "host": self.host,
            "model_profile": self.model_profile,
            "model_family": self.model_family,
            "configured_model": self.configured_model,
            "model": self.model,
            "ollama_reachable": self.ollama_reachable,
            "model_available": self.model_available,
            "healthy": self.healthy,
            "reasons": self.reasons,
            "response_time_ms": self.response_time_ms,
            "version": self.version,
        }


def default_context_spec(flow_name: str) -> dict[str, Any]:
    if flow_name not in FLOW_CONTEXT_PROFILES:
        raise HybridAssistError("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    return dict(FLOW_CONTEXT_PROFILES[flow_name])


def default_hybrid_model_profiles() -> dict[str, dict[str, Any]]:
    return deepcopy(DEFAULT_HYBRID_MODEL_PROFILES)


def infer_model_family(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("deepseek"):
        return "deepseek"
    if normalized.startswith("qwen"):
        return "qwen"
    return "custom"


def merge_hybrid_model_profiles(overrides: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    profiles = default_hybrid_model_profiles()
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


def apply_legacy_default_model(
    profiles: dict[str, dict[str, Any]],
    *,
    default_profile: str,
    legacy_default_model: str | None,
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


def resolve_hybrid_model_selection(
    *,
    configured_profiles: dict[str, dict[str, Any]],
    default_profile: str,
    requested_profile: str | None = None,
    requested_model: str | None = None,
) -> dict[str, Any]:
    profile_name = (requested_profile or default_profile).strip()
    if profile_name not in configured_profiles:
        raise HybridAssistError(
            "hybrid_unknown_model_profile",
            f"Unknown hybrid model profile `{profile_name}`.",
            details={"known_profiles": sorted(configured_profiles.keys())},
        )
    spec = deepcopy(configured_profiles[profile_name])
    configured_model = str(spec.get("model", "")).strip()
    if not configured_model:
        raise HybridAssistError(
            "hybrid_invalid_model_profile",
            f"Hybrid model profile `{profile_name}` is missing a configured model tag.",
        )
    resolved_model = (requested_model or configured_model).strip()
    if not resolved_model:
        raise HybridAssistError("hybrid_invalid_model", "Hybrid model selection resolved to an empty model tag.")
    family = str(spec.get("family") or infer_model_family(resolved_model)).strip() or infer_model_family(resolved_model)
    return {
        "name": profile_name,
        "family": family,
        "configured_model": configured_model,
        "resolved_model": resolved_model,
        "description": str(spec.get("description", "")).strip(),
        "example_tags": [str(tag).strip() for tag in spec.get("example_tags", []) if str(tag).strip()],
    }


def build_shared_hybrid_contract() -> dict[str, Any]:
    return {
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "backends": list(BACKEND_CHOICES),
        "safety_classes": list(SAFETY_CLASSES),
        "result_statuses": list(RESULT_STATUSES),
        "model_profiles": default_hybrid_model_profiles(),
        "flows": {
            flow: {
                "summary": contract["summary"],
                "safety_class": contract["safety_class"],
                "required_keys": list(contract["required_keys"]),
            }
            for flow, contract in sorted(FLOW_CONTRACTS.items())
        },
    }


def build_flow_contract(flow_name: str) -> dict[str, Any]:
    contract = FLOW_CONTRACTS.get(flow_name)
    if contract is None:
        raise HybridAssistError("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    payload = {
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "flow": flow_name,
        "summary": contract["summary"],
        "safety_class": contract["safety_class"],
        "required_keys": list(contract["required_keys"]),
    }
    for key in ("scope_enum", "overall_enum", "classification_enum", "risk_enum", "strategy_enum"):
        if key in contract:
            payload[key] = list(contract[key])
    if flow_name == "next-step":
        payload["allowed_actions"] = list(ALLOWED_DISPATCH_ACTIONS)
        payload["safe_sync_kinds"] = list(SAFE_SYNC_KINDS)
    return payload


def _json_request(host: str, path: str, *, payload: dict[str, Any] | None = None, timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(
        f"{host.rstrip('/')}{path}",
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_ollama_backend(
    *,
    requested_backend: str,
    host: str = DEFAULT_HYBRID_HOST,
    model_profile: str = DEFAULT_HYBRID_MODEL_PROFILE,
    model_family: str = "deepseek",
    configured_model: str = DEFAULT_HYBRID_MODEL,
    model: str = DEFAULT_HYBRID_MODEL,
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> HybridBackendStatus:
    normalized_host = host.strip() or os.environ.get("OLLAMA_HOST", DEFAULT_HYBRID_HOST)
    if not normalized_host.startswith(("http://", "https://")):
        normalized_host = f"http://{normalized_host}"
    normalized_host = normalized_host.rstrip("/")
    reasons: list[str] = []
    version: str | None = None
    response_time_ms: float | None = None
    reachable = False
    model_available = False

    try:
        started = datetime.now(timezone.utc)
        version_payload = _json_request(normalized_host, "/api/version", timeout_seconds=timeout_seconds)
        elapsed = datetime.now(timezone.utc) - started
        response_time_ms = round(elapsed.total_seconds() * 1000, 3)
        version = str(version_payload.get("version", "")) or None
        reachable = True
        tags_payload = _json_request(normalized_host, "/api/tags", timeout_seconds=timeout_seconds)
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

    selected_backend = requested_backend
    if requested_backend == "auto":
        selected_backend = "ollama" if reachable and model_available else "codex"
    elif requested_backend == "ollama" and not (reachable and model_available):
        raise HybridAssistError(
            "hybrid_ollama_unavailable",
            f"Ollama backend was requested explicitly but `{model}` is not healthy at {normalized_host}.",
            details={"host": normalized_host, "model": model, "reasons": reasons},
        )

    healthy = reachable and model_available
    if selected_backend == "codex" and requested_backend == "auto" and not reasons:
        reasons.append("ollama-not-selected")
    return HybridBackendStatus(
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
        reasons=reasons,
        response_time_ms=response_time_ms,
        version=version,
    )


def build_hybrid_messages(flow_name: str, context_bundle: dict[str, Any]) -> list[dict[str, str]]:
    contract = context_bundle["contract"]
    system = (
        "You are a bounded hybrid delivery assistant for the Logics workflow. "
        "Reply with one JSON object only. "
        "Do not use markdown fences. "
        "Stay within the supplied contract. "
        "Prefer conservative short outputs over speculative ones."
    )
    user = (
        "Return a JSON object matching this contract exactly.\n\n"
        f"Hybrid contract:\n{json.dumps(contract, indent=2, sort_keys=True)}\n\n"
        f"Context bundle:\n{json.dumps(context_bundle, indent=2, sort_keys=True)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_ollama_hybrid(
    *,
    host: str,
    model: str,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    messages = build_hybrid_messages(flow_name, context_bundle)
    request_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        response_payload = _json_request(host, "/api/chat", payload=request_payload, timeout_seconds=timeout_seconds)
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HybridAssistError(
            "hybrid_ollama_http_error",
            f"Ollama returned HTTP {exc.code}: {body or exc.reason}",
            details={"host": host, "model": model, "flow": flow_name},
        ) from exc
    except urllib_error.URLError as exc:
        raise HybridAssistError(
            "hybrid_ollama_unreachable",
            f"Could not reach Ollama at {host}: {exc.reason}",
            details={"host": host, "model": model, "flow": flow_name},
        ) from exc

    content = ""
    if isinstance(response_payload, dict):
        message = response_payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
    if not content:
        raise HybridAssistError(
            "hybrid_ollama_empty_response",
            "Ollama returned an empty hybrid assist response.",
            details={"host": host, "model": model, "flow": flow_name},
        )
    return {
        "transport": "ollama",
        "host": host,
        "model": model,
        "messages": messages,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "raw_content": content,
        "result_payload": extract_json_object(content),
    }


def _normalize_confidence(raw_value: Any) -> float:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise HybridAssistError("hybrid_invalid_confidence", "Confidence must be numeric.")
    value = float(raw_value)
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    if value < 0.0 or value > 1.0:
        raise HybridAssistError("hybrid_invalid_confidence", "Confidence must be between 0.0 and 1.0.")
    return round(value, 4)


def _normalize_string_list(value: Any, key: str, *, min_items: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise HybridAssistError("hybrid_invalid_list", f"`{key}` must be an array of strings.")
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HybridAssistError("hybrid_invalid_list", f"`{key}` must contain only non-empty strings.")
        normalized.append(" ".join(item.split()))
    if len(normalized) < min_items:
        raise HybridAssistError("hybrid_invalid_list", f"`{key}` must contain at least {min_items} item(s).")
    return normalized


def validate_hybrid_result(flow_name: str, payload: dict[str, Any], docs_by_ref: dict[str, WorkflowDocModel]) -> dict[str, Any]:
    contract = FLOW_CONTRACTS.get(flow_name)
    if contract is None:
        raise HybridAssistError("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    required = set(contract["required_keys"])
    missing = sorted(required - set(payload))
    if missing:
        raise HybridAssistError(
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
    normalized["confidence"] = _normalize_confidence(payload["confidence"])
    rationale = payload["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise HybridAssistError("hybrid_invalid_rationale", "`rationale` must be a non-empty string.")
    normalized["rationale"] = " ".join(rationale.split())[:500]

    if flow_name == "commit-message":
        subject = payload["subject"]
        if not isinstance(subject, str) or not subject.strip():
            raise HybridAssistError("hybrid_invalid_subject", "`subject` must be a non-empty string.")
        normalized["subject"] = " ".join(subject.split())[:72]
        body = payload["body"]
        if not isinstance(body, str):
            raise HybridAssistError("hybrid_invalid_body", "`body` must be a string.")
        normalized["body"] = body.strip()[:400]
        scope = payload["scope"]
        if scope not in contract["scope_enum"]:
            raise HybridAssistError("hybrid_invalid_scope", f"`scope` must be one of {', '.join(contract['scope_enum'])}.")
        normalized["scope"] = scope
        return normalized

    if flow_name in {"pr-summary", "changelog-summary"}:
        title = payload["title"]
        if not isinstance(title, str) or not title.strip():
            raise HybridAssistError("hybrid_invalid_title", "`title` must be a non-empty string.")
        normalized["title"] = " ".join(title.split())[:120]
        list_key = "highlights" if flow_name == "pr-summary" else "entries"
        normalized[list_key] = _normalize_string_list(payload[list_key], list_key)
        summary_key = "summary"
        if flow_name == "pr-summary":
            summary = payload["summary"]
            if not isinstance(summary, str) or not summary.strip():
                raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
            normalized[summary_key] = " ".join(summary.split())[:500]
        return normalized

    if flow_name == "validation-summary":
        overall = payload["overall"]
        if overall not in contract["overall_enum"]:
            raise HybridAssistError("hybrid_invalid_overall", f"`overall` must be one of {', '.join(contract['overall_enum'])}.")
        normalized["overall"] = overall
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["highlights"] = _normalize_string_list(payload["highlights"], "highlights")
        normalized["commands"] = _normalize_string_list(payload["commands"], "commands")
        return normalized

    if flow_name == "triage":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise HybridAssistError("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        classification = payload["classification"]
        if classification not in contract["classification_enum"]:
            raise HybridAssistError(
                "hybrid_invalid_classification",
                f"`classification` must be one of {', '.join(contract['classification_enum'])}.",
            )
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["target_ref"] = target_ref
        normalized["classification"] = classification
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["next_actions"] = _normalize_string_list(payload["next_actions"], "next_actions")
        return normalized

    if flow_name == "handoff-packet":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise HybridAssistError("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        normalized["target_ref"] = target_ref
        for key in ("goal", "why_now"):
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise HybridAssistError("hybrid_invalid_field", f"`{key}` must be a non-empty string.")
            normalized[key] = " ".join(value.split())[:400]
        normalized["files_of_interest"] = _normalize_string_list(payload["files_of_interest"], "files_of_interest")
        normalized["validation_targets"] = _normalize_string_list(payload["validation_targets"], "validation_targets")
        normalized["risks"] = _normalize_string_list(payload["risks"], "risks")
        return normalized

    if flow_name == "suggest-split":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise HybridAssistError("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        normalized["target_ref"] = target_ref
        normalized["suggested_titles"] = _normalize_string_list(payload["suggested_titles"], "suggested_titles")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        return normalized

    if flow_name == "diff-risk":
        risk = payload["risk"]
        if risk not in contract["risk_enum"]:
            raise HybridAssistError("hybrid_invalid_risk", f"`risk` must be one of {', '.join(contract['risk_enum'])}.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["risk"] = risk
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["drivers"] = _normalize_string_list(payload["drivers"], "drivers")
        return normalized

    if flow_name == "commit-plan":
        strategy = payload["strategy"]
        if strategy not in contract["strategy_enum"]:
            raise HybridAssistError(
                "hybrid_invalid_strategy",
                f"`strategy` must be one of {', '.join(contract['strategy_enum'])}.",
            )
        steps = payload["steps"]
        if not isinstance(steps, list) or not steps:
            raise HybridAssistError("hybrid_invalid_steps", "`steps` must be a non-empty array.")
        normalized_steps = []
        for step in steps:
            if not isinstance(step, dict):
                raise HybridAssistError("hybrid_invalid_steps", "Each commit-plan step must be a JSON object.")
            scope = step.get("scope")
            summary = step.get("summary")
            paths = step.get("paths")
            if scope not in {"root", "submodule"}:
                raise HybridAssistError("hybrid_invalid_steps", "Each commit-plan step requires scope=root|submodule.")
            if not isinstance(summary, str) or not summary.strip():
                raise HybridAssistError("hybrid_invalid_steps", "Each commit-plan step requires a non-empty summary.")
            normalized_steps.append(
                {
                    "scope": scope,
                    "summary": " ".join(summary.split())[:240],
                    "paths": _normalize_string_list(paths, "paths"),
                }
            )
        normalized["strategy"] = strategy
        normalized["steps"] = normalized_steps
        return normalized

    if flow_name == "closure-summary":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise HybridAssistError("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["target_ref"] = target_ref
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["delivered"] = _normalize_string_list(payload["delivered"], "delivered")
        normalized["validations"] = _normalize_string_list(payload["validations"], "validations")
        normalized["remaining_risks"] = _normalize_string_list(payload["remaining_risks"], "remaining_risks")
        return normalized

    if flow_name == "validation-checklist":
        profile = payload["profile"]
        if not isinstance(profile, str) or not profile.strip():
            raise HybridAssistError("hybrid_invalid_profile", "`profile` must be a non-empty string.")
        normalized["profile"] = " ".join(profile.split())[:120]
        normalized["checks"] = _normalize_string_list(payload["checks"], "checks")
        return normalized

    if flow_name == "doc-consistency":
        overall = payload["overall"]
        if overall not in contract["overall_enum"]:
            raise HybridAssistError("hybrid_invalid_overall", f"`overall` must be one of {', '.join(contract['overall_enum'])}.")
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["overall"] = overall
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["issues"] = _normalize_string_list(payload["issues"], "issues")
        normalized["follow_up"] = _normalize_string_list(payload["follow_up"], "follow_up")
        return normalized

    raise HybridAssistError("hybrid_unhandled_flow", f"Unhandled hybrid assist flow `{flow_name}`.")


def append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _git(repo_root: Path, *argv: str) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", *argv],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def collect_git_snapshot(repo_root: Path) -> dict[str, Any]:
    status_code, status_out, _status_err = _git(repo_root, "status", "--short")
    diff_code, diff_out, _diff_err = _git(repo_root, "diff", "--stat")
    staged_code, staged_out, _staged_err = _git(repo_root, "diff", "--cached", "--stat")
    changed_paths = []
    if status_code == 0:
        for raw in status_out.splitlines():
            if len(raw) < 4:
                continue
            path_text = raw[3:].strip()
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[1].strip()
            if path_text:
                changed_paths.append(path_text)
    return {
        "git_available": status_code == 0,
        "changed_paths": changed_paths,
        "unstaged_diff_stat": [line for line in diff_out.splitlines() if line.strip()] if diff_code == 0 else [],
        "staged_diff_stat": [line for line in staged_out.splitlines() if line.strip()] if staged_code == 0 else [],
        "has_changes": bool(changed_paths),
        "doc_only": bool(changed_paths) and all(path.startswith("logics/") or path.endswith(".md") for path in changed_paths),
        "touches_plugin": any(path.startswith("src/") or path.startswith("media/") or path == "README.md" for path in changed_paths),
        "touches_runtime": any(path.startswith("logics/skills/") or path == "logics.yaml" for path in changed_paths),
        "touches_tests": any(path.startswith("tests/") or "/tests/" in path for path in changed_paths),
        "touches_submodule": any(path == "logics/skills" or path.startswith("logics/skills/") for path in changed_paths),
    }


def build_runtime_status(
    *,
    repo_root: Path,
    requested_backend: str,
    host: str,
    model_profile: dict[str, Any],
    supported_model_profiles: dict[str, dict[str, Any]],
    model: str,
    timeout_seconds: float,
    claude_bridge_available: bool,
) -> dict[str, Any]:
    backend = probe_ollama_backend(
        requested_backend=requested_backend,
        host=host,
        model_profile=str(model_profile["name"]),
        model_family=str(model_profile["family"]),
        configured_model=str(model_profile["configured_model"]),
        model=model,
        timeout_seconds=timeout_seconds,
    )
    degraded_reasons = list(backend.reasons)
    if not claude_bridge_available:
        degraded_reasons.append("claude-bridge-missing")
    return {
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "backend": backend.to_dict(),
        "active_model_profile": {
            "name": model_profile["name"],
            "family": model_profile["family"],
            "configured_model": model_profile["configured_model"],
            "resolved_model": model_profile["resolved_model"],
            "description": model_profile["description"],
            "example_tags": model_profile["example_tags"],
        },
        "supported_model_profiles": supported_model_profiles,
        "claude_bridge_available": claude_bridge_available,
        "windows_safe_entrypoint": "python logics/skills/logics.py flow assist ...",
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


def build_hybrid_audit_record(
    *,
    flow_name: str,
    result_status: str,
    backend_status: HybridBackendStatus,
    context_bundle: dict[str, Any],
    raw_payload: dict[str, Any] | None,
    validated_payload: dict[str, Any],
    transport: dict[str, Any],
    degraded_reasons: list[str],
    execution_result: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "flow": flow_name,
        "result_status": result_status,
        "backend": backend_status.to_dict(),
        "safety_class": context_bundle["contract"]["safety_class"],
        "context_summary": {
            "seed_ref": context_bundle.get("seed_ref"),
            "context_profile": context_bundle.get("context_profile"),
            "mode": context_bundle.get("context_pack", {}).get("mode"),
            "profile": context_bundle.get("context_pack", {}).get("profile"),
            "doc_count": context_bundle.get("context_pack", {}).get("estimates", {}).get("doc_count"),
            "changed_paths": len(context_bundle.get("git_snapshot", {}).get("changed_paths", [])),
        },
        "raw_payload": raw_payload,
        "validated_payload": validated_payload,
        "transport": transport,
        "degraded_reasons": degraded_reasons,
        "execution_result": execution_result,
    }


def build_measurement_record(
    *,
    flow_name: str,
    backend_status: HybridBackendStatus,
    result_status: str,
    confidence: float | None,
    degraded_reasons: list[str],
    review_recommended: bool,
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "flow": flow_name,
        "backend_requested": backend_status.requested_backend,
        "backend_used": backend_status.selected_backend,
        "result_status": result_status,
        "confidence": confidence,
        "degraded_reasons": degraded_reasons,
        "review_recommended": review_recommended,
    }


def _count_section_bullets(doc: WorkflowDocModel, heading: str) -> int:
    return len([line for line in doc.sections.get(heading, []) if line.strip().startswith("- ")])


def _section_bullets(doc: WorkflowDocModel, heading: str) -> list[str]:
    return [line.strip()[2:].strip() for line in doc.sections.get(heading, []) if line.strip().startswith("- ")]


def _fallback_next_step(seed_ref: str, docs_by_ref: dict[str, WorkflowDocModel]) -> DispatcherDecision:
    doc = docs_by_ref[seed_ref]
    status = doc.indicators.get("Status", "")
    if doc.kind == "request" and not doc.refs.get("item"):
        return DispatcherDecision(
            action="promote",
            target_ref=seed_ref,
            proposed_args={},
            rationale="The request has no linked backlog item yet and is ready for promotion.",
            confidence=0.82,
        )
    if doc.kind == "backlog" and not doc.refs.get("task"):
        return DispatcherDecision(
            action="promote",
            target_ref=seed_ref,
            proposed_args={},
            rationale="The backlog item has no linked task yet and should move to execution planning.",
            confidence=0.82,
        )
    if doc.kind == "task" and status == "Done":
        return DispatcherDecision(
            action="finish",
            target_ref=seed_ref,
            proposed_args={},
            rationale="The task already shows Done and is a candidate for guarded finish propagation.",
            confidence=0.8,
        )
    return DispatcherDecision(
        action="sync",
        target_ref=None,
        proposed_args={"sync_kind": "doctor"},
        rationale="The safest bounded next step is to refresh health signals before taking a write action.",
        confidence=0.65,
    )


def _summarize_changed_paths(context_bundle: dict[str, Any]) -> str:
    changed_paths = context_bundle.get("git_snapshot", {}).get("changed_paths", [])
    if not changed_paths:
        return "No working tree changes detected."
    if len(changed_paths) == 1:
        return f"Change touches `{changed_paths[0]}`."
    if len(changed_paths) <= 4:
        return "Changes touch " + ", ".join(f"`{path}`" for path in changed_paths[:4]) + "."
    return "Changes touch " + ", ".join(f"`{path}`" for path in changed_paths[:4]) + f", and {len(changed_paths) - 4} more path(s)."


def build_fallback_result(
    flow_name: str,
    *,
    context_bundle: dict[str, Any],
    docs_by_ref: dict[str, WorkflowDocModel],
    validation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_ref = context_bundle.get("seed_ref")
    git_snapshot = context_bundle.get("git_snapshot", {})
    changed_paths = list(git_snapshot.get("changed_paths", []))
    if flow_name == "commit-message":
        scope = "submodule" if changed_paths and all(path.startswith("logics/skills/") or path == "logics/skills" for path in changed_paths) else "root"
        subject = "Update Logics docs and runtime surfaces"
        if git_snapshot.get("touches_plugin") and git_snapshot.get("touches_runtime"):
            subject = "Add hybrid assist runtime and plugin surfaces"
        elif git_snapshot.get("touches_plugin"):
            subject = "Update plugin hybrid assist surfaces"
        elif git_snapshot.get("touches_runtime"):
            subject = "Add hybrid assist runtime flows"
        elif git_snapshot.get("doc_only"):
            subject = "Update Logics planning and workflow docs"
        return {
            "subject": subject[:72],
            "body": _summarize_changed_paths(context_bundle),
            "scope": scope,
            "confidence": 0.64,
            "rationale": "Fallback commit message derived from changed-path categories.",
        }
    if flow_name == "pr-summary":
        return {
            "title": "Hybrid assist runtime and delivery automation updates",
            "summary": _summarize_changed_paths(context_bundle),
            "highlights": [
                "Adds shared hybrid runtime contracts and backend selection.",
                "Keeps risky execution outside raw model output.",
                "Updates delivery tooling and workflow surfaces around the new runtime.",
            ],
            "confidence": 0.62,
            "rationale": "Fallback PR summary derived from change categories.",
        }
    if flow_name == "changelog-summary":
        entries = ["Add hybrid assist runtime contracts and backend selection."]
        if git_snapshot.get("touches_plugin"):
            entries.append("Expose hybrid assist health and action surfaces in the VS Code plugin.")
        if git_snapshot.get("touches_runtime"):
            entries.append("Add bounded hybrid assist flows for delivery summaries, triage, and planning.")
        return {
            "title": "Hybrid assist delivery updates",
            "entries": entries,
            "confidence": 0.62,
            "rationale": "Fallback changelog summary derived from changed surfaces.",
        }
    if flow_name == "validation-summary":
        if validation_payload is None:
            validation_payload = {}
        statuses = validation_payload.get("statuses", [])
        overall = "pass" if statuses and all(item["ok"] for item in statuses) else "warning"
        if statuses and any(not item["ok"] for item in statuses):
            overall = "fail"
        return {
            "overall": overall,
            "summary": "Validation summary derived from the shared hybrid validation run.",
            "highlights": [item["summary"] for item in statuses] if statuses else ["No validation commands were executed."],
            "commands": [item["command"] for item in statuses] if statuses else [],
            "confidence": 0.7 if statuses else 0.45,
            "rationale": "Fallback validation summary reuses structured command results.",
        }
    if flow_name == "next-step":
        return _fallback_next_step(str(seed_ref), docs_by_ref).to_dict()
    if flow_name == "triage":
        doc = docs_by_ref[str(seed_ref)]
        acceptance_count = _count_section_bullets(doc, "Acceptance criteria")
        needs_count = _count_section_bullets(doc, "Needs")
        if not acceptance_count and doc.kind != "task":
            classification = "needs-clarification"
            summary = "The doc is still missing acceptance criteria."
        elif doc.kind in {"request", "backlog"} and max(acceptance_count, needs_count) > 3:
            classification = "needs-split"
            summary = "The scope looks broad enough to justify a bounded split review."
        elif doc.indicators.get("Status") == "Blocked":
            classification = "blocked"
            summary = "The target doc is explicitly marked blocked."
        else:
            classification = "ready"
            summary = "The target doc looks ready for the next bounded workflow step."
        return {
            "target_ref": doc.ref,
            "classification": classification,
            "summary": summary,
            "next_actions": ["Review the suggested next-step flow.", "Confirm the target status and linked refs."],
            "confidence": 0.68,
            "rationale": "Fallback triage is based on status, acceptance-criteria presence, and scope size.",
        }
    if flow_name == "handoff-packet":
        doc = docs_by_ref[str(seed_ref)]
        files = [doc.path, *changed_paths[:5]]
        validations = [
            "python logics/skills/logics.py lint",
            "python logics/skills/logics.py audit --group-by-doc",
        ]
        return {
            "target_ref": doc.ref,
            "goal": f"Move `{doc.ref}` forward without losing workflow traceability.",
            "why_now": "The hybrid runtime needs a compact operator handoff packet.",
            "files_of_interest": list(dict.fromkeys(files)),
            "validation_targets": validations,
            "risks": ["Do not bypass the shared safety taxonomy.", "Keep workflow docs and runtime surfaces aligned."],
            "confidence": 0.63,
            "rationale": "Fallback handoff packet combines workflow target context with current changed paths.",
        }
    if flow_name == "suggest-split":
        doc = docs_by_ref[str(seed_ref)]
        source_bullets = _section_bullets(doc, "Acceptance criteria") or _section_bullets(doc, "Needs")
        titles = [bullet[:80] for bullet in source_bullets[:2] if bullet]
        if len(titles) < 2:
            titles = [f"{doc.title} slice A", f"{doc.title} slice B"]
        return {
            "target_ref": doc.ref,
            "suggested_titles": titles,
            "summary": "Fallback split suggestion keeps the source at the minimum coherent slice count.",
            "confidence": 0.61,
            "rationale": "Fallback split suggestion is derived from acceptance-criteria or needs bullets.",
        }
    if flow_name == "diff-risk":
        risk = "low"
        drivers: list[str] = []
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            risk = "high"
            drivers.append("Diff spans both runtime scripts and plugin surfaces.")
        elif git_snapshot.get("touches_runtime") or git_snapshot.get("touches_plugin"):
            risk = "medium"
            drivers.append("Diff touches execution or UI surfaces beyond docs only.")
        else:
            drivers.append("Diff is mostly limited to docs and light metadata.")
        if git_snapshot.get("touches_tests"):
            drivers.append("Tests are changing alongside implementation.")
        return {
            "risk": risk,
            "summary": "Fallback risk triage is based on changed-path categories.",
            "drivers": drivers,
            "confidence": 0.66,
            "rationale": "Fallback risk triage uses the shared git snapshot.",
        }
    if flow_name == "commit-plan":
        touches_submodule = git_snapshot.get("touches_submodule")
        root_paths = [path for path in changed_paths if not path.startswith("logics/skills/") and path != "logics/skills"]
        if touches_submodule and root_paths:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the kit/runtime changes inside logics/skills first.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Commit the parent repo updates and submodule pointer after the kit commit.", "paths": root_paths[:8] or ["logics/skills"]},
                ],
                "confidence": 0.86,
                "rationale": "Separate submodule and parent commits keep git history coherent.",
            }
        if touches_submodule:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the nested logics/skills changes.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Record the updated submodule pointer in the parent repo.", "paths": ["logics/skills"]},
                ],
                "confidence": 0.78,
                "rationale": "Submodule changes still require a parent pointer update.",
            }
        return {
            "strategy": "single",
            "steps": [{"scope": "root", "summary": "Commit all staged root-repo changes together.", "paths": changed_paths[:8] or ["."]}],
            "confidence": 0.74,
            "rationale": "No separate submodule step is required for the current diff.",
        }
    if flow_name == "closure-summary":
        doc = docs_by_ref[str(seed_ref)]
        linked = sorted({ref for refs in doc.refs.values() for ref in refs if ref in docs_by_ref})
        delivered = [doc.title, *[docs_by_ref[ref].title for ref in linked[:3]]]
        return {
            "target_ref": doc.ref,
            "summary": f"Fallback closure summary for `{doc.ref}` built from linked workflow docs and status metadata.",
            "delivered": delivered,
            "validations": ["python logics/skills/logics.py lint", "python logics/skills/logics.py audit --group-by-doc"],
            "remaining_risks": ["Confirm final validation results before closing delivery."],
            "confidence": 0.63,
            "rationale": "Fallback closure summary uses the workflow graph and standard validations.",
        }
    if flow_name == "validation-checklist":
        checks = ["python logics/skills/logics.py lint", "python logics/skills/logics.py audit --group-by-doc"]
        profile = "docs-only"
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            profile = "mixed"
            checks.extend(["python3 -m unittest discover -s logics/skills/tests -p 'test_*.py' -v", "npm test"])
        elif git_snapshot.get("touches_runtime"):
            profile = "runtime"
            checks.append("python3 -m unittest discover -s logics/skills/tests -p 'test_*.py' -v")
        elif git_snapshot.get("touches_plugin"):
            profile = "plugin"
            checks.extend(["npm test", "npm run test:smoke"])
        return {
            "profile": profile,
            "checks": checks,
            "confidence": 0.78,
            "rationale": "Fallback validation checklist is derived from the changed-path categories.",
        }
    if flow_name == "doc-consistency":
        issues = []
        follow_up = []
        statuses = validation_payload.get("statuses", []) if validation_payload else []
        for item in statuses:
            if not item["ok"]:
                issues.append(item["summary"])
                follow_up.append(f"Re-run or repair `{item['command']}`.")
        overall = "clean" if not issues else "issues-found"
        if not issues:
            issues = ["No consistency issues were detected by the fallback review."]
            follow_up = ["Keep the workflow audit and lint surfaces green."]
        return {
            "overall": overall,
            "summary": "Fallback doc-consistency review is based on workflow audit and lint results.",
            "issues": issues,
            "follow_up": follow_up,
            "confidence": 0.72 if statuses else 0.45,
            "rationale": "Fallback doc consistency review reuses the shared validation results.",
        }
    raise HybridAssistError("hybrid_unhandled_flow", f"Unhandled hybrid assist flow `{flow_name}`.")


def execute_commit_step(repo_root: Path, message: str) -> dict[str, Any]:
    add = subprocess.run(["git", "add", "-A"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if add.returncode != 0:
        raise HybridAssistError("hybrid_git_add_failed", add.stderr.strip() or "git add failed", details={"repo_root": str(repo_root)})
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise HybridAssistError(
            "hybrid_git_commit_failed",
            commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
            details={"repo_root": str(repo_root), "message": message},
        )
    return {"stdout": commit.stdout.strip(), "stderr": commit.stderr.strip(), "message": message}


def run_validation_commands(
    repo_root: Path,
    commands: list[list[str]],
    *,
    command_labeler: Callable[[list[str]], str] | None = None,
) -> dict[str, Any]:
    statuses = []
    for argv in commands:
        label = command_labeler(argv) if command_labeler is not None else " ".join(argv)
        result = subprocess.run(
            argv,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        summary = result.stderr.strip() or result.stdout.strip() or ("ok" if result.returncode == 0 else "failed")
        statuses.append(
            {
                "command": label,
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "summary": summary.splitlines()[0][:240] if summary else "",
            }
        )
    return {"statuses": statuses}
