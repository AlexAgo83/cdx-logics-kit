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
from logics_flow_hybrid_core import (
    apply_legacy_default_model_impl,
    build_deterministic_commit_subject_impl,
    build_flow_backend_policy_impl,
    build_flow_contract_impl,
    build_shared_hybrid_contract_impl,
    default_context_spec_impl,
    default_hybrid_model_profiles_impl,
    infer_commit_focus_from_paths_impl,
    infer_model_family_impl,
    looks_generic_commit_subject_impl,
    merge_hybrid_model_profiles_impl,
    normalize_confidence_impl,
    normalize_string_list_impl,
    resolve_hybrid_model_selection_impl,
    validate_hybrid_result_impl,
)
from logics_flow_hybrid_observability import (
    append_jsonl_record_impl,
    build_hybrid_audit_record_impl,
    build_hybrid_roi_report_impl,
    build_measurement_record_impl,
    build_runtime_status_impl,
    collect_git_snapshot_impl,
    load_jsonl_records_impl,
)
from logics_flow_hybrid_transport import (
    HybridProviderDefinition,
    build_hybrid_provider_registry_impl,
    build_hybrid_messages_impl,
    execute_hybrid_backend_impl,
    json_request_impl,
    probe_remote_provider_impl,
    probe_ollama_backend_impl,
    run_gemini_hybrid_impl,
    run_openai_hybrid_impl,
    run_ollama_hybrid_impl,
    select_hybrid_backend_impl,
)
from logics_flow_models import WorkflowDocModel


HYBRID_ASSIST_SCHEMA_VERSION = "1.0"
DEFAULT_HYBRID_BACKEND = "auto"
DEFAULT_HYBRID_MODEL_PROFILE = "deepseek-coder"
DEFAULT_HYBRID_MODEL = "deepseek-coder-v2:16b"
DEFAULT_HYBRID_HOST = "http://127.0.0.1:11434"
DEFAULT_HYBRID_TIMEOUT_SECONDS = 20.0
DEFAULT_HYBRID_AUDIT_LOG = "logics/.cache/hybrid_assist_audit.jsonl"
DEFAULT_HYBRID_MEASUREMENT_LOG = "logics/.cache/hybrid_assist_measurements.jsonl"
DEFAULT_HYBRID_ROI_RECENT_LIMIT = 8
DEFAULT_HYBRID_ROI_WINDOW_DAYS = 14
DEFAULT_ESTIMATED_REMOTE_TOKENS_PER_LOCAL_RUN = 1200
_GIT_SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}
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
REQUESTED_BACKEND_CHOICES = ("auto", "ollama", "openai", "gemini", "codex")
SUPPORTED_BACKEND_NAMES = ("auto", "ollama", "openai", "gemini", "codex", "deterministic")
RESULT_STATUSES = ("ok", "degraded", "error")
BACKEND_POLICY_OLLAMA_FIRST = "ollama-first"
BACKEND_POLICY_CODEX_ONLY = "codex-only"
BACKEND_POLICY_DETERMINISTIC = "deterministic"
BACKEND_POLICY_MODES = (
    BACKEND_POLICY_OLLAMA_FIRST,
    BACKEND_POLICY_CODEX_ONLY,
    BACKEND_POLICY_DETERMINISTIC,
)
GENERIC_COMMIT_SUBJECTS = {
    "update plugin hybrid assist surfaces",
    "update logics docs and runtime surfaces",
    "add hybrid assist runtime and plugin surfaces",
    "add hybrid assist runtime flows",
}

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
    "generate-changelog": {
        "summary": "Generate a curated changelog document for the current version from git history and changed surfaces.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("content", "title", "entries", "confidence", "rationale"),
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
    "generate-changelog": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
}

