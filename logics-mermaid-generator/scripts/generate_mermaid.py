#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any

FLOW_MANAGER_SCRIPTS = Path(__file__).resolve().parents[2] / "logics-flow-manager" / "scripts"
if str(FLOW_MANAGER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FLOW_MANAGER_SCRIPTS))

from logics_flow_config import get_config_value, load_repo_config  # noqa: E402
from logics_flow_hybrid import (  # noqa: E402
    DEFAULT_HYBRID_AUDIT_LOG,
    DEFAULT_HYBRID_BACKEND,
    DEFAULT_HYBRID_HOST,
    DEFAULT_HYBRID_MEASUREMENT_LOG,
    HybridAssistError,
    append_jsonl_record,
    apply_legacy_default_model,
    build_flow_contract,
    build_hybrid_audit_record,
    build_hybrid_provider_registry,
    build_measurement_record,
    default_hybrid_model_profiles,
    merge_hybrid_model_profiles,
    probe_ollama_backend,
    probe_remote_provider,
    resolve_hybrid_model_selection,
    run_gemini_hybrid,
    run_ollama_hybrid,
    run_openai_hybrid,
    validate_hybrid_result,
)

HYBRID_FLOW_NAME = "mermaid-generator"
HYBRID_TIMEOUT_SECONDS = 8.0
MERMAID_LABEL_MAX_WORDS = 6
MERMAID_LABEL_MAX_CHARS = 42
MERMAID_MAX_NODES = 8
MERMAID_FALLBACKS = {
    "request_backlog": "Backlog slice",
    "backlog_task": "Execution task",
    "task_report": "Done report",
}
REF_PREFIXES = {
    "request": "req",
    "backlog": "item",
    "task": "task",
}
MERMAID_NODE_PATTERN = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\[(.*?)\]")


def _plain_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>]+", " ", text)
    text = re.sub(r"[^A-Za-z0-9:._ -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text


def _safe_mermaid_label(value: str, fallback: str) -> str:
    text = _plain_text(value)
    if not text:
        text = fallback
    words = text.split()
    if len(words) > MERMAID_LABEL_MAX_WORDS:
        text = " ".join(words[:MERMAID_LABEL_MAX_WORDS])
    if len(text) > MERMAID_LABEL_MAX_CHARS:
        text = text[:MERMAID_LABEL_MAX_CHARS].rstrip(" .:-")
    return text or fallback


def _rendered_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^- \[[ xX]\]\s*", "", stripped)
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        items.append(stripped)
    return items


def _pick_mermaid_summary(candidates: list[str], fallback: str) -> str:
    for candidate in candidates:
        label = _safe_mermaid_label(candidate, "")
        if label:
            return label
    return fallback


def _mermaid_signature_part(value: str) -> str:
    text = _plain_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:40]


def _compose_mermaid_signature(kind_name: str, *parts: str) -> str:
    signature_parts = [_mermaid_signature_part(kind_name)]
    for part in parts:
        rendered = _mermaid_signature_part(part)
        if rendered:
            signature_parts.append(rendered)
    return "|".join(signature_parts)


def _render_mermaid_block(kind_name: str, signature: str, lines: list[str]) -> str:
    return "\n".join(
        [
            "```mermaid",
            f"%% logics-kind: {kind_name}",
            f"%% logics-signature: {signature}",
            *lines,
            "```",
        ]
    )


