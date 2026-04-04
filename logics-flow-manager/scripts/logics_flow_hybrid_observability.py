from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Callable


def append_jsonl_record_impl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl_records_impl(path: Path) -> tuple[list[dict[str, Any]], int]:
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


def build_hybrid_roi_report_impl(
    *,
    repo_root: Path,
    audit_log: Path,
    measurement_log: Path,
    recent_limit: int,
    window_days: int,
    schema_version: str,
    default_estimated_remote_tokens_per_local_run: int,
) -> dict[str, Any]:
    effective_recent_limit = max(1, recent_limit)
    effective_window_days = max(1, window_days)
    audit_records, audit_invalid_lines = load_jsonl_records_impl(audit_log)
    measurement_records, measurement_invalid_lines = load_jsonl_records_impl(measurement_log)
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
    estimated_remote_token_avoidance = local_runs_count * default_estimated_remote_tokens_per_local_run

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
        "schema_version": schema_version,
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
                "remote_tokens_per_local_run": default_estimated_remote_tokens_per_local_run,
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


def collect_git_snapshot_impl(repo_root: Path) -> dict[str, Any]:
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


def build_runtime_status_impl(
    *,
    repo_root: Path,
    requested_backend: str,
    requested_model: str | None,
    config: dict[str, Any] | None,
    host: str,
    model_profile: dict[str, Any],
    supported_model_profiles: dict[str, dict[str, Any]],
    model: str,
    timeout_seconds: float,
    claude_bridge_status: dict[str, Any],
    schema_version: str,
    flow_contracts: dict[str, dict[str, Any]],
    provider_registry: dict[str, Any],
    select_hybrid_backend: Callable[..., Any],
    probe_ollama_backend: Callable[..., Any],
    probe_remote_provider: Callable[..., Any],
    build_flow_backend_policy: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    backend = select_hybrid_backend(
        requested_backend=requested_backend,
        flow_name="diff-risk",
        repo_root=repo_root,
        config=config,
        requested_model=requested_model,
        host=host,
        model_profile=str(model_profile["name"]),
        model_family=str(model_profile["family"]),
        configured_model=str(model_profile["configured_model"]),
        model=model,
        timeout_seconds=timeout_seconds,
    )
    degraded_reasons = list(backend.reasons)
    claude_bridge_available = bool(claude_bridge_status.get("available"))
    provider_statuses: dict[str, Any] = {}
    for provider_name, provider in sorted(provider_registry.items()):
        if provider.execution_kind == "fallback":
            provider_statuses[provider_name] = {
                "name": provider.name,
                "enabled": provider.enabled,
                "healthy": provider.name in {"codex", "deterministic"},
                "selected_backend": provider.name,
                "credential_env": provider.credential_env,
                "credential_present": provider.credential_present,
                "endpoint": provider.endpoint,
                "model": provider.model,
                "reasons": [],
            }
            continue
        if provider.name == "ollama":
            status = probe_ollama_backend(
                requested_backend="auto",
                host=provider.endpoint,
                model_profile=provider.model_profile,
                model_family=provider.model_family,
                configured_model=provider.configured_model,
                model=provider.model,
                timeout_seconds=timeout_seconds,
            )
        else:
            status = probe_remote_provider(
                provider=provider,
                requested_backend="auto",
                timeout_seconds=timeout_seconds,
            )
        provider_statuses[provider_name] = {
            "name": provider.name,
            "enabled": provider.enabled,
            "healthy": status.healthy,
            "selected_backend": status.selected_backend,
            "credential_env": provider.credential_env,
            "credential_present": provider.credential_present,
            "endpoint": provider.endpoint,
            "model": provider.model,
            "reasons": list(status.reasons),
            "response_time_ms": status.response_time_ms,
            "version": status.version,
        }
    return {
        "schema_version": schema_version,
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
        "providers": provider_statuses,
        "flow_backend_policies": {
            flow: build_flow_backend_policy(flow)
            for flow in sorted(flow_contracts.keys())
        },
        "windows_safe_entrypoint": "python logics/skills/logics.py flow assist ...",
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


def build_hybrid_audit_record_impl(
    *,
    flow_name: str,
    result_status: str,
    backend_status: Any,
    context_bundle: dict[str, Any],
    raw_payload: dict[str, Any] | None,
    validated_payload: dict[str, Any],
    transport: dict[str, Any],
    degraded_reasons: list[str],
    execution_result: dict[str, Any] | None,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": schema_version,
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


def build_measurement_record_impl(
    *,
    flow_name: str,
    backend_status: Any,
    result_status: str,
    confidence: float | None,
    degraded_reasons: list[str],
    review_recommended: bool,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": schema_version,
        "flow": flow_name,
        "backend_requested": backend_status.requested_backend,
        "backend_used": backend_status.selected_backend,
        "result_status": result_status,
        "confidence": confidence,
        "degraded_reasons": degraded_reasons,
        "review_recommended": review_recommended,
    }
