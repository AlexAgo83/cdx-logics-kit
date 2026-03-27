#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
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
DEFAULT_HYBRID_ROI_RECENT_LIMIT = 8
DEFAULT_HYBRID_ROI_WINDOW_DAYS = 14
DEFAULT_ESTIMATED_REMOTE_TOKENS_PER_LOCAL_RUN = 1200
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
REQUESTED_BACKEND_CHOICES = ("auto", "ollama", "codex")
SUPPORTED_BACKEND_NAMES = ("auto", "ollama", "codex", "deterministic")
RESULT_STATUSES = ("ok", "degraded", "error")
BACKEND_POLICY_OLLAMA_FIRST = "ollama-first"
BACKEND_POLICY_CODEX_ONLY = "codex-only"
BACKEND_POLICY_DETERMINISTIC = "deterministic"
BACKEND_POLICY_MODES = (
    BACKEND_POLICY_OLLAMA_FIRST,
    BACKEND_POLICY_CODEX_ONLY,
    BACKEND_POLICY_DETERMINISTIC,
)

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
    "changed-surface-summary": {
        "summary": "Summarize the current changed surface deterministically from git and repository signals.",
        "safety_class": SAFETY_CLASS_DETERMINISTIC_RUNNER,
        "required_keys": ("summary", "changed_paths", "categories", "confidence", "rationale"),
    },
    "release-changelog-status": {
        "summary": "Resolve the current curated release changelog contract deterministically from package.json and changelog files.",
        "safety_class": SAFETY_CLASS_DETERMINISTIC_RUNNER,
        "required_keys": ("tag", "version", "relative_path", "exists", "summary", "confidence", "rationale"),
    },
    "test-impact-summary": {
        "summary": "Summarize deterministic validation impact from the current change surface.",
        "safety_class": SAFETY_CLASS_DETERMINISTIC_RUNNER,
        "required_keys": ("summary", "commands", "targeted_tests", "confidence", "rationale"),
    },
    "hybrid-insights-explainer": {
        "summary": "Explain the current Hybrid Insights report with bounded operator guidance.",
        "safety_class": SAFETY_CLASS_DETERMINISTIC_RUNNER,
        "required_keys": ("summary", "strengths", "concerns", "next_actions", "confidence", "rationale"),
    },
    "windows-compat-risk": {
        "summary": "Review the current change surface for Windows compatibility risk.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("risk", "summary", "drivers", "confidence", "rationale"),
        "risk_enum": ("low", "medium", "high"),
    },
    "review-checklist": {
        "summary": "Generate a bounded review checklist from the current change surface.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("profile", "checks", "confidence", "rationale"),
    },
    "doc-link-suggestion": {
        "summary": "Suggest missing workflow or companion-doc links for a target doc without mutating the repository.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("target_ref", "missing_links", "suggested_follow_up", "confidence", "rationale"),
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
    "changed-surface-summary": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "release-changelog-status": {"mode": "summary-only", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "test-impact-summary": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
    "hybrid-insights-explainer": {"mode": "summary-only", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
    "windows-compat-risk": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
    "review-checklist": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": True, "include_doctor": True},
    "doc-link-suggestion": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
}

FLOW_BACKEND_POLICIES: dict[str, dict[str, str]] = {
    "commit-message": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep commit-message local-first when Ollama is healthy; degrade to Codex only after health or payload validation failure.",
    },
    "pr-summary": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep PR summaries local-first because the flow is bounded and non-mutating.",
    },
    "changelog-summary": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep changelog summaries local-first because the flow is bounded and non-mutating.",
    },
    "validation-summary": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-against-shared-results-then-bounded-codex-fallback",
        "selection_summary": "Keep validation summaries local-first, but preserve stricter fallback because shared validation evidence must stay coherent.",
    },
    "next-step": {
        "mode": BACKEND_POLICY_CODEX_ONLY,
        "auto_backend": "codex",
        "fallback_policy": "policy-routed-to-codex-before-any-local-dispatch",
        "selection_summary": "Keep next-step Codex-only under auto because it feeds the deterministic dispatcher and should not broaden silently.",
    },
    "triage": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep triage local-first because it is bounded, proposal-only, and easy to review when degraded.",
    },
    "handoff-packet": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep handoff packets local-first because the output is advisory and stays within the shared contract.",
    },
    "suggest-split": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep split suggestions local-first because the output remains bounded and operator-reviewed.",
    },
    "diff-risk": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep diff-risk local-first because the risk report is bounded and non-mutating.",
    },
    "commit-plan": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep commit-plan local-first while preserving bounded fallback if local structure is weak.",
    },
    "closure-summary": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep closure summaries local-first because the output is advisory and easily reviewable.",
    },
    "validation-checklist": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-against-change-surface-then-bounded-codex-fallback",
        "selection_summary": "Keep validation checklists local-first, with stricter fallback because the checklist drives operator validation effort.",
    },
    "doc-consistency": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-against-workflow-signals-then-bounded-codex-fallback",
        "selection_summary": "Keep doc-consistency local-first, with stricter fallback because the review must stay aligned with lint and audit evidence.",
    },
    "changed-surface-summary": {
        "mode": BACKEND_POLICY_DETERMINISTIC,
        "auto_backend": "deterministic",
        "fallback_policy": "deterministic-runner",
        "selection_summary": "Keep changed-surface summaries deterministic because the output is fully derivable from git and repository signals.",
    },
    "release-changelog-status": {
        "mode": BACKEND_POLICY_DETERMINISTIC,
        "auto_backend": "deterministic",
        "fallback_policy": "deterministic-runner",
        "selection_summary": "Keep release changelog resolution deterministic because the contract depends on package version and curated files only.",
    },
    "test-impact-summary": {
        "mode": BACKEND_POLICY_DETERMINISTIC,
        "auto_backend": "deterministic",
        "fallback_policy": "deterministic-runner",
        "selection_summary": "Keep test-impact summaries deterministic because the change surface and available scripts already define the candidate validation order.",
    },
    "hybrid-insights-explainer": {
        "mode": BACKEND_POLICY_DETERMINISTIC,
        "auto_backend": "deterministic",
        "fallback_policy": "deterministic-runner",
        "selection_summary": "Keep Hybrid Insights explanations deterministic because the input is already a structured shared runtime report.",
    },
    "windows-compat-risk": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep Windows compatibility review local-first because the output stays bounded, advisory, and easy to review.",
    },
    "review-checklist": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep review checklists local-first because the output is bounded and directly operator-facing.",
    },
    "doc-link-suggestion": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-against-workflow-refs-then-bounded-codex-fallback",
        "selection_summary": "Keep doc-link suggestions local-first while validating the output against actual workflow references.",
    },
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
    selection_reason: str | None = None
    policy_mode: str | None = None

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
            "selection_reason": self.selection_reason,
            "policy_mode": self.policy_mode,
        }


