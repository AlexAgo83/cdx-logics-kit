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
    json_request_impl,
    probe_remote_provider_impl,
    probe_ollama_backend_impl,
    run_gemini_hybrid_impl,
    run_openai_hybrid_impl,
    run_ollama_hybrid_impl,
)
from logics_flow_hybrid_transport_routing import execute_hybrid_backend_impl, select_hybrid_backend_impl
from logics_flow_models import WorkflowDocModel


HYBRID_ASSIST_SCHEMA_VERSION = "1.0"
DEFAULT_HYBRID_BACKEND = "auto"
DEFAULT_HYBRID_MODEL_PROFILE = "deepseek-coder"
DEFAULT_HYBRID_MODEL = "deepseek-coder-v2:16b"
DEFAULT_HYBRID_HOST = "http://127.0.0.1:11434"
DEFAULT_HYBRID_TIMEOUT_SECONDS = 20.0
DEFAULT_HYBRID_AUDIT_LOG = "logics/.cache/hybrid_assist_audit.jsonl"
DEFAULT_HYBRID_MEASUREMENT_LOG = "logics/.cache/hybrid_assist_measurements.jsonl"
DEFAULT_HYBRID_RESULT_CACHE = "logics/.cache/flow_results_cache.json"
DEFAULT_HYBRID_RESULT_CACHE_TTL_SECONDS = 600
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
    "request-draft": {
        "summary": "Draft bounded request Needs and Context blocks from a short operator intent.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("needs", "context", "confidence", "rationale"),
    },
    "spec-first-pass": {
        "summary": "Draft a first-pass spec outline from a backlog item and its acceptance criteria.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("sections", "open_questions", "constraints", "confidence", "rationale"),
    },
    "backlog-groom": {
        "summary": "Draft a bounded backlog-item proposal from a request doc.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("title", "complexity", "acceptance_criteria", "confidence", "rationale"),
        "complexity_enum": ("Low", "Medium", "High"),
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
    "mermaid-generator": {
        "summary": "Generate a bounded Mermaid block for a Logics workflow doc with deterministic fallback.",
        "safety_class": SAFETY_CLASS_PROPOSAL_ONLY,
        "required_keys": ("mermaid", "confidence", "rationale"),
    },
}

FLOW_CONTEXT_PROFILES: dict[str, dict[str, Any]] = {
    "commit-message": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "pr-summary": {"mode": "diff-first", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
    "changelog-summary": {"mode": "diff-first", "profile": "tiny", "include_graph": False, "include_registry": False, "include_doctor": False},
    "validation-summary": {"mode": "summary-only", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": True},
    "next-step": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": True, "include_doctor": True},
    "request-draft": {"mode": "summary-only", "profile": "normal", "include_graph": False, "include_registry": True, "include_doctor": False},
    "spec-first-pass": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
    "backlog-groom": {"mode": "summary-only", "profile": "normal", "include_graph": True, "include_registry": False, "include_doctor": False},
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
    "mermaid-generator": {"mode": "summary-only", "profile": "normal", "include_graph": False, "include_registry": False, "include_doctor": False},
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
        "provider_order": ["codex"],
        "allowed_backends": ["openai", "gemini", "codex"],
        "fallback_policy": "auto-remains-codex-first-explicit-remote-dispatch-validates-then-bounded-codex-fallback",
        "selection_summary": "Keep next-step Codex-only under auto, but allow explicit OpenAI or Gemini dispatch with the same bounded dispatcher validation and Codex fallback on invalid payloads.",
    },
    "request-draft": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep request-draft local-first because the output is bounded, proposal-only, and easy to review before any file write.",
    },
    "spec-first-pass": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep spec-first-pass local-first because the outline is bounded, proposal-only, and derived from a backlog slice.",
    },
    "backlog-groom": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-payload-then-bounded-codex-fallback",
        "selection_summary": "Keep backlog-groom local-first because the proposal is bounded, proposal-only, and derived from a request doc.",
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
    "mermaid-generator": {
        "mode": BACKEND_POLICY_OLLAMA_FIRST,
        "auto_backend": "ollama",
        "fallback_policy": "validate-local-mermaid-then-bounded-codex-fallback-to-deterministic",
        "selection_summary": "Keep Mermaid generation local-first because the output is bounded, proposal-only, and safely replaceable by the deterministic renderer.",
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
    from logics_flow_hybrid_runtime_fallbacks import build_fallback_result

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


__all__ = [name for name in globals() if not name.startswith("__")]