FLOW_BACKEND_POLICIES: dict[str, dict[str, Any]] = {
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
    "generate-changelog": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep changelog generation local-first; fall back to Codex if local payload fails validation.",
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
    return default_context_spec_impl(
        flow_name,
        flow_context_profiles=FLOW_CONTEXT_PROFILES,
        error_cls=HybridAssistError,
    )


def build_flow_backend_policy(flow_name: str) -> dict[str, Any]:
    return build_flow_backend_policy_impl(
        flow_name,
        flow_contracts=FLOW_CONTRACTS,
        flow_backend_policies=FLOW_BACKEND_POLICIES,
        backend_policy_modes=BACKEND_POLICY_MODES,
        supported_backend_names=SUPPORTED_BACKEND_NAMES,
        error_cls=HybridAssistError,
    )


def default_hybrid_model_profiles() -> dict[str, dict[str, Any]]:
    return default_hybrid_model_profiles_impl(default_profiles=DEFAULT_HYBRID_MODEL_PROFILES)


def infer_model_family(model: str) -> str:
    return infer_model_family_impl(model)


def merge_hybrid_model_profiles(overrides: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return merge_hybrid_model_profiles_impl(
        overrides,
        default_profiles=DEFAULT_HYBRID_MODEL_PROFILES,
        infer_model_family=infer_model_family,
    )


def apply_legacy_default_model(
    profiles: dict[str, dict[str, Any]],
    *,
    default_profile: str,
    legacy_default_model: str | None,
) -> dict[str, dict[str, Any]]:
    return apply_legacy_default_model_impl(
        profiles,
        default_profile=default_profile,
        legacy_default_model=legacy_default_model,
        infer_model_family=infer_model_family,
    )


def resolve_hybrid_model_selection(
    *,
    configured_profiles: dict[str, dict[str, Any]],
    default_profile: str,
    requested_profile: str | None = None,
    requested_model: str | None = None,
) -> dict[str, Any]:
    return resolve_hybrid_model_selection_impl(
        configured_profiles=configured_profiles,
        default_profile=default_profile,
        requested_profile=requested_profile,
        requested_model=requested_model,
        infer_model_family=infer_model_family,
        error_cls=HybridAssistError,
    )


def build_shared_hybrid_contract() -> dict[str, Any]:
    return build_shared_hybrid_contract_impl(
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
        supported_backend_names=SUPPORTED_BACKEND_NAMES,
        safety_classes=SAFETY_CLASSES,
        backend_policy_modes=BACKEND_POLICY_MODES,
        result_statuses=RESULT_STATUSES,
        flow_contracts=FLOW_CONTRACTS,
        default_hybrid_model_profiles=default_hybrid_model_profiles,
        build_flow_backend_policy=build_flow_backend_policy,
    )


def build_flow_contract(flow_name: str) -> dict[str, Any]:
    return build_flow_contract_impl(
        flow_name,
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
        flow_contracts=FLOW_CONTRACTS,
        allowed_dispatch_actions=ALLOWED_DISPATCH_ACTIONS,
        safe_sync_kinds=SAFE_SYNC_KINDS,
        build_flow_backend_policy=build_flow_backend_policy,
        error_cls=HybridAssistError,
    )


def _json_request(
    host: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return json_request_impl(host, path, headers=headers, payload=payload, timeout_seconds=timeout_seconds)


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
    return probe_ollama_backend_impl(
        requested_backend=requested_backend,
        flow_name=flow_name,
        host=host.strip() or os.environ.get("OLLAMA_HOST", DEFAULT_HYBRID_HOST),
        model_profile=model_profile,
        model_family=model_family,
        configured_model=configured_model,
        model=model,
        timeout_seconds=timeout_seconds,
        default_hybrid_host=DEFAULT_HYBRID_HOST,
        backend_policy_deterministic=BACKEND_POLICY_DETERMINISTIC,
        backend_policy_codex_only=BACKEND_POLICY_CODEX_ONLY,
        error_cls=HybridAssistError,
        backend_status_cls=HybridBackendStatus,
        build_flow_backend_policy=build_flow_backend_policy,
        json_request=lambda request_host, request_path: _json_request(
            request_host,
            request_path,
            timeout_seconds=timeout_seconds,
        ),
    )


def probe_remote_provider(
    *,
    provider: HybridProviderDefinition,
    requested_backend: str,
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> HybridBackendStatus:
    hybrid_config = config.get("hybrid_assist", {}) if isinstance(config, dict) else {}
    provider_config = hybrid_config.get("providers", {}) if isinstance(hybrid_config, dict) else {}
    health_path = str(hybrid_config.get("provider_health_path", "logics/.cache/provider_health.json")).strip() or "logics/.cache/provider_health.json"
    cooldown_seconds = int(provider_config.get("readiness_cooldown_seconds", 300)) if isinstance(provider_config, dict) else 300
    return probe_remote_provider_impl(
        provider=provider,
        requested_backend=requested_backend,
        timeout_seconds=timeout_seconds,
        provider_health_path=(repo_root / health_path).resolve() if repo_root is not None else None,
        cooldown_seconds=cooldown_seconds,
        backend_status_cls=HybridBackendStatus,
        error_cls=HybridAssistError,
        json_request=_json_request,
    )


def build_hybrid_provider_registry(
    *,
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
    requested_backend: str = DEFAULT_HYBRID_BACKEND,
    requested_model: str | None = None,
    host: str = DEFAULT_HYBRID_HOST,
    model_profile: str = DEFAULT_HYBRID_MODEL_PROFILE,
    model_family: str = "deepseek",
    configured_model: str = DEFAULT_HYBRID_MODEL,
    model: str = DEFAULT_HYBRID_MODEL,
) -> dict[str, HybridProviderDefinition]:
    return build_hybrid_provider_registry_impl(
        repo_root=repo_root,
        config=config,
        requested_backend=requested_backend,
        requested_model=requested_model,
        host=host,
        default_hybrid_host=DEFAULT_HYBRID_HOST,
        model_profile=model_profile,
        model_family=model_family,
        configured_model=configured_model,
        model=model,
    )


def select_hybrid_backend(
    *,
    requested_backend: str,
    flow_name: str,
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
    requested_model: str | None = None,
    host: str = DEFAULT_HYBRID_HOST,
    model_profile: str = DEFAULT_HYBRID_MODEL_PROFILE,
    model_family: str = "deepseek",
    configured_model: str = DEFAULT_HYBRID_MODEL,
    model: str = DEFAULT_HYBRID_MODEL,
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> HybridBackendStatus:
    provider_registry = build_hybrid_provider_registry(
        repo_root=repo_root,
        config=config,
        requested_backend=requested_backend,
        requested_model=requested_model,
        host=host,
        model_profile=model_profile,
        model_family=model_family,
        configured_model=configured_model,
        model=model,
    )
    return select_hybrid_backend_impl(
        requested_backend=requested_backend,
        flow_name=flow_name,
        host=host,
        default_hybrid_host=DEFAULT_HYBRID_HOST,
        model_profile=model_profile,
        model_family=model_family,
        configured_model=configured_model,
        model=model,
        timeout_seconds=timeout_seconds,
        provider_registry=provider_registry,
        build_flow_backend_policy=build_flow_backend_policy,
        probe_ollama_backend=probe_ollama_backend,
        probe_remote_provider=lambda *, provider, requested_backend, timeout_seconds: probe_remote_provider(
            provider=provider,
            requested_backend=requested_backend,
            repo_root=repo_root,
            config=config,
            timeout_seconds=timeout_seconds,
        ),
        backend_status_cls=HybridBackendStatus,
        error_cls=HybridAssistError,
    )


def build_hybrid_messages(flow_name: str, context_bundle: dict[str, Any]) -> list[dict[str, str]]:
    return build_hybrid_messages_impl(flow_name, context_bundle)


def run_ollama_hybrid(
    *,
    host: str,
    model: str,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return run_ollama_hybrid_impl(
        host=host,
        model=model,
        flow_name=flow_name,
        context_bundle=context_bundle,
        timeout_seconds=timeout_seconds,
        error_cls=HybridAssistError,
        json_request=_json_request,
        extract_json_object=extract_json_object,
        build_hybrid_messages=build_hybrid_messages,
    )


def run_openai_hybrid(
    *,
    provider: HybridProviderDefinition,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return run_openai_hybrid_impl(
        provider=provider,
        flow_name=flow_name,
        context_bundle=context_bundle,
        timeout_seconds=timeout_seconds,
        error_cls=HybridAssistError,
        json_request=_json_request,
        extract_json_object=extract_json_object,
        build_hybrid_messages=build_hybrid_messages,
    )


def run_gemini_hybrid(
    *,
    provider: HybridProviderDefinition,
    flow_name: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return run_gemini_hybrid_impl(
        provider=provider,
        flow_name=flow_name,
        context_bundle=context_bundle,
        timeout_seconds=timeout_seconds,
        error_cls=HybridAssistError,
        json_request=_json_request,
        extract_json_object=extract_json_object,
        build_hybrid_messages=build_hybrid_messages,
    )


def execute_hybrid_backend(
    *,
    backend_status: HybridBackendStatus,
    requested_backend: str,
    flow_name: str,
    context_bundle: dict[str, Any],
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
    requested_model: str | None = None,
    timeout_seconds: float = DEFAULT_HYBRID_TIMEOUT_SECONDS,
    docs_by_ref: dict[str, WorkflowDocModel],
    validation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider_registry = build_hybrid_provider_registry(
        repo_root=repo_root,
        config=config,
        requested_backend=requested_backend,
        requested_model=requested_model,
        host=backend_status.host,
        model_profile=backend_status.model_profile,
        model_family=backend_status.model_family,
        configured_model=backend_status.configured_model,
        model=backend_status.model,
    )
    return execute_hybrid_backend_impl(
        backend_status=backend_status,
        requested_backend=requested_backend,
        flow_name=flow_name,
        context_bundle=context_bundle,
        timeout_seconds=timeout_seconds,
        docs_by_ref=docs_by_ref,
        validation_payload=validation_payload,
        provider_registry=provider_registry,
        run_ollama_hybrid=run_ollama_hybrid,
        run_openai_hybrid=run_openai_hybrid,
        run_gemini_hybrid=run_gemini_hybrid,
        validate_hybrid_result=validate_hybrid_result,
        build_hybrid_failure_raw_payload=build_hybrid_failure_raw_payload,
        build_hybrid_failure_transport=build_hybrid_failure_transport,
        build_fallback_result=build_fallback_result,
        backend_status_cls=HybridBackendStatus,
        error_cls=HybridAssistError,
    )


def _normalize_confidence(raw_value: Any) -> float:
    return normalize_confidence_impl(raw_value, error_cls=HybridAssistError)


def _normalize_string_list(value: Any, key: str, *, min_items: int = 1) -> list[str]:
    return normalize_string_list_impl(value, key, min_items=min_items, error_cls=HybridAssistError)


def _looks_generic_commit_subject(subject: str) -> bool:
    return looks_generic_commit_subject_impl(subject, generic_commit_subjects=GENERIC_COMMIT_SUBJECTS)


def _infer_commit_focus_from_paths(changed_paths: list[str]) -> str | None:
    return infer_commit_focus_from_paths_impl(changed_paths)


def _build_deterministic_commit_subject(git_snapshot: dict[str, Any]) -> str:
    return build_deterministic_commit_subject_impl(
        git_snapshot,
        infer_commit_focus_from_paths=_infer_commit_focus_from_paths,
    )


def validate_hybrid_result(
    flow_name: str,
    payload: dict[str, Any],
    docs_by_ref: dict[str, WorkflowDocModel],
    *,
    context_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return validate_hybrid_result_impl(
        flow_name,
        payload,
        docs_by_ref,
        context_bundle=context_bundle,
        flow_contracts=FLOW_CONTRACTS,
        error_cls=HybridAssistError,
        validate_dispatcher_decision=validate_dispatcher_decision,
        normalize_confidence=_normalize_confidence,
        normalize_string_list=lambda value, key: _normalize_string_list(value, key),
        looks_generic_commit_subject=_looks_generic_commit_subject,
    )


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
    append_jsonl_record_impl(path, record)


def load_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    return load_jsonl_records_impl(path)


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
    return build_hybrid_roi_report_impl(
        repo_root=repo_root,
        audit_log=audit_log,
        measurement_log=measurement_log,
        recent_limit=recent_limit,
        window_days=window_days,
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
        default_estimated_remote_tokens_per_local_run=DEFAULT_ESTIMATED_REMOTE_TOKENS_PER_LOCAL_RUN,
    )


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


def collect_git_snapshot(repo_root: Path, *, refresh: bool = False) -> dict[str, Any]:
    cache_key = str(repo_root.resolve())
    if refresh or cache_key not in _GIT_SNAPSHOT_CACHE:
        _GIT_SNAPSHOT_CACHE[cache_key] = collect_git_snapshot_impl(repo_root)
    return deepcopy(_GIT_SNAPSHOT_CACHE[cache_key])


def build_runtime_status(
    *,
    repo_root: Path,
    requested_backend: str,
    requested_model: str | None = None,
    config: dict[str, Any] | None = None,
    host: str,
    model_profile: dict[str, Any],
    supported_model_profiles: dict[str, dict[str, Any]],
    model: str,
    timeout_seconds: float,
    claude_bridge_status: dict[str, Any],
) -> dict[str, Any]:
    provider_registry = build_hybrid_provider_registry(
        repo_root=repo_root,
        config=config,
        requested_backend=requested_backend,
        requested_model=requested_model,
        host=host,
        model_profile=str(model_profile["name"]),
        model_family=str(model_profile["family"]),
        configured_model=str(model_profile["configured_model"]),
        model=model,
    )
    return build_runtime_status_impl(
        repo_root=repo_root,
        requested_backend=requested_backend,
        requested_model=requested_model,
        config=config,
        host=host,
        model_profile=model_profile,
        supported_model_profiles=supported_model_profiles,
        model=model,
        timeout_seconds=timeout_seconds,
        claude_bridge_status=claude_bridge_status,
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
        flow_contracts=FLOW_CONTRACTS,
        provider_registry=provider_registry,
        select_hybrid_backend=select_hybrid_backend,
        probe_ollama_backend=probe_ollama_backend,
        probe_remote_provider=lambda *, provider, requested_backend, timeout_seconds: probe_remote_provider(
            provider=provider,
            requested_backend=requested_backend,
            repo_root=repo_root,
            config=config,
            timeout_seconds=timeout_seconds,
        ),
        build_flow_backend_policy=build_flow_backend_policy,
    )


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
    return build_hybrid_audit_record_impl(
        flow_name=flow_name,
        result_status=result_status,
        backend_status=backend_status,
        context_bundle=context_bundle,
        raw_payload=raw_payload,
        validated_payload=validated_payload,
        transport=transport,
        degraded_reasons=degraded_reasons,
        execution_result=execution_result,
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
    )


def build_measurement_record(
    *,
    flow_name: str,
    backend_status: HybridBackendStatus,
    result_status: str,
    confidence: float | None,
    degraded_reasons: list[str],
    review_recommended: bool,
) -> dict[str, Any]:
    return build_measurement_record_impl(
        flow_name=flow_name,
        backend_status=backend_status,
        result_status=result_status,
        confidence=confidence,
        degraded_reasons=degraded_reasons,
        review_recommended=review_recommended,
        schema_version=HYBRID_ASSIST_SCHEMA_VERSION,
    )


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
    version_file = repo_root / "VERSION"
    package_version = _read_release_package_version(repo_root)
    version_file_version = _read_release_version_file(repo_root)
    version_source = "default"
    version = "0.0.0"
    if package_version:
        version = package_version
        version_source = "package.json"
    elif version_file_version:
        version = version_file_version
        version_source = "VERSION"

    version_mismatch = bool(package_version and version_file_version and package_version != version_file_version)
    tag = f"v{version}"
    relative_path = f"changelogs/CHANGELOGS_{version.replace('.', '_')}.md"
    exists = (repo_root / relative_path).is_file()
    tag_exists_local = _git_tag_exists(repo_root, tag)
    tag_exists_remote = _git_remote_tag_exists(repo_root, tag)
    already_published = tag_exists_local or tag_exists_remote
    next_version = _next_patch_release_version(version) if version != "0.0.0" else None
    next_tag = f"v{next_version}" if next_version else None
    readme_badge_ok: bool | None = None
    for readme_name in ("README.md", "readme.md", "Readme.md"):
        readme_path = repo_root / readme_name
        if readme_path.is_file():
            readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
            readme_badge_ok = f"version-v{version}" in readme_text or f"version/{version}" in readme_text or f"v{version}" in readme_text
            break
    warnings: list[str] = []
    if version_mismatch:
        warnings.append(
            f"VERSION is out of sync with package.json ({version_file_version} vs {package_version}); update VERSION before publishing."
        )
    if already_published:
        if next_tag:
            warnings.append(
                f"{tag} is already tagged or published; bump to {next_tag} before preparing another release."
            )
        else:
            warnings.append(f"{tag} is already tagged or published; bump the version before preparing another release.")
    if readme_badge_ok is False:
        warnings.append(f"README version badge may not reflect {tag}; update the badge before publishing.")
    summary_parts = [
        (
            f"Curated changelog ready for {tag}."
            if exists
            else f"Curated changelog missing for {tag}; expected {relative_path}."
        )
    ]
    if warnings:
        summary_parts.extend(warnings)
    return {
        "tag": tag,
        "version": version,
        "version_source": version_source,
        "next_version": next_version,
        "next_tag": next_tag,
        "package_version": package_version,
        "version_file_version": version_file_version,
        "version_mismatch": version_mismatch,
        "relative_path": relative_path,
        "exists": exists,
        "tag_exists_local": tag_exists_local,
        "tag_exists_remote": tag_exists_remote,
        "already_published": already_published,
        "readme_badge_ok": readme_badge_ok,
        "warnings": warnings,
        "summary": " ".join(summary_parts),
        "confidence": 0.92,
        "rationale": "Deterministic release-changelog status derived from package.json or VERSION file and curated changelog file presence.",
    }


def _read_release_package_version(repo_root: Path) -> str | None:
    package_json = repo_root / "package.json"
    if not package_json.is_file():
        return None
    try:
        package_payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    candidate = package_payload.get("version")
    if not isinstance(candidate, str):
        return None
    normalized = candidate.strip()
    if not normalized or normalized == "0.0.0":
        return None
    return normalized


def _next_patch_release_version(version: str) -> str | None:
    parts = version.split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return None
    return f"{major}.{minor}.{patch + 1}"


def _read_release_version_file(repo_root: Path) -> str | None:
    version_file = repo_root / "VERSION"
    if not version_file.is_file():
        return None
    candidate = version_file.read_text(encoding="utf-8").strip()
    return candidate or None


def _git_tag_exists(repo_root: Path, tag: str) -> bool:
    completed = subprocess.run(
        ["git", "tag", "--list", tag],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() == tag


def _git_remote_tag_exists(repo_root: Path, tag: str) -> bool:
    remote = _git_default_remote(repo_root)
    if not remote:
        return False
    try:
        completed = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", remote, f"refs/tags/{tag}"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _git_default_remote(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "remote"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    remotes = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not remotes:
        return None
    if "origin" in remotes:
        return "origin"
    return remotes[0]


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
        subject = _build_deterministic_commit_subject(git_snapshot)
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
    if flow_name == "generate-changelog":
        version_info = _resolve_release_changelog_status(Path(context_bundle.get("repo_root", ".")))
        version = version_info.get("version", "0.0.0")
        tag = version_info.get("tag", f"v{version}")
        entries: list[str] = []
        if git_snapshot.get("touches_plugin"):
            entries.append("Expose new action surfaces in the VS Code plugin.")
        if git_snapshot.get("touches_runtime"):
            entries.append("Add bounded hybrid assist flows and delivery automation.")
        if git_snapshot.get("touches_tests"):
            entries.append("Add or update integration tests for the new flows.")
        if not entries:
            entries.append("Delivery automation and workflow surface updates.")
        content_lines = [f"# Changelog (`{tag}`)", "", "## Highlights", ""]
        content_lines += [f"- {e}" for e in entries]
        return {
            "content": "\n".join(content_lines),
            "title": f"Release {tag}",
            "entries": entries,
            "confidence": 0.6,
            "rationale": "Fallback changelog generated from changed-path categories when AI runtime is unavailable.",
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