def _extract_refs(text: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return sorted({match.group(0) for match in pattern.finditer(text)})


def _render_request_mermaid(title: str, values: dict[str, str]) -> str:
    need_items = _rendered_list_items(values.get("NEEDS_PLACEHOLDER", ""))
    context_items = _rendered_list_items(values.get("CONTEXT_PLACEHOLDER", ""))
    acceptance_items = _rendered_list_items(values.get("ACCEPTANCE_PLACEHOLDER", ""))
    title_label = _safe_mermaid_label(title, "Request need")
    need_label = _pick_mermaid_summary([*need_items, *context_items, title], "Need scope")
    outcome_label = _pick_mermaid_summary([*acceptance_items, *context_items], "Acceptance target")
    feedback_label = _safe_mermaid_label(MERMAID_FALLBACKS["request_backlog"], MERMAID_FALLBACKS["request_backlog"])
    signature = _compose_mermaid_signature("request", title, need_label, outcome_label)
    return _render_mermaid_block(
        "request",
        signature,
        [
            "flowchart TD",
            f"    Trigger[{title_label}] --> Need[{need_label}]",
            f"    Need --> Outcome[{outcome_label}]",
            f"    Outcome --> Backlog[{feedback_label}]",
        ],
    )


def _render_backlog_mermaid(title: str, values: dict[str, str]) -> str:
    request_refs = _extract_refs(values.get("REQUEST_LINK_PLACEHOLDER", ""), REF_PREFIXES["request"])
    task_refs = _extract_refs(values.get("TASK_LINK_PLACEHOLDER", ""), REF_PREFIXES["task"])
    problem_items = _rendered_list_items(values.get("PROBLEM_PLACEHOLDER", ""))
    acceptance_items = _rendered_list_items(values.get("ACCEPTANCE_BLOCK", ""))
    source_label = _pick_mermaid_summary([*request_refs, title], "Request source")
    problem_label = _pick_mermaid_summary([*problem_items, title], "Problem scope")
    scope_label = _safe_mermaid_label(title, "Scoped delivery")
    acceptance_label = _pick_mermaid_summary(acceptance_items, "Acceptance check")
    task_label = _pick_mermaid_summary(task_refs, MERMAID_FALLBACKS["backlog_task"])
    signature = _compose_mermaid_signature("backlog", title, source_label, problem_label, acceptance_label)
    return _render_mermaid_block(
        "backlog",
        signature,
        [
            "flowchart LR",
            f"    Request[{source_label}] --> Problem[{problem_label}]",
            f"    Problem --> Scope[{scope_label}]",
            f"    Scope --> Acceptance[{acceptance_label}]",
            f"    Acceptance --> Tasks[{task_label}]",
        ],
    )


def _render_task_mermaid(title: str, values: dict[str, str]) -> str:
    backlog_refs = _extract_refs(values.get("BACKLOG_LINK_PLACEHOLDER", ""), REF_PREFIXES["backlog"])
    plan_items = [
        item
        for item in _rendered_list_items(values.get("PLAN_BLOCK", ""))
        if not item.lower().startswith("final:")
    ]
    validation_items = _rendered_list_items(values.get("VALIDATION_BLOCK", ""))
    source_label = _pick_mermaid_summary([*backlog_refs, title], "Backlog source")
    step_one = _pick_mermaid_summary(plan_items[:1], "Confirm scope")
    step_two = _pick_mermaid_summary(plan_items[1:2], "Implement scope")
    step_three = _pick_mermaid_summary(plan_items[2:3], "Validate result")
    validation_label = _pick_mermaid_summary(validation_items, "Validation")
    report_label = _safe_mermaid_label(MERMAID_FALLBACKS["task_report"], MERMAID_FALLBACKS["task_report"])
    signature = _compose_mermaid_signature("task", title, source_label, step_one, validation_label)
    return _render_mermaid_block(
        "task",
        signature,
        [
            "flowchart LR",
            f"    Backlog[{source_label}] --> Step1[{step_one}]",
            f"    Step1 --> Step2[{step_two}]",
            f"    Step2 --> Step3[{step_three}]",
            f"    Step3 --> Validation[{validation_label}]",
            f"    Validation --> Report[{report_label}]",
        ],
    )


def _render_workflow_mermaid(kind_name: str, title: str, values: dict[str, str]) -> str:
    if kind_name == "request":
        return _render_request_mermaid(title, values)
    if kind_name == "backlog":
        return _render_backlog_mermaid(title, values)
    if kind_name == "task":
        return _render_task_mermaid(title, values)
    raise ValueError(f"Unsupported Mermaid workflow kind: {kind_name}")


def _normalize_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in values.items()}


def _mermaid_key_sections(kind_name: str, values: dict[str, str]) -> dict[str, list[str]]:
    if kind_name == "request":
        return {
            "needs": _rendered_list_items(values.get("NEEDS_PLACEHOLDER", "")),
            "context": _rendered_list_items(values.get("CONTEXT_PLACEHOLDER", "")),
            "acceptance": _rendered_list_items(values.get("ACCEPTANCE_PLACEHOLDER", "")),
        }
    if kind_name == "backlog":
        return {
            "problem": _rendered_list_items(values.get("PROBLEM_PLACEHOLDER", "")),
            "acceptance": _rendered_list_items(values.get("ACCEPTANCE_BLOCK", "")),
            "refs": _extract_refs(values.get("REQUEST_LINK_PLACEHOLDER", ""), REF_PREFIXES["request"]),
        }
    return {
        "plan": _rendered_list_items(values.get("PLAN_BLOCK", "")),
        "validation": _rendered_list_items(values.get("VALIDATION_BLOCK", "")),
        "refs": _extract_refs(values.get("BACKLOG_LINK_PLACEHOLDER", ""), REF_PREFIXES["backlog"]),
    }