def default_context_spec(flow_name: str) -> dict[str, Any]:
    if flow_name not in FLOW_CONTEXT_PROFILES:
        raise HybridAssistError("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    return dict(FLOW_CONTEXT_PROFILES[flow_name])


def build_flow_backend_policy(flow_name: str) -> dict[str, str]:
    if flow_name not in FLOW_CONTRACTS:
        raise HybridAssistError("hybrid_unknown_flow", f"Unknown hybrid assist flow `{flow_name}`.")
    policy = FLOW_BACKEND_POLICIES.get(flow_name)
    if policy is None:
        raise HybridAssistError("hybrid_missing_backend_policy", f"Missing backend policy for flow `{flow_name}`.")
    mode = str(policy.get("mode", "")).strip()
    auto_backend = str(policy.get("auto_backend", "")).strip()
    if mode not in BACKEND_POLICY_MODES:
        raise HybridAssistError(
            "hybrid_invalid_backend_policy",
            f"Flow `{flow_name}` uses unsupported backend policy mode `{mode}`.",
        )
    if auto_backend not in SUPPORTED_BACKEND_NAMES:
        raise HybridAssistError(
            "hybrid_invalid_backend_policy",
            f"Flow `{flow_name}` uses unsupported auto backend `{auto_backend}`.",
        )
    return {
        "mode": mode,
        "auto_backend": auto_backend,
        "fallback_policy": str(policy.get("fallback_policy", "")).strip(),
        "selection_summary": str(policy.get("selection_summary", "")).strip(),
    }


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
        "backends": list(SUPPORTED_BACKEND_NAMES),
        "safety_classes": list(SAFETY_CLASSES),
        "backend_policy_modes": list(BACKEND_POLICY_MODES),
        "result_statuses": list(RESULT_STATUSES),
        "model_profiles": default_hybrid_model_profiles(),
        "flows": {
            flow: {
                "summary": contract["summary"],
                "safety_class": contract["safety_class"],
                "required_keys": list(contract["required_keys"]),
                "backend_policy": build_flow_backend_policy(flow),
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
        "backend_policy": build_flow_backend_policy(flow_name),
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
    flow_name: str | None = None,
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
    flow_policy = build_flow_backend_policy(flow_name) if flow_name else None
    policy_mode = flow_policy["mode"] if flow_policy else None

    if policy_mode == BACKEND_POLICY_DETERMINISTIC:
        return HybridBackendStatus(
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

    effective_reasons = list(reasons)
    selection_reason = None
    selected_backend = requested_backend
    healthy = reachable and model_available
    if policy_mode == BACKEND_POLICY_CODEX_ONLY and requested_backend == "ollama":
        raise HybridAssistError(
            "hybrid_backend_policy_violation",
            f"Flow `{flow_name}` is policy-routed away from Ollama.",
            details={"flow": flow_name, "policy_mode": policy_mode, "requested_backend": requested_backend},
        )
    if requested_backend == "auto":
        if policy_mode == BACKEND_POLICY_CODEX_ONLY:
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
        raise HybridAssistError(
            "hybrid_ollama_unavailable",
            f"Ollama backend was requested explicitly but `{model}` is not healthy at {normalized_host}.",
            details={"host": normalized_host, "model": model, "reasons": reasons},
        )
    elif requested_backend == "ollama":
        selected_backend = "ollama"
        selection_reason = "explicit-backend"
        effective_reasons = []
    elif requested_backend == "codex":
        selected_backend = "codex"
        selection_reason = "explicit-backend"
        effective_reasons = []

    if selected_backend == "codex" and requested_backend == "auto" and policy_mode != BACKEND_POLICY_CODEX_ONLY and not effective_reasons:
        effective_reasons.append("ollama-not-selected")
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
        reasons=effective_reasons,
        response_time_ms=response_time_ms,
        version=version,
        selection_reason=selection_reason,
        policy_mode=policy_mode,
    )


def build_hybrid_messages(flow_name: str, context_bundle: dict[str, Any]) -> list[dict[str, str]]:
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
    except socket.timeout as exc:
        raise HybridAssistError(
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
        raise HybridAssistError(
            "hybrid_ollama_empty_response",
            "Ollama returned an empty hybrid assist response.",
            details={"host": host, "model": model, "flow": flow_name},
        )
    try:
        result_payload = extract_json_object(content)
    except Exception as exc:  # noqa: BLE001
        message = exc.args[0] if exc.args else str(exc)
        raise HybridAssistError(
            "hybrid_invalid_json",
            f"Ollama returned a response that did not decode to a JSON object: {message}",
            details={
                "host": host,
                "model": model,
                "flow": flow_name,
                "raw_content_preview": _bounded_diagnostic_value(content),
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


def _normalize_confidence(raw_value: Any) -> float:
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
                raise HybridAssistError(
                    "hybrid_invalid_confidence",
                    "Confidence must be numeric or one of low, medium, high.",
                ) from exc
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

    if flow_name == "changed-surface-summary":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["changed_paths"] = _normalize_string_list(payload["changed_paths"], "changed_paths")
        normalized["categories"] = _normalize_string_list(payload["categories"], "categories")
        return normalized

    if flow_name == "release-changelog-status":
        for key in ("tag", "version", "relative_path", "summary"):
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise HybridAssistError("hybrid_invalid_field", f"`{key}` must be a non-empty string.")
            normalized[key] = " ".join(value.split())[:240]
        exists = payload["exists"]
        if not isinstance(exists, bool):
            raise HybridAssistError("hybrid_invalid_field", "`exists` must be a boolean.")
        normalized["exists"] = exists
        return normalized

    if flow_name == "test-impact-summary":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["commands"] = _normalize_string_list(payload["commands"], "commands")
        normalized["targeted_tests"] = _normalize_string_list(payload["targeted_tests"], "targeted_tests")
        return normalized

    if flow_name == "hybrid-insights-explainer":
        summary = payload["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise HybridAssistError("hybrid_invalid_summary", "`summary` must be a non-empty string.")
        normalized["summary"] = " ".join(summary.split())[:500]
        normalized["strengths"] = _normalize_string_list(payload["strengths"], "strengths")
        normalized["concerns"] = _normalize_string_list(payload["concerns"], "concerns")
        normalized["next_actions"] = _normalize_string_list(payload["next_actions"], "next_actions")
        return normalized

    if flow_name == "windows-compat-risk":
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

    if flow_name == "review-checklist":
        profile = payload["profile"]
        if not isinstance(profile, str) or not profile.strip():
            raise HybridAssistError("hybrid_invalid_profile", "`profile` must be a non-empty string.")
        normalized["profile"] = " ".join(profile.split())[:120]
        normalized["checks"] = _normalize_string_list(payload["checks"], "checks")
        return normalized

    if flow_name == "doc-link-suggestion":
        target_ref = payload["target_ref"]
        if not isinstance(target_ref, str) or target_ref not in docs_by_ref:
            raise HybridAssistError("hybrid_invalid_target_ref", "`target_ref` must resolve to a known workflow doc.")
        normalized["target_ref"] = target_ref
        normalized["missing_links"] = _normalize_string_list(payload["missing_links"], "missing_links")
        normalized["suggested_follow_up"] = _normalize_string_list(payload["suggested_follow_up"], "suggested_follow_up")
        return normalized

    raise HybridAssistError("hybrid_unhandled_flow", f"Unhandled hybrid assist flow `{flow_name}`.")


def _bounded_diagnostic_value(
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
            _bounded_diagnostic_value(item, max_depth=max_depth - 1, max_items=max_items, max_string=max_string)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            limited.append(f"... {len(value) - max_items} more item(s)")
        return limited
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        bounded = {
            str(key): _bounded_diagnostic_value(item, max_depth=max_depth - 1, max_items=max_items, max_string=max_string)
            for key, item in items
        }
        if len(value) > max_items:
            bounded["_truncated_keys"] = len(value) - max_items
        return bounded
    return repr(value)[:max_string]


def build_hybrid_failure_transport(
    *,
    exc: HybridAssistError,
    transport: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transport": "fallback",
        "reason": exc.code,
        "selected_backend": "codex",
        "diagnostic": {
            "error_code": exc.code,
            "error_message": str(exc),
            "details": _bounded_diagnostic_value(exc.details),
        },
    }
    if transport:
        payload["upstream_transport"] = transport.get("transport", "ollama")
        raw_content = transport.get("raw_content")
        response_payload = transport.get("response_payload")
        if raw_content:
            payload["raw_content_preview"] = _bounded_diagnostic_value(raw_content)
        if response_payload is not None:
            payload["response_payload_preview"] = _bounded_diagnostic_value(response_payload)
    return payload


def build_hybrid_failure_raw_payload(
    *,
    exc: HybridAssistError,
    transport: dict[str, Any] | None,
    raw_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw_payload is not None:
        return raw_payload
    if transport and isinstance(transport.get("result_payload"), dict):
        bounded_payload = _bounded_diagnostic_value(transport["result_payload"])
        return bounded_payload if isinstance(bounded_payload, dict) else {"_diagnostic_value": bounded_payload}
    raw_content = transport.get("raw_content") if transport else None
    if isinstance(raw_content, str) and raw_content.strip():
        return {
            "_diagnostic_kind": "invalid-local-response",
            "error_code": exc.code,
            "raw_content_preview": _bounded_diagnostic_value(raw_content),
        }
    raw_preview = exc.details.get("raw_content_preview")
    if raw_preview:
        return {
            "_diagnostic_kind": "invalid-local-response",
            "error_code": exc.code,
            "raw_content_preview": _bounded_diagnostic_value(raw_preview),
        }
    return None


def append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], 0
    records: list[dict[str, Any]] = []
    invalid_lines = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            invalid_lines += 1
    return records, invalid_lines


def _parse_recorded_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _round_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _counter_to_ranked_items(counter: Counter[str], *, limit: int | None = None) -> list[dict[str, Any]]:
    ranked = counter.most_common(limit)
    return [{"label": label, "count": count} for label, count in ranked]


def _stringify_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _summarize_validated_payload(payload: dict[str, Any]) -> str:
    for key in ("summary", "title", "subject", "overall", "classification", "risk"):
        value = payload.get(key)
        text = _stringify_scalar(value)
        if text:
            return " ".join(text.split())[:240]
    if "decision" in payload and isinstance(payload["decision"], dict):
        decision = payload["decision"]
        action = _stringify_scalar(decision.get("action"))
        target = _stringify_scalar(decision.get("target_ref"))
        confidence = decision.get("confidence")
        parts = [part for part in [action, target] if part]
        if confidence is not None:
            parts.append(f"confidence {confidence}")
        if parts:
            return "Decision: " + ", ".join(parts)
    serialized = json.dumps(payload, sort_keys=True)
    return serialized[:240]


def _build_validated_excerpt(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    excerpt: dict[str, Any] = {}
    for key in ("summary", "title", "subject", "overall", "classification", "risk", "target_ref"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            excerpt[key] = value
    if "decision" in payload and isinstance(payload["decision"], dict):
        decision = payload["decision"]
        excerpt["decision"] = {
            "action": decision.get("action"),
            "target_ref": decision.get("target_ref"),
            "confidence": decision.get("confidence"),
        }
    return excerpt or None


def _normalize_reason_label(value: Any, fallback: str = "unspecified") -> str:
    label = _stringify_scalar(value)
    return label if label else fallback


def _fallback_triggered(record: dict[str, Any]) -> bool:
    requested = _stringify_scalar(record.get("backend_requested") or record.get("requested_backend"))
    used = _stringify_scalar(record.get("backend_used") or record.get("selected_backend"))
    return used == "codex" and requested in {"auto", "ollama"}


def _measurement_review_recommended(record: dict[str, Any]) -> bool:
    if bool(record.get("review_recommended")):
        return True
    confidence = record.get("confidence")
    return isinstance(confidence, (int, float)) and float(confidence) < 0.7


def _audit_review_recommended(record: dict[str, Any]) -> bool:
    if bool(record.get("review_recommended")):
        return True
    if record.get("result_status") == "degraded":
        return True
    if record.get("degraded_reasons"):
        return True
    validated_payload = record.get("validated_payload")
    if isinstance(validated_payload, dict):
        confidence = validated_payload.get("confidence")
        if isinstance(confidence, (int, float)) and float(confidence) < 0.7:
            return True
        decision = validated_payload.get("decision")
        if isinstance(decision, dict):
            decision_confidence = decision.get("confidence")
            if isinstance(decision_confidence, (int, float)) and float(decision_confidence) < 0.7:
                return True
    return False


def build_hybrid_roi_report(
    *,
    repo_root: Path,
    audit_log: Path,
    measurement_log: Path,
    recent_limit: int = DEFAULT_HYBRID_ROI_RECENT_LIMIT,
    window_days: int = DEFAULT_HYBRID_ROI_WINDOW_DAYS,
) -> dict[str, Any]:
    effective_recent_limit = max(1, recent_limit)
    effective_window_days = max(1, window_days)
    audit_records, audit_invalid_lines = load_jsonl_records(audit_log)
    measurement_records, measurement_invalid_lines = load_jsonl_records(measurement_log)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=effective_window_days)

    measurement_records_sorted = sorted(
        measurement_records,
        key=lambda record: _parse_recorded_at(record.get("recorded_at")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    audit_records_sorted = sorted(
        audit_records,
        key=lambda record: _parse_recorded_at(record.get("recorded_at")) or datetime.min.replace(tzinfo=timezone.utc),
    )

    total_runs = len(measurement_records_sorted)
    by_flow: dict[str, dict[str, Any]] = {}
    backend_requested_counter: Counter[str] = Counter()
    backend_used_counter: Counter[str] = Counter()
    result_status_counter: Counter[str] = Counter()
    recent_result_distribution_counter: Counter[str] = Counter()
    degraded_reason_counter: Counter[str] = Counter()
    fallback_reason_counter: Counter[str] = Counter()
    review_recommended_count = 0
    degraded_count = 0
    fallback_count = 0
    local_runs_count = 0

    for record in measurement_records_sorted:
        flow = _normalize_reason_label(record.get("flow"), fallback="unknown-flow")
        requested_backend = _normalize_reason_label(record.get("backend_requested"), fallback="unknown")
        used_backend = _normalize_reason_label(record.get("backend_used"), fallback="unknown")
        result_status = _normalize_reason_label(record.get("result_status"), fallback="unknown")
        review_recommended = _measurement_review_recommended(record)
        degraded_reasons = [
            _normalize_reason_label(reason)
            for reason in record.get("degraded_reasons", [])
            if _normalize_reason_label(reason)
        ]
        recorded_at = _parse_recorded_at(record.get("recorded_at"))

        backend_requested_counter[requested_backend] += 1
        backend_used_counter[used_backend] += 1
        result_status_counter[result_status] += 1
        if used_backend == "ollama":
            local_runs_count += 1
        if review_recommended:
            review_recommended_count += 1
        if result_status == "degraded" or degraded_reasons:
            degraded_count += 1
        if _fallback_triggered(record):
            fallback_count += 1

        if recorded_at is not None and recorded_at >= window_start:
            recent_result_distribution_counter[result_status] += 1

        for reason in degraded_reasons:
            degraded_reason_counter[reason] += 1

        flow_bucket = by_flow.setdefault(
            flow,
            {
                "run_count": 0,
                "backend_requested": {},
                "backend_used": {},
                "result_statuses": {},
                "fallback_count": 0,
                "degraded_count": 0,
                "review_recommended_count": 0,
            },
        )
        flow_bucket["run_count"] += 1
        flow_bucket["backend_requested"][requested_backend] = flow_bucket["backend_requested"].get(requested_backend, 0) + 1
        flow_bucket["backend_used"][used_backend] = flow_bucket["backend_used"].get(used_backend, 0) + 1
        flow_bucket["result_statuses"][result_status] = flow_bucket["result_statuses"].get(result_status, 0) + 1
        if _fallback_triggered(record):
            flow_bucket["fallback_count"] += 1
        if result_status == "degraded" or degraded_reasons:
            flow_bucket["degraded_count"] += 1
        if review_recommended:
            flow_bucket["review_recommended_count"] += 1

    for flow_bucket in by_flow.values():
        run_count = int(flow_bucket["run_count"])
        flow_bucket["fallback_rate"] = _round_rate(int(flow_bucket["fallback_count"]), run_count)
        flow_bucket["degraded_rate"] = _round_rate(int(flow_bucket["degraded_count"]), run_count)
        flow_bucket["review_recommended_rate"] = _round_rate(int(flow_bucket["review_recommended_count"]), run_count)

    recent_runs: list[dict[str, Any]] = []
    for audit_record in reversed(audit_records_sorted):
        backend = audit_record.get("backend")
        backend_requested = "unknown"
        backend_used = "unknown"
        if isinstance(backend, dict):
            backend_requested = _normalize_reason_label(backend.get("requested_backend"), fallback="unknown")
            backend_used = _normalize_reason_label(backend.get("selected_backend"), fallback="unknown")
            backend_reason_values = backend.get("reasons")
            if isinstance(backend_reason_values, list):
                for reason in backend_reason_values:
                    if backend_used == "codex" and backend_requested in {"auto", "ollama"}:
                        fallback_reason_counter[_normalize_reason_label(reason)] += 1
        transport = audit_record.get("transport") if isinstance(audit_record.get("transport"), dict) else {}
        if backend_used == "codex" and backend_requested in {"auto", "ollama"}:
            transport_reason = transport.get("reason") if isinstance(transport, dict) else None
            fallback_reason_counter[_normalize_reason_label(transport_reason)] += 1
        recent_runs.append(
            {
                "recorded_at": audit_record.get("recorded_at"),
                "flow": _normalize_reason_label(audit_record.get("flow"), fallback="unknown-flow"),
                "result_status": _normalize_reason_label(audit_record.get("result_status"), fallback="unknown"),
                "backend_requested": backend_requested,
                "backend_used": backend_used,
                "degraded_reasons": [
                    _normalize_reason_label(reason)
                    for reason in audit_record.get("degraded_reasons", [])
                    if _normalize_reason_label(reason)
                ],
                "review_recommended": _audit_review_recommended(audit_record),
                "safety_class": _normalize_reason_label(audit_record.get("safety_class"), fallback="unknown"),
                "seed_ref": (
                    audit_record.get("context_summary", {}).get("seed_ref")
                    if isinstance(audit_record.get("context_summary"), dict)
                    else None
                ),
                "transport": transport if isinstance(transport, dict) else {},
                "validated_summary": _summarize_validated_payload(audit_record.get("validated_payload", {}))
                if isinstance(audit_record.get("validated_payload"), dict)
                else "",
                "validated_excerpt": _build_validated_excerpt(audit_record.get("validated_payload")),
            }
        )
        if len(recent_runs) >= effective_recent_limit:
            break

    total_audit_runs = len(audit_records_sorted)
    recent_runs.reverse()
    fallback_heavy = _round_rate(fallback_count, total_runs) >= 0.25 if total_runs else False
    degraded_heavy = _round_rate(degraded_count, total_runs) >= 0.2 if total_runs else False
    review_heavy = _round_rate(review_recommended_count, total_runs) >= 0.35 if total_runs else False
    local_offload_rate = _round_rate(local_runs_count, total_runs)
    estimated_remote_token_avoidance = local_runs_count * DEFAULT_ESTIMATED_REMOTE_TOKENS_PER_LOCAL_RUN

    health_summary: list[str] = []
    if total_runs == 0:
        health_summary.append("No hybrid assist measurement records are available yet.")
    else:
        if fallback_heavy:
            health_summary.append("Fallback routing is elevated, which suggests local backend instability or explicit codex preference.")
        if degraded_heavy:
            health_summary.append("Degraded outcomes are elevated and should be reviewed before treating the ROI proxies as healthy.")
        if review_heavy:
            health_summary.append("Review-recommended outcomes are frequent, so operator follow-up remains important.")
        if not health_summary:
            health_summary.append("Recent hybrid assist activity looks operationally healthy under the current bounded metrics.")

    return {
        "schema_version": HYBRID_ASSIST_SCHEMA_VERSION,
        "report_kind": "hybrid-assist-roi-report",
        "generated_at": now.isoformat(),
        "ok": True,
        "sources": {
            "audit_log": audit_log.relative_to(repo_root).as_posix() if audit_log.is_absolute() else audit_log.as_posix(),
            "measurement_log": measurement_log.relative_to(repo_root).as_posix()
            if measurement_log.is_absolute()
            else measurement_log.as_posix(),
            "audit_records": total_audit_runs,
            "measurement_records": total_runs,
            "invalid_audit_lines": audit_invalid_lines,
            "invalid_measurement_lines": measurement_invalid_lines,
        },
        "limits": {
            "recent_limit": effective_recent_limit,
            "window_days": effective_window_days,
            "window_start": window_start.isoformat(),
        },
        "semantics": {
            "measured": "Values under `measured` come directly from hybrid assist measurement records and recent audit provenance.",
            "derived": "Values under `derived` are deterministic summaries or rates computed from measured counters.",
            "estimated": "Values under `estimated` are conservative proxies only. They are not billing truth and must be read alongside degraded and fallback rates.",
        },
        "measured": {
            "totals": {
                "runs": total_runs,
                "fallback_runs": fallback_count,
                "degraded_runs": degraded_count,
                "review_recommended_runs": review_recommended_count,
                "local_runs": local_runs_count,
            },
            "runs_by_flow": dict(sorted((flow, bucket["run_count"]) for flow, bucket in by_flow.items())),
            "backend_requested": dict(sorted(backend_requested_counter.items())),
            "backend_used": dict(sorted(backend_used_counter.items())),
            "result_statuses": dict(sorted(result_status_counter.items())),
            "review_recommended_by_flow": {
                flow: bucket["review_recommended_count"] for flow, bucket in sorted(by_flow.items())
            },
            "recent_result_distribution": dict(sorted(recent_result_distribution_counter.items())),
            "flow_breakdown": dict(sorted(by_flow.items())),
        },
        "derived": {
            "rates": {
                "fallback_rate": _round_rate(fallback_count, total_runs),
                "degraded_rate": _round_rate(degraded_count, total_runs),
                "review_recommended_rate": _round_rate(review_recommended_count, total_runs),
                "local_offload_rate": local_offload_rate,
            },
            "dispatch_split": _counter_to_ranked_items(backend_used_counter),
            "top_degraded_reasons": _counter_to_ranked_items(degraded_reason_counter, limit=5),
            "top_fallback_reasons": _counter_to_ranked_items(fallback_reason_counter, limit=5),
            "health_summary": health_summary,
            "report_state": {
                "fallback_heavy": fallback_heavy,
                "degraded_heavy": degraded_heavy,
                "review_heavy": review_heavy,
            },
        },
        "estimated": {
            "assumptions": {
                "remote_tokens_per_local_run": DEFAULT_ESTIMATED_REMOTE_TOKENS_PER_LOCAL_RUN,
                "token_avoidance_note": "Each successful local Ollama run is treated as one avoided remote assist dispatch with a conservative illustrative token budget.",
                "interpretation_note": "Use these proxies for relative trend review only. They are not exact cost or billing metrics.",
            },
            "proxies": {
                "estimated_remote_dispatches_avoided": local_runs_count,
                "estimated_remote_token_avoidance": estimated_remote_token_avoidance,
                "estimated_local_offload_share": local_offload_rate,
            },
        },
        "recent_runs": recent_runs,
    }


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


def _repo_has_local_changes(repo_root: Path) -> bool:
    status_code, status_out, _status_err = _git(repo_root, "status", "--short")
    return status_code == 0 and bool(status_out.strip())


def _submodule_has_local_changes(repo_root: Path, rel_path: str) -> bool:
    submodule_root = repo_root / rel_path
    if not submodule_root.is_dir():
        return False
    return _repo_has_local_changes(submodule_root)


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
        "submodule_has_changes": _submodule_has_local_changes(repo_root, "logics/skills"),
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
    claude_bridge_status: dict[str, Any],
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
    claude_bridge_available = bool(claude_bridge_status.get("available"))
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
        "claude_bridge": claude_bridge_status,
        "claude_bridge_available": claude_bridge_available,
        "flow_backend_policies": {
            flow: build_flow_backend_policy(flow)
            for flow in sorted(FLOW_CONTRACTS.keys())
        },
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


def _deterministic_categories(git_snapshot: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    if git_snapshot.get("doc_only"):
        categories.append("docs-only")
    if git_snapshot.get("touches_runtime"):
        categories.append("runtime")
    if git_snapshot.get("touches_plugin"):
        categories.append("plugin")
    if git_snapshot.get("touches_tests"):
        categories.append("tests")
    if git_snapshot.get("touches_submodule"):
        categories.append("submodule")
    return categories or ["unclassified"]


def _resolve_release_changelog_status(repo_root: Path) -> dict[str, Any]:
    package_json = repo_root / "package.json"
    version = "0.0.0"
    if package_json.is_file():
        try:
            package_payload = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(package_payload.get("version"), str):
                version = package_payload["version"].strip() or version
        except json.JSONDecodeError:
            pass
    tag = f"v{version}"
    relative_path = f"changelogs/CHANGELOGS_{version.replace('.', '_')}.md"
    exists = (repo_root / relative_path).is_file()
    return {
        "tag": tag,
        "version": version,
        "relative_path": relative_path,
        "exists": exists,
        "summary": (
            f"Curated changelog ready for {tag}."
            if exists
            else f"Curated changelog missing for {tag}; expected {relative_path}."
        ),
        "confidence": 0.92,
        "rationale": "Deterministic release-changelog status derived from package.json and curated changelog file presence.",
    }


def _deterministic_test_impact_summary(repo_root: Path, changed_paths: list[str]) -> dict[str, Any]:
    script = repo_root / "logics" / "skills" / "logics-test-impact-orchestrator" / "scripts" / "plan_test_impact.py"
    if not script.is_file():
        return {
            "summary": f"Fallback deterministic test impact summary for {len(changed_paths)} changed path(s).",
            "commands": ["npm run lint", "npm run test"],
            "targeted_tests": ["No repo-local deterministic test-impact script was found."],
            "confidence": 0.55,
            "rationale": "The dedicated deterministic test-impact script is unavailable in this repository snapshot.",
        }

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "summary": "Deterministic test impact script failed; use the default validation safety net.",
            "commands": ["npm run lint", "npm run test"],
            "targeted_tests": [proc.stderr.strip() or "Test impact script failed without diagnostics."],
            "confidence": 0.45,
            "rationale": "The deterministic test-impact script returned a non-zero exit status.",
        }

    commands: list[str] = []
    targeted_tests: list[str] = []
    section = ""
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "## Suggested validation order":
            section = "commands"
            continue
        if line == "## Candidate targeted tests":
            section = "targeted"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if section == "commands":
            normalized = re.sub(r"^\d+\.\s*", "", line).strip()
            if normalized.startswith("`") and normalized.endswith("`"):
                normalized = normalized[1:-1]
            if normalized:
                commands.append(normalized)
        elif section == "targeted":
            targeted_tests.append(line.removeprefix("- ").strip())

    if not commands:
        commands = ["npm run lint", "npm run test"]
    if not targeted_tests:
        targeted_tests = ["No close targeted test match found; rely on the selected command plan."]

    return {
        "summary": f"Deterministic test impact summary built from {len(changed_paths)} changed path(s).",
        "commands": commands,
        "targeted_tests": targeted_tests,
        "confidence": 0.84,
        "rationale": "The summary is derived from the deterministic test-impact planner script.",
    }


def _deterministic_hybrid_insights_explainer(roi_report: dict[str, Any]) -> dict[str, Any]:
    measured = roi_report.get("measured", {}) if isinstance(roi_report, dict) else {}
    raw_derived = roi_report.get("derived", {}) if isinstance(roi_report, dict) else {}
    derived = raw_derived if isinstance(raw_derived, dict) else {}
    totals = measured.get("totals", {}) if isinstance(measured, dict) else {}
    rates = derived.get("rates", {}) if isinstance(derived, dict) else {}
    health_summary = derived.get("health_summary", []) if isinstance(derived, dict) else []
    local_rate = float(rates.get("local_offload_rate", 0.0) or 0.0)
    fallback_rate = float(rates.get("fallback_rate", 0.0) or 0.0)
    degraded_rate = float(rates.get("degraded_rate", 0.0) or 0.0)
    review_rate = float(rates.get("review_recommended_rate", 0.0) or 0.0)

    strengths = [
        f"Local offload is running at {local_rate * 100:.1f}%." if local_rate > 0 else "Measured counters are being recorded."
    ]
    if int(totals.get("local_runs", 0) or 0) > 0:
        strengths.append(f"Local completions total {int(totals.get('local_runs', 0) or 0)} run(s).")

    concerns: list[str] = []
    if fallback_rate > 0:
        concerns.append(f"Fallback routing is visible at {fallback_rate * 100:.1f}%.")
    if degraded_rate > 0:
        concerns.append(f"Degraded outcomes remain present at {degraded_rate * 100:.1f}%.")
    if review_rate >= 0.25:
        concerns.append(f"Review-recommended outcomes remain elevated at {review_rate * 100:.1f}%.")
    if not concerns:
        concerns.append("No strong pressure signal is visible in the measured counters.")

    next_actions = list(health_summary[:2] if isinstance(health_summary, list) else [])
    if fallback_rate > 0:
        next_actions.append("Inspect recent runs and fallback reasons before broadening local-first exposure.")
    if degraded_rate > 0:
        next_actions.append("Review degraded runs first to separate transport issues from payload-quality issues.")
    if not next_actions:
        next_actions.append("Keep recent runs under review while the local-first portfolio expands.")

    return {
        "summary": "Deterministic Hybrid Insights explanation derived from the shared ROI report.",
        "strengths": strengths[:3],
        "concerns": concerns[:3],
        "next_actions": next_actions[:3],
        "confidence": 0.86,
        "rationale": "The explanation is synthesized deterministically from measured counters, derived rates, and health summary notes.",
    }


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
        submodule_has_changes = git_snapshot.get("submodule_has_changes")
        root_paths = [path for path in changed_paths if not path.startswith("logics/skills/") and path != "logics/skills"]
        if touches_submodule and submodule_has_changes and root_paths:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the kit/runtime changes inside logics/skills first.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Commit the parent repo updates and submodule pointer after the kit commit.", "paths": root_paths[:8] or ["logics/skills"]},
                ],
                "confidence": 0.86,
                "rationale": "Separate submodule and parent commits keep git history coherent.",
            }
        if touches_submodule and submodule_has_changes:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the nested logics/skills changes.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Record the updated submodule pointer in the parent repo.", "paths": ["logics/skills"]},
                ],
                "confidence": 0.78,
                "rationale": "Submodule changes still require a parent pointer update.",
            }
        if touches_submodule:
            return {
                "strategy": "single",
                "steps": [{"scope": "root", "summary": "Commit the updated logics/skills submodule pointer in the parent repo.", "paths": root_paths[:8] or ["logics/skills"]}],
                "confidence": 0.82,
                "rationale": "The nested logics/skills repo is already clean, so only the parent pointer update still needs a commit.",
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
    if flow_name == "changed-surface-summary":
        return {
            "summary": _summarize_changed_paths(context_bundle),
            "changed_paths": changed_paths or ["No changed paths detected."],
            "categories": _deterministic_categories(git_snapshot),
            "confidence": 0.9,
            "rationale": "Changed-surface summary is derived directly from the shared git snapshot.",
        }
    if flow_name == "release-changelog-status":
        return _resolve_release_changelog_status(Path(context_bundle.get("repo_root", ".")))
    if flow_name == "test-impact-summary":
        return _deterministic_test_impact_summary(Path(context_bundle.get("repo_root", ".")), changed_paths)
    if flow_name == "hybrid-insights-explainer":
        roi_report = context_bundle.get("roi_report", {})
        return _deterministic_hybrid_insights_explainer(roi_report if isinstance(roi_report, dict) else {})
    if flow_name == "windows-compat-risk":
        risk = "low"
        drivers: list[str] = []
        if any(path.endswith((".ps1", ".bat", ".cmd")) for path in changed_paths):
            risk = "medium"
            drivers.append("Windows-specific script surfaces changed and should be rechecked for entrypoint drift.")
        if any(path.startswith("scripts/") or path.endswith((".mjs", ".py")) for path in changed_paths):
            risk = "medium"
            drivers.append("Script or runtime entrypoints changed and may carry quoting or launcher assumptions.")
        if any(path in {"README.md", "package.json"} for path in changed_paths):
            drivers.append("Operator-facing command examples or npm scripts changed and should stay Windows-safe.")
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            risk = "high"
            drivers.append("The change spans runtime and plugin surfaces, so command contracts can drift across layers.")
        if not drivers:
            drivers.append("No obvious Windows-specific risk signal appears in the changed paths.")
        return {
            "risk": risk,
            "summary": "Fallback Windows compatibility review derived from changed-path categories.",
            "drivers": drivers,
            "confidence": 0.64,
            "rationale": "Fallback Windows review uses deterministic path heuristics when no validated local-model payload is available.",
        }
    if flow_name == "review-checklist":
        checks = ["Review the changed runtime and plugin contracts together.", "Confirm validation commands still match the changed surface."]
        if git_snapshot.get("touches_runtime"):
            checks.append("Inspect fallback, observability, and bounded-output semantics in the shared runtime.")
        if git_snapshot.get("touches_plugin"):
            checks.append("Verify the plugin stays a thin client over the shared runtime command surfaces.")
        if git_snapshot.get("touches_tests"):
            checks.append("Confirm updated tests still reflect real operator behavior rather than stale fixtures.")
        return {
            "profile": "mixed" if git_snapshot.get("touches_runtime") or git_snapshot.get("touches_plugin") else "docs-only",
            "checks": checks,
            "confidence": 0.7,
            "rationale": "Fallback review checklist is derived from the changed-path categories.",
        }
    if flow_name == "doc-link-suggestion":
        doc = docs_by_ref[str(seed_ref)]
        missing_links: list[str] = []
        suggested_follow_up: list[str] = []
        if doc.kind in {"request", "backlog", "task"} and not any(doc.refs.values()):
            missing_links.append("No workflow references are linked yet.")
            suggested_follow_up.append("Link the adjacent request, backlog item, or task before closing the slice.")
        if doc.kind in {"backlog", "task"} and "prod" not in doc.refs and "adr" not in doc.refs:
            missing_links.append("No companion product or architecture doc is linked.")
            suggested_follow_up.append("Confirm whether a product brief or ADR should be linked for this scope.")
        if not missing_links:
            missing_links.append("No obvious missing link was detected from the workflow graph.")
            suggested_follow_up.append("Keep references aligned if the scope or decision framing changes.")
        return {
            "target_ref": doc.ref,
            "missing_links": missing_links,
            "suggested_follow_up": suggested_follow_up,
            "confidence": 0.61,
            "rationale": "Fallback doc-link suggestion is derived from the existing workflow reference graph.",
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
