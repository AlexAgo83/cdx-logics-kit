from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from logics_flow_hybrid_runtime_core import *  # noqa: F401,F403



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
    execution_path_override: str | None = None,
    cache_hit: bool = False,
) -> dict[str, Any]:
    return build_measurement_record_impl(
        flow_name=flow_name,
        backend_status=backend_status,
        result_status=result_status,
        confidence=confidence,
        degraded_reasons=degraded_reasons,
        review_recommended=review_recommended,
        execution_path_override=execution_path_override,
        cache_hit=cache_hit,
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


__all__ = [name for name in globals() if not name.startswith("__")]