def _expected_direction(kind_name: str) -> str:
    return "TD" if kind_name == "request" else "LR"


def _validate_mermaid_safety(kind_name: str, mermaid_block: str) -> list[str]:
    issues: list[str] = []
    lines = mermaid_block.strip().splitlines()
    if len(lines) < 5 or lines[0].strip() != "```mermaid":
        issues.append("mermaid-fence-missing")
        return issues
    if lines[-1].strip() != "```":
        issues.append("mermaid-fence-unclosed")
    kind_line = next((line.strip() for line in lines if line.strip().startswith("%% logics-kind:")), "")
    signature_line = next((line.strip() for line in lines if line.strip().startswith("%% logics-signature:")), "")
    if kind_line != f"%% logics-kind: {kind_name}":
        issues.append("mermaid-kind-mismatch")
    if not signature_line:
        issues.append("mermaid-signature-missing")
    flowchart_line = next((line.strip() for line in lines if line.strip().startswith("flowchart ")), "")
    if flowchart_line != f"flowchart {_expected_direction(kind_name)}":
        issues.append("mermaid-direction-mismatch")
    node_ids: set[str] = set()
    for node_id, label in MERMAID_NODE_PATTERN.findall(mermaid_block):
        node_ids.add(node_id)
        if any(ord(char) > 127 for char in label):
            issues.append("mermaid-non-ascii-label")
        if re.search(r"[*_`#]", label):
            issues.append("mermaid-markdown-label")
        if "-->" in label or "---" in label or "{" in label or "}" in label:
            issues.append("mermaid-unsafe-route-label")
    if len(node_ids) > MERMAID_MAX_NODES:
        issues.append("mermaid-node-count-exceeded")
    return sorted(set(issues))


def _build_mermaid_context_bundle(kind_name: str, title: str, values: dict[str, str]) -> dict[str, Any]:
    return {
        "contract": build_flow_contract(HYBRID_FLOW_NAME),
        "context_pack": {
            "doc_kind": kind_name,
            "title": title,
            "direction": _expected_direction(kind_name),
            "key_sections": _mermaid_key_sections(kind_name, values),
        },
        "operator_input": {
            "doc_kind": kind_name,
            "title": title,
        },
        "mermaid_request": {
            "kind": kind_name,
            "title": title,
            "values": values,
        },
        "git_snapshot": {
            "changed_paths": [],
            "unstaged_diff_stat": [],
            "staged_diff_stat": [],
            "has_changes": False,
        },
    }


def _extract_deterministic_signature(mermaid_block: str) -> str:
    for line in mermaid_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("%% logics-signature:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _normalize_candidate_mermaid(
    *,
    kind_name: str,
    candidate_mermaid: str,
    deterministic_mermaid: str,
) -> str:
    stripped = candidate_mermaid.strip()
    if not stripped:
        return candidate_mermaid
    signature = _extract_deterministic_signature(deterministic_mermaid)
    direction = _expected_direction(kind_name)

    if stripped.startswith("```mermaid"):
        body_lines = [
            line.rstrip()
            for line in stripped.splitlines()
            if line.strip()
            and line.strip() not in {"```mermaid", "```"}
            and not line.strip().startswith("%% logics-kind:")
            and not line.strip().startswith("%% logics-signature:")
            and not line.strip().startswith("flowchart ")
        ]
        return _render_mermaid_block(
            kind_name,
            signature,
            [f"flowchart {direction}", *body_lines],
        )

    if not stripped.startswith("flowchart "):
        return candidate_mermaid

    body_lines = [line.rstrip() for line in stripped.splitlines() if line.strip()]
    if body_lines:
        body_lines[0] = f"flowchart {direction}"
    return _render_mermaid_block(
        kind_name,
        signature,
        body_lines,
    )


def _resolve_model_selection(
    config: dict[str, Any],
    *,
    requested_model_profile: str | None,
    requested_model: str | None,
) -> dict[str, Any]:
    configured_profiles = merge_hybrid_model_profiles(get_config_value(config, "hybrid_assist", "model_profiles", default={}))
    configured_profiles = apply_legacy_default_model(
        configured_profiles,
        default_profile=str(get_config_value(config, "hybrid_assist", "default_model_profile", default="deepseek-coder")),
        legacy_default_model=str(get_config_value(config, "hybrid_assist", "default_model", default="")).strip() or None,
    )
    return resolve_hybrid_model_selection(
        configured_profiles=configured_profiles or default_hybrid_model_profiles(),
        default_profile=str(get_config_value(config, "hybrid_assist", "default_model_profile", default="deepseek-coder")),
        requested_profile=requested_model_profile,
        requested_model=requested_model,
    )


def generate_mermaid(
    *,
    repo_root: Path,
    kind_name: str,
    title: str,
    values: dict[str, Any],
    requested_backend: str = DEFAULT_HYBRID_BACKEND,
    requested_model_profile: str | None = None,
    requested_model: str | None = None,
    ollama_host: str | None = None,
    timeout_seconds: float = HYBRID_TIMEOUT_SECONDS,
    audit_log: str = DEFAULT_HYBRID_AUDIT_LOG,
    measurement_log: str = DEFAULT_HYBRID_MEASUREMENT_LOG,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_values = _normalize_values(values)
    deterministic_mermaid = _render_workflow_mermaid(kind_name, title, normalized_values)
    repo_root = repo_root.resolve()
    config, _config_path = load_repo_config(repo_root)
    context_bundle = _build_mermaid_context_bundle(kind_name, title, normalized_values)
    model_selection = _resolve_model_selection(
        config,
        requested_model_profile=requested_model_profile,
        requested_model=requested_model,
    )
    resolved_host = str(ollama_host or get_config_value(config, "hybrid_assist", "ollama_host", default=DEFAULT_HYBRID_HOST)).strip() or DEFAULT_HYBRID_HOST
    backend_status = probe_ollama_backend(
        requested_backend=requested_backend,
        flow_name=HYBRID_FLOW_NAME,
        host=resolved_host,
        model_profile=str(model_selection["name"]),
        model_family=str(model_selection["family"]),
        configured_model=str(model_selection["configured_model"]),
        model=str(model_selection["resolved_model"]),
        timeout_seconds=timeout_seconds,
    )
    provider_registry = build_hybrid_provider_registry(
        repo_root=repo_root,
        config=config,
        requested_backend=requested_backend,
        requested_model=requested_model,
        host=resolved_host,
        model_profile=str(model_selection["name"]),
        model_family=str(model_selection["family"]),
        configured_model=str(model_selection["configured_model"]),
        model=str(model_selection["resolved_model"]),
    )

    if requested_backend in {"openai", "gemini"}:
        provider = provider_registry[requested_backend]
        backend_status = probe_remote_provider(
            provider=provider,
            requested_backend=requested_backend,
            repo_root=repo_root,
            config=config,
            timeout_seconds=timeout_seconds,
        )
    elif requested_backend == "auto":
        for provider_name in ("openai", "gemini"):
            provider = provider_registry.get(provider_name)
            if provider is None:
                continue
            remote_status = probe_remote_provider(
                provider=provider,
                requested_backend=requested_backend,
                repo_root=repo_root,
                config=config,
                timeout_seconds=timeout_seconds,
            )
            if not backend_status.healthy and remote_status.healthy:
                backend_status = remote_status
                break

    raw_payload: dict[str, Any] | None = None
    transport = {"transport": "deterministic", "reason": "local-deterministic-fallback", "selected_backend": "codex"}
    degraded_reasons: list[str] = []
    result_status = "ok"
    transport_ran = False
    backend_used = "codex"
    validated = {
        "mermaid": deterministic_mermaid,
        "confidence": 0.72,
        "rationale": "Deterministic Mermaid fallback derived from workflow placeholders.",
    }

    try:
        if backend_status.healthy and backend_status.selected_backend == "ollama":
            transport_ran = True
            transport = run_ollama_hybrid(
                host=backend_status.host,
                model=backend_status.model,
                flow_name=HYBRID_FLOW_NAME,
                context_bundle=context_bundle,
                timeout_seconds=timeout_seconds,
            )
        elif backend_status.healthy and backend_status.selected_backend == "openai":
            transport_ran = True
            transport = run_openai_hybrid(
                provider=provider_registry["openai"],
                flow_name=HYBRID_FLOW_NAME,
                context_bundle=context_bundle,
                timeout_seconds=timeout_seconds,
            )
        elif backend_status.healthy and backend_status.selected_backend == "gemini":
            transport_ran = True
            transport = run_gemini_hybrid(
                provider=provider_registry["gemini"],
                flow_name=HYBRID_FLOW_NAME,
                context_bundle=context_bundle,
                timeout_seconds=timeout_seconds,
            )
        else:
            degraded_reasons = list(backend_status.reasons or ["selected-codex"])
    except HybridAssistError as exc:
        degraded_reasons = [exc.code]
        transport = {"transport": "fallback", "reason": exc.code, "selected_backend": "codex"}
    else:
        if transport_ran:
            raw_payload = transport.get("result_payload") if isinstance(transport.get("result_payload"), dict) else None
            candidate = validate_hybrid_result(HYBRID_FLOW_NAME, raw_payload or {}, {}, context_bundle=context_bundle)
            candidate["mermaid"] = _normalize_candidate_mermaid(
                kind_name=kind_name,
                candidate_mermaid=str(candidate.get("mermaid", "")),
                deterministic_mermaid=deterministic_mermaid,
            )
            safety_issues = _validate_mermaid_safety(kind_name, candidate["mermaid"])
            if safety_issues:
                degraded_reasons = safety_issues
                transport = {**transport, "safety_rejected": safety_issues}
            else:
                validated = candidate
                backend_used = backend_status.selected_backend

    if degraded_reasons:
        result_status = "degraded"
        validated = {
            "mermaid": deterministic_mermaid,
            "confidence": 0.72,
            "rationale": "Deterministic Mermaid fallback used after provider unavailability or Mermaid safety rejection.",
        }

    confidence = float(validated["confidence"])
    review_recommended = bool(degraded_reasons) or confidence < 0.7
    audit_path = (repo_root / audit_log).resolve()
    measurement_path = (repo_root / measurement_log).resolve()
    if not dry_run:
        append_jsonl_record(
            audit_path,
            build_hybrid_audit_record(
                flow_name=HYBRID_FLOW_NAME,
                result_status=result_status,
                backend_status=backend_status,
                context_bundle=context_bundle,
                raw_payload=raw_payload,
                validated_payload=validated,
                transport=transport,
                degraded_reasons=degraded_reasons,
                execution_result=None,
            ),
        )
        append_jsonl_record(
            measurement_path,
            build_measurement_record(
                flow_name=HYBRID_FLOW_NAME,
                backend_status=backend_status,
                result_status=result_status,
                confidence=confidence,
                degraded_reasons=degraded_reasons,
                review_recommended=review_recommended,
            ),
        )

    return {
        "flow": HYBRID_FLOW_NAME,
        "kind": kind_name,
        "backend_requested": requested_backend,
        "backend_used": backend_used,
        "result_status": result_status,
        "degraded_reasons": degraded_reasons,
        "mermaid": validated["mermaid"],
        "confidence": confidence,
        "rationale": validated["rationale"],
        "transport": transport,
        "audit_log": str(audit_path),
        "measurement_log": str(measurement_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Mermaid blocks for Logics workflow docs.")
    parser.add_argument("--kind", choices=("request", "backlog", "task"), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--values-json", default="{}", help="JSON object with template placeholder values.")
    parser.add_argument("--backend", choices=("auto", "ollama", "openai", "gemini", "codex"), default="auto")
    parser.add_argument("--model-profile")
    parser.add_argument("--model")
    parser.add_argument("--ollama-host")
    parser.add_argument("--timeout", type=float, default=HYBRID_TIMEOUT_SECONDS)
    parser.add_argument("--audit-log", default=DEFAULT_HYBRID_AUDIT_LOG)
    parser.add_argument("--measurement-log", default=DEFAULT_HYBRID_MEASUREMENT_LOG)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        values = json.loads(args.values_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid --values-json payload: {exc}") from exc
    if not isinstance(values, dict):
        raise SystemExit("--values-json must decode to an object.")

    payload = generate_mermaid(
        repo_root=Path.cwd(),
        kind_name=args.kind,
        title=args.title,
        values=values,
        requested_backend=args.backend,
        requested_model_profile=args.model_profile,
        requested_model=args.model,
        ollama_host=args.ollama_host,
        timeout_seconds=args.timeout,
        audit_log=args.audit_log,
        measurement_log=args.measurement_log,
        dry_run=args.dry_run,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["mermaid"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
