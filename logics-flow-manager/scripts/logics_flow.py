#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from logics_flow_config import get_config_value, load_repo_config
from logics_flow_dispatcher import (
    DEFAULT_DISPATCH_AUDIT_LOG,
    DEFAULT_DISPATCH_CONTEXT_MODE,
    DEFAULT_DISPATCH_EXECUTION_MODE,
    DEFAULT_DISPATCH_PROFILE,
    DispatcherError,
    append_audit_record,
    build_audit_record,
    build_dispatcher_contract,
    extract_json_object,
    map_decision_to_command,
    run_ollama_dispatch,
    validate_dispatcher_decision,
)
from logics_flow_hybrid import (
    DEFAULT_HYBRID_AUDIT_LOG,
    DEFAULT_HYBRID_BACKEND,
    DEFAULT_HYBRID_HOST,
    DEFAULT_HYBRID_MEASUREMENT_LOG,
    DEFAULT_HYBRID_MODEL,
    DEFAULT_HYBRID_MODEL_PROFILE,
    DEFAULT_HYBRID_RESULT_CACHE,
    DEFAULT_HYBRID_RESULT_CACHE_TTL_SECONDS,
    DEFAULT_HYBRID_ROI_RECENT_LIMIT,
    DEFAULT_HYBRID_ROI_WINDOW_DAYS,
    DEFAULT_HYBRID_TIMEOUT_SECONDS,
    REQUESTED_BACKEND_CHOICES,
    HybridBackendStatus,
    HybridAssistError,
    apply_legacy_default_model,
    append_jsonl_record,
    build_hybrid_roi_report,
    build_flow_contract,
    build_hybrid_audit_record,
    build_measurement_record,
    build_runtime_status,
    build_shared_hybrid_contract,
    collect_git_snapshot,
    default_context_spec,
    execute_hybrid_backend,
    merge_hybrid_model_profiles,
    execute_commit_step,
    resolve_hybrid_model_selection,
    select_hybrid_backend,
    run_validation_commands,
)
from logics_flow_index import indexed_skill_packages, indexed_workflow_docs, load_runtime_index
from logics_flow_support import (
    ALLOWED_COMPLEXITIES,
    DOC_KINDS,
    REF_PREFIXES,
    STATUS_BY_KIND_DEFAULT,
    _append_section_bullets,
    _apply_decision_assessment,
    _assess_decision_framing,
    _auto_create_companion_docs,
    _build_template_values,
    _close_doc,
    _collect_docs_linking_ref,
    _collect_reference_items,
    _create_backlog_from_request,
    _create_task_from_backlog,
    _extract_refs,
    _find_repo_root,
    _is_doc_done,
    _mark_section_checkboxes_done,
    _parse_indicator,
    _parse_title_from_source,
    _print_decision_summary,
    _render_references_section,
    _render_template,
    _render_workflow_mermaid,
    _reserve_doc,
    _resolve_doc_path,
    _split_titles,
    _strip_mermaid_blocks,
    _template_path,
    _write,
    refresh_ai_context_text,
    refresh_workflow_mermaid_signature_file,
)
from logics_flow_models import WorkflowDocModel, parse_workflow_doc
from logics_flow_mutations import build_planned_mutation
from logics_flow_registry import (
    CURRENT_WORKFLOW_SCHEMA_VERSION,
    GOVERNANCE_PROFILES,
    WORKFLOW_CONVENTIONS,
    build_release_metadata,
)
from logics_flow_transactions import TransactionWrite, apply_transaction

CLAUDE_BRIDGE_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "id": "hybrid-assist",
        "command_path": ".claude/commands/logics-assist.md",
        "agent_path": ".claude/agents/logics-hybrid-delivery-assistant.md",
    },
    {
        "id": "flow-manager",
        "command_path": ".claude/commands/logics-flow.md",
        "agent_path": ".claude/agents/logics-flow-manager.md",
    },
)


def _rel(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _rdict(v: object) -> dict[str, object]:
    """Narrow an object-typed payload value to dict[str, object] for attribute access."""
    return v if isinstance(v, dict) else {}


def _git_capture(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _git_current_branch(repo_root: Path) -> str | None:
    completed = _git_capture(repo_root, "branch", "--show-current")
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    return branch or None


def _git_local_branch_exists(repo_root: Path, branch_name: str) -> bool:
    completed = _git_capture(repo_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}")
    return completed.returncode == 0


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool | None:
    completed = _git_capture(repo_root, "merge-base", "--is-ancestor", ancestor, descendant)
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None


def _release_branch_status(repo_root: Path, branch_name: str = "release") -> dict[str, object]:
    current_branch = _git_current_branch(repo_root)
    status: dict[str, object] = {"name": branch_name, "exists": False}
    if current_branch:
        status["current_branch"] = current_branch

    if not _git_local_branch_exists(repo_root, branch_name):
        return status

    status["exists"] = True
    if current_branch == branch_name:
        status["needs_update"] = False
        return status

    release_contains_head = _git_is_ancestor(repo_root, "HEAD", branch_name)
    release_is_ancestor = _git_is_ancestor(repo_root, branch_name, "HEAD")
    if release_contains_head is None or release_is_ancestor is None:
        status["needs_update"] = False
        return status

    status["needs_update"] = not release_contains_head
    status["can_fast_forward"] = release_is_ancestor and not release_contains_head

    if not status["needs_update"]:
        return status

    source_branch = current_branch or "current branch"
    if status["can_fast_forward"]:
        quoted_release = shlex.quote(branch_name)
        quoted_source = shlex.quote(source_branch)
        status["suggestion"] = (
            f"Branch '{branch_name}' is behind '{source_branch}'. Consider updating it before publishing."
        )
        status["command"] = (
            f"git switch {quoted_release} && git merge --ff-only {quoted_source}"
            f" && git switch {quoted_source} && git push origin {quoted_release}"
        )
    else:
        status["suggestion"] = (
            f"Branch '{branch_name}' does not contain '{source_branch}'. Review its divergence before publishing."
        )

    return status


def _effective_config(repo_root: Path) -> tuple[dict[str, object], Path | None]:
    return load_repo_config(repo_root)


def _next_patch_release_version(version: str) -> str | None:
    parts = version.split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return None
    return f"{major}.{minor}.{patch + 1}"


def _update_release_version_artifacts(repo_root: Path, version: str) -> list[str]:
    updated_paths: list[str] = []

    package_json_path = repo_root / "package.json"
    if package_json_path.is_file():
        package_payload = json.loads(package_json_path.read_text(encoding="utf-8"))
        if package_payload.get("version") != version:
            package_payload["version"] = version
            package_json_path.write_text(json.dumps(package_payload, indent=2) + "\n", encoding="utf-8")
            updated_paths.append(_rel(repo_root, package_json_path))

    package_lock_path = repo_root / "package-lock.json"
    if package_lock_path.is_file():
        package_lock_payload = json.loads(package_lock_path.read_text(encoding="utf-8"))
        changed = False
        if package_lock_payload.get("version") != version:
            package_lock_payload["version"] = version
            changed = True
        packages_root = package_lock_payload.get("packages")
        if isinstance(packages_root, dict):
            root_entry = packages_root.get("")
            if isinstance(root_entry, dict) and root_entry.get("version") != version:
                root_entry["version"] = version
                changed = True
        if changed:
            package_lock_path.write_text(json.dumps(package_lock_payload, indent=2) + "\n", encoding="utf-8")
            updated_paths.append(_rel(repo_root, package_lock_path))

    version_path = repo_root / "VERSION"
    current_version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else None
    if current_version != version:
        version_path.write_text(f"{version}\n", encoding="utf-8")
        updated_paths.append(_rel(repo_root, version_path))

    return updated_paths


def _load_workflow_docs(repo_root: Path, *, config: dict[str, object] | None = None, force_reindex: bool = False) -> dict[str, WorkflowDocModel]:
    effective_config = config or _effective_config(repo_root)[0]
    docs, _stats = indexed_workflow_docs(repo_root, config=effective_config, force=force_reindex)
    return docs


def _resolve_target_docs(repo_root: Path, sources: list[str]) -> list[tuple[str, Path]]:
    if not sources:
        targets: list[tuple[str, Path]] = []
        for kind_name, kind in DOC_KINDS.items():
            directory = repo_root / kind.directory
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob(f"{kind.prefix}_*.md")):
                targets.append((kind_name, path))
        return targets

    resolved: list[tuple[str, Path]] = []
    for source in sources:
        candidate = (repo_root / source).resolve()
        if candidate.is_file():
            for kind_name, kind in DOC_KINDS.items():
                if candidate.parent == (repo_root / kind.directory).resolve():
                    resolved.append((kind_name, candidate))
                    break
            continue
        for kind_name, kind in DOC_KINDS.items():
            path = repo_root / kind.directory / f"{source}.md"
            if path.is_file():
                resolved.append((kind_name, path))
                break
        else:
            raise SystemExit(f"Could not resolve workflow doc target `{source}`.")
    return resolved


def _git_changed_paths(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--relative=."],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _context_profile_limit(profile: str) -> int:
    return {"tiny": 2, "normal": 4, "deep": 8}[profile]


def _workflow_neighborhood(seed: WorkflowDocModel, docs: dict[str, WorkflowDocModel]) -> list[WorkflowDocModel]:
    ordered: list[WorkflowDocModel] = [seed]
    seen = {seed.ref}
    linked_refs = []
    for values in seed.refs.values():
        linked_refs.extend(values)
    for ref in linked_refs:
        candidate = docs.get(ref)
        if candidate is None or candidate.ref in seen:
            continue
        ordered.append(candidate)
        seen.add(candidate.ref)
    for candidate in docs.values():
        if candidate.ref in seen:
            continue
        if seed.ref in sum(candidate.refs.values(), []):
            ordered.append(candidate)
            seen.add(candidate.ref)
    return ordered


def _context_pack_doc_entry(doc: WorkflowDocModel, mode: str) -> dict[str, object]:
    entry = {
        "ref": doc.ref,
        "kind": doc.kind,
        "path": doc.path,
        "title": doc.title,
        "status": doc.indicators.get("Status", ""),
        "schema_version": doc.schema_version,
        "ai_context": doc.ai_context,
        "linked_refs": {prefix: refs for prefix, refs in doc.refs.items() if refs},
    }
    if mode == "summary-only":
        return entry

    section_names = {
        "request": ["Needs", "Acceptance criteria"],
        "backlog": ["Problem", "Acceptance criteria"],
        "task": ["Context", "Validation"],
    }.get(doc.kind, [])
    entry["sections"] = {
        heading: [line for line in doc.sections.get(heading, []) if line.strip()][:6]
        for heading in section_names
    }
    return entry


def _build_context_pack(
    repo_root: Path,
    seed_ref: str,
    *,
    mode: str,
    profile: str,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    docs = _load_workflow_docs(repo_root, config=config)
    seed = docs.get(seed_ref)
    if seed is None:
        raise SystemExit(f"Unknown workflow ref `{seed_ref}`.")
    ordered = _workflow_neighborhood(seed, docs)[: _context_profile_limit(profile)]
    pack_docs = [_context_pack_doc_entry(doc, mode) for doc in ordered]
    changed_paths = _git_changed_paths(repo_root) if mode == "diff-first" else []
    return {
        "ref": seed_ref,
        "mode": mode,
        "profile": profile,
        "budgets": {
            "max_docs": _context_profile_limit(profile),
        },
        "changed_paths": changed_paths,
        "docs": pack_docs,
        "estimates": {
            "doc_count": len(pack_docs),
            "char_count": sum(len(json.dumps(entry, sort_keys=True)) for entry in pack_docs),
        },
    }


def _schema_status(repo_root: Path, targets: list[str]) -> dict[str, object]:
    docs = [parse_workflow_doc(path, repo_root=repo_root) for _kind, path in _resolve_target_docs(repo_root, targets)]
    counts: dict[str, int] = {}
    outdated: list[str] = []
    missing: list[str] = []
    for doc in docs:
        schema_version = doc.indicators.get("Schema version", "")
        if not schema_version:
            missing.append(doc.path)
            schema_version = "(missing)"
        counts[schema_version] = counts.get(schema_version, 0) + 1
        if schema_version not in {"(missing)", CURRENT_WORKFLOW_SCHEMA_VERSION}:
            outdated.append(doc.path)
    return {
        "current_schema_version": CURRENT_WORKFLOW_SCHEMA_VERSION,
        "counts": dict(sorted(counts.items())),
        "missing": missing,
        "outdated": outdated,
        "doc_count": len(docs),
    }


def _ensure_schema_version_text(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    heading_idx = next((idx for idx, line in enumerate(lines) if line.startswith("## ")), None)
    if heading_idx is None:
        return text, False
    existing_idx, existing_value = _parse_indicator(lines, "Schema version")
    rendered = f"> Schema version: {CURRENT_WORKFLOW_SCHEMA_VERSION}"
    if existing_idx is not None:
        if existing_value == CURRENT_WORKFLOW_SCHEMA_VERSION:
            return text, False
        lines[existing_idx] = rendered
    else:
        insert_at = heading_idx + 1
        while insert_at < len(lines) and lines[insert_at].lstrip().startswith(">"):
            insert_at += 1
        lines.insert(insert_at, rendered)
    refreshed = "\n".join(lines).rstrip() + "\n"
    return refreshed, refreshed != text


def _graph_payload(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    docs = _load_workflow_docs(repo_root, config=config)
    nodes = []
    edges = []
    for doc in docs.values():
        nodes.append(
            {
                "ref": doc.ref,
                "kind": doc.kind,
                "title": doc.title,
                "path": doc.path,
                "status": doc.indicators.get("Status", ""),
            }
        )
        for refs in doc.refs.values():
            for ref in refs:
                if ref in docs:
                    edges.append({"from": doc.ref, "to": ref})
    return {"nodes": nodes, "edges": edges}


def _skill_packages(repo_root: Path, *, config: dict[str, object] | None = None, force_reindex: bool = False) -> list[dict[str, object]]:
    effective_config = config or _effective_config(repo_root)[0]
    packages, _stats = indexed_skill_packages(repo_root, config=effective_config, force=force_reindex)
    return [package.to_dict() for package in packages]


def _validate_skills_payload(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    packages = _skill_packages(repo_root, config=config)
    issues = [
        {
            "skill": package["name"],
            "path": package["path"],
            "issues": package["issues"],
        }
        for package in packages
        if package["issues"]
    ]
    return {
        "skill_count": len(packages),
        "packages": packages,
        "issues": issues,
        "ok": not issues,
    }


def _export_registry_payload(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    skills_root = repo_root / "logics" / "skills"
    return {
        "schema_version": CURRENT_WORKFLOW_SCHEMA_VERSION,
        "conventions": WORKFLOW_CONVENTIONS,
        "governance_profiles": GOVERNANCE_PROFILES,
        "skills": _skill_packages(repo_root, config=config),
        "releases": [release.__dict__ for release in build_release_metadata(skills_root)],
    }


def _doctor_payload(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    for directory in ("logics/request", "logics/backlog", "logics/tasks", "logics/skills"):
        path = repo_root / directory
        if not path.exists():
            issues.append(
                {
                    "code": "missing_directory",
                    "path": directory,
                    "message": f"Missing required directory `{directory}`.",
                    "remediation": f"Create `{directory}` or run the bootstrap flow before using the kit.",
                }
            )

    validation = _validate_skills_payload(repo_root, config=config)
    for issue in validation["issues"]:
        issues.append(
            {
                "code": "invalid_skill_package",
                "path": issue["path"],
                "message": "; ".join(issue["issues"]),
                "remediation": "Repair SKILL.md frontmatter and agents/openai.yaml so the skill package matches the kit contract.",
            }
        )

    schema = _schema_status(repo_root, [])
    for path in schema["missing"]:
        issues.append(
            {
                "code": "missing_schema_version",
                "path": path,
                "message": "Workflow doc is missing a schema version indicator.",
                "remediation": "Run `logics_flow.py sync migrate-schema` to normalize the workflow corpus.",
            }
        )
    return {
        "ok": not issues,
        "issues": issues,
        "skill_validation": validation,
        "schema_status": schema,
    }


def _claude_bridge_status(repo_root: Path) -> dict[str, object]:
    detected_variants: list[str] = []
    for variant in CLAUDE_BRIDGE_VARIANTS:
        command_path = repo_root / variant["command_path"]
        agent_path = repo_root / variant["agent_path"]
        if command_path.is_file() and agent_path.is_file():
            detected_variants.append(variant["id"])
    preferred_variant = detected_variants[0] if detected_variants else None
    return {
        "available": bool(detected_variants),
        "preferred_variant": preferred_variant,
        "detected_variants": detected_variants,
        "supported_variants": [variant["id"] for variant in CLAUDE_BRIDGE_VARIANTS],
    }


def _claude_bridge_available(repo_root: Path) -> bool:
    return bool(_claude_bridge_status(repo_root)["available"])


def _benchmark_payload(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    started = time.perf_counter()
    packages = _skill_packages(repo_root, config=config)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "skill_count": len(packages),
        "duration_ms": duration_ms,
        "average_ms_per_skill": round(duration_ms / len(packages), 3) if packages else 0.0,
    }


def _dispatcher_graph_slice(repo_root: Path, seed_ref: str, *, config: dict[str, object] | None = None) -> dict[str, object]:
    docs = _load_workflow_docs(repo_root, config=config)
    seed = docs.get(seed_ref)
    if seed is None:
        raise SystemExit(f"Unknown workflow ref `{seed_ref}`.")
    neighborhood = _workflow_neighborhood(seed, docs)
    allowed = {doc.ref for doc in neighborhood}
    nodes = [
        {
            "ref": doc.ref,
            "kind": doc.kind,
            "title": doc.title,
            "path": doc.path,
            "status": doc.indicators.get("Status", ""),
        }
        for doc in neighborhood
    ]
    edges = []
    for doc in neighborhood:
        for refs in doc.refs.values():
            for ref in refs:
                if ref in allowed:
                    edges.append({"from": doc.ref, "to": ref})
    return {"seed_ref": seed_ref, "nodes": nodes, "edges": edges}


def _dispatcher_registry_summary(repo_root: Path, *, config: dict[str, object] | None = None) -> dict[str, object]:
    payload = _export_registry_payload(repo_root, config=config)
    return {
        "schema_version": payload["schema_version"],
        "governance_profiles": payload["governance_profiles"],
        "skill_count": len(payload["skills"]),
        "skill_names": [skill["name"] for skill in payload["skills"]],
        "release_versions": [release["version"] for release in payload["releases"]],
    }


def _build_dispatcher_context(
    repo_root: Path,
    ref: str,
    *,
    mode: str,
    profile: str,
    include_graph: bool,
    include_registry: bool,
    include_doctor: bool,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    bundle: dict[str, object] = {
        "schema_version": CURRENT_WORKFLOW_SCHEMA_VERSION,
        "seed_ref": ref,
        "default_execution_mode": DEFAULT_DISPATCH_EXECUTION_MODE,
        "contract": build_dispatcher_contract(),
        "context_pack": _build_context_pack(repo_root, ref, mode=mode, profile=profile, config=config),
    }
    if include_graph:
        bundle["graph"] = _dispatcher_graph_slice(repo_root, ref, config=config)
    if include_registry:
        bundle["registry"] = _dispatcher_registry_summary(repo_root, config=config)
    if include_doctor:
        doctor_payload = _doctor_payload(repo_root, config=config)
        bundle["doctor"] = {
            "ok": doctor_payload["ok"],
            "issue_count": len(doctor_payload["issues"]),
            "issues": doctor_payload["issues"],
        }
    return bundle


def _hybrid_default_backend(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_backend", default=DEFAULT_HYBRID_BACKEND))


def _hybrid_default_model(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_model", default=DEFAULT_HYBRID_MODEL))


def _hybrid_default_model_profile(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "default_model_profile", default=DEFAULT_HYBRID_MODEL_PROFILE))


def _hybrid_model_profiles(config: dict[str, object]) -> dict[str, dict[str, object]]:
    configured = merge_hybrid_model_profiles(get_config_value(config, "hybrid_assist", "model_profiles", default={}))
    return apply_legacy_default_model(
        configured,
        default_profile=_hybrid_default_model_profile(config),
        legacy_default_model=(
            str(get_config_value(config, "hybrid_assist", "default_model", default="")).strip() or None
            if _hybrid_default_model_profile(config) == DEFAULT_HYBRID_MODEL_PROFILE
            else None
        ),
    )


def _hybrid_model_selection(
    config: dict[str, object],
    *,
    requested_model_profile: str | None,
    requested_model: str | None,
) -> dict[str, object]:
    profiles = _hybrid_model_profiles(config)
    selection = resolve_hybrid_model_selection(
        configured_profiles=profiles,
        default_profile=_hybrid_default_model_profile(config),
        requested_profile=requested_model_profile,
        requested_model=requested_model,
    )
    selection["supported_profiles"] = profiles
    return selection


def _hybrid_default_host(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "ollama_host", default=DEFAULT_HYBRID_HOST))


def _hybrid_default_timeout(config: dict[str, object]) -> float:
    return float(get_config_value(config, "hybrid_assist", "timeout_seconds", default=DEFAULT_HYBRID_TIMEOUT_SECONDS))


def _hybrid_audit_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "audit_log", default=DEFAULT_HYBRID_AUDIT_LOG))


def _hybrid_measurement_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "measurement_log", default=DEFAULT_HYBRID_MEASUREMENT_LOG))


def _hybrid_result_cache_enabled(config: dict[str, object]) -> bool:
    return bool(get_config_value(config, "hybrid_assist", "result_cache", "enabled", default=True))


def _hybrid_result_cache_path(config: dict[str, object]) -> str:
    return str(get_config_value(config, "hybrid_assist", "result_cache", "path", default=DEFAULT_HYBRID_RESULT_CACHE))


def _hybrid_result_cache_ttl_seconds(config: dict[str, object]) -> int:
    return max(
        1,
        int(
            get_config_value(
                config,
                "hybrid_assist",
                "result_cache",
                "ttl_seconds",
                default=DEFAULT_HYBRID_RESULT_CACHE_TTL_SECONDS,
            )
        ),
    )


def _load_hybrid_result_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    entries = payload.get("entries") if isinstance(payload, dict) else {}
    return {"entries": entries if isinstance(entries, dict) else {}}


def _write_hybrid_result_cache(path: Path, entries: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": entries}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prune_hybrid_result_cache_entries(entries: dict[str, object], *, now_ts: float) -> dict[str, object]:
    kept: dict[str, object] = {}
    for key, value in entries.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        expires_at = value.get("expires_at")
        if not isinstance(expires_at, (int, float)) or float(expires_at) <= now_ts:
            continue
        if not isinstance(value.get("validated_payload"), dict):
            continue
        kept[key] = value
    return kept


def _build_hybrid_result_cache_key(
    *,
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    context_bundle: dict[str, object],
) -> tuple[str, str]:
    git_snapshot = context_bundle.get("git_snapshot", {})
    context_pack = context_bundle.get("context_pack", {})
    fingerprint_payload = {
        "seed_ref": context_bundle.get("seed_ref"),
        "context_profile": context_bundle.get("context_profile"),
        "mode": context_pack.get("mode") if isinstance(context_pack, dict) else None,
        "profile": context_pack.get("profile") if isinstance(context_pack, dict) else None,
        "requested_backend": requested_backend,
        "model_profile": model_selection.get("name"),
        "resolved_model": model_selection.get("resolved_model"),
        "changed_paths": list(git_snapshot.get("changed_paths", [])) if isinstance(git_snapshot, dict) else [],
        "unstaged_diff_stat": list(git_snapshot.get("unstaged_diff_stat", [])) if isinstance(git_snapshot, dict) else [],
        "staged_diff_stat": list(git_snapshot.get("staged_diff_stat", [])) if isinstance(git_snapshot, dict) else [],
    }
    diff_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_key = hashlib.sha256(f"{flow_name}:{diff_fingerprint}".encode("utf-8")).hexdigest()
    return cache_key, diff_fingerprint


def _read_hybrid_result_cache_entry(
    *,
    repo_root: Path,
    config: dict[str, object],
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    context_bundle: dict[str, object],
    dry_run: bool,
) -> tuple[Path, str, str, dict[str, object] | None]:
    cache_path = (repo_root / _hybrid_result_cache_path(config)).resolve()
    cache_key, diff_fingerprint = _build_hybrid_result_cache_key(
        flow_name=flow_name,
        requested_backend=requested_backend,
        model_selection=model_selection,
        context_bundle=context_bundle,
    )
    if not _hybrid_result_cache_enabled(config):
        return cache_path, cache_key, diff_fingerprint, None
    cache_payload = _load_hybrid_result_cache(cache_path)
    entries = cache_payload["entries"] if isinstance(cache_payload, dict) else {}
    now_ts = time.time()
    pruned_entries = _prune_hybrid_result_cache_entries(entries if isinstance(entries, dict) else {}, now_ts=now_ts)
    if not dry_run and pruned_entries != entries:
        _write_hybrid_result_cache(cache_path, pruned_entries)
    cached_entry = pruned_entries.get(cache_key) if isinstance(pruned_entries.get(cache_key), dict) else None
    return cache_path, cache_key, diff_fingerprint, cached_entry


def _write_hybrid_result_cache_entry(
    *,
    cache_path: Path,
    cache_key: str,
    diff_fingerprint: str,
    ttl_seconds: int,
    flow_name: str,
    requested_backend: str,
    model_selection: dict[str, object],
    backend_status: HybridBackendStatus,
    result_status: str,
    raw_payload: dict[str, object] | None,
    validated_payload: dict[str, object],
    transport: dict[str, object],
    confidence: float | None,
    review_recommended: bool,
) -> None:
    cache_payload = _load_hybrid_result_cache(cache_path)
    entries = cache_payload["entries"] if isinstance(cache_payload, dict) else {}
    now_ts = time.time()
    pruned_entries = _prune_hybrid_result_cache_entries(entries if isinstance(entries, dict) else {}, now_ts=now_ts)
    pruned_entries[cache_key] = {
        "flow": flow_name,
        "diff_fingerprint": diff_fingerprint,
        "stored_at": now_ts,
        "expires_at": now_ts + ttl_seconds,
        "requested_backend": requested_backend,
        "backend_status": backend_status.to_dict(),
        "result_status": result_status,
        "raw_payload": raw_payload,
        "validated_payload": validated_payload,
        "transport": transport,
        "confidence": confidence,
        "review_recommended": review_recommended,
        "active_model_profile": {
            "name": model_selection["name"],
            "family": model_selection["family"],
            "configured_model": model_selection["configured_model"],
            "resolved_model": model_selection["resolved_model"],
            "description": model_selection["description"],
            "example_tags": model_selection["example_tags"],
        },
    }
    _write_hybrid_result_cache(cache_path, pruned_entries)


def _cached_backend_status(cached_entry: dict[str, object], requested_backend: str) -> HybridBackendStatus:
    cached_status = cached_entry.get("backend_status") if isinstance(cached_entry, dict) else {}
    status_dict = cached_status if isinstance(cached_status, dict) else {}
    return HybridBackendStatus(
        requested_backend=requested_backend,
        selected_backend=str(status_dict.get("selected_backend", "codex")),
        host=str(status_dict.get("host", DEFAULT_HYBRID_HOST)),
        model_profile=str(status_dict.get("model_profile", DEFAULT_HYBRID_MODEL_PROFILE)),
        model_family=str(status_dict.get("model_family", "")),
        configured_model=str(status_dict.get("configured_model", DEFAULT_HYBRID_MODEL)),
        model=str(status_dict.get("model", DEFAULT_HYBRID_MODEL)),
        ollama_reachable=bool(status_dict.get("ollama_reachable", False)),
        model_available=bool(status_dict.get("model_available", True)),
        healthy=True,
        reasons=[],
        response_time_ms=None,
        version=None,
        selection_reason="cache-hit",
        policy_mode=status_dict.get("policy_mode"),
    )


LOW_RISK_GENERATED_PATHS = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "Cargo.lock",
    "Pipfile.lock",
    "poetry.lock",
    "composer.lock",
}


def _is_low_risk_generated_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    lowered = normalized.lower()
    return (
        filename in LOW_RISK_GENERATED_PATHS
        or ".generated." in lowered
        or lowered.endswith(".snap")
        or lowered.startswith("dist/")
        or lowered.startswith("build/")
    )


def _is_schema_or_migration_path(path: str) -> bool:
    lowered = path.strip().replace("\\", "/").lower()
    return (
        "/migrations/" in lowered
        or lowered.startswith("migrations/")
        or "/migration/" in lowered
        or lowered.startswith("migration/")
        or lowered.endswith("schema.prisma")
        or lowered.endswith("schema.sql")
        or lowered.endswith("/schema.ts")
        or lowered.endswith("/schema.js")
        or "/db/schema" in lowered
        or "/alembic/" in lowered
    )


def _deterministic_preclassified_result(flow_name: str, context_bundle: dict[str, object]) -> dict[str, object] | None:
    if flow_name not in {"diff-risk", "windows-compat-risk"}:
        return None
    git_snapshot = context_bundle.get("git_snapshot", {})
    changed_paths = list(git_snapshot.get("changed_paths", [])) if isinstance(git_snapshot, dict) else []
    if not changed_paths:
        return {
            "reason": "empty-diff",
            "validated": {
                "risk": "low",
                "summary": "Deterministic pre-classifier marked the empty diff as low risk.",
                "drivers": ["No changed paths were detected in the working tree."],
                "confidence": 0.97,
                "rationale": "An empty diff does not require AI classification.",
            },
        }
    if any(_is_schema_or_migration_path(path) for path in changed_paths):
        return {
            "reason": "schema-or-migration",
            "validated": {
                "risk": "high",
                "summary": "Deterministic pre-classifier escalated the diff because schema or migration files changed.",
                "drivers": ["The change surface includes schema or migration files that require careful review."],
                "confidence": 0.95,
                "rationale": "Schema and migration changes are treated as high risk without an AI round-trip.",
            },
        }
    if all(_is_low_risk_generated_path(path) for path in changed_paths):
        return {
            "reason": "lock-or-generated-only",
            "validated": {
                "risk": "low",
                "summary": "Deterministic pre-classifier marked the diff as low risk because it only touches lock or generated files.",
                "drivers": ["Only lock-file or generated-artifact paths changed."],
                "confidence": 0.94,
                "rationale": "Lock-file-only and generated-only diffs are handled deterministically before any AI dispatch.",
            },
        }
    return None


def _prepare_hybrid_context_bundle(
    repo_root: Path,
    *,
    flow_name: str,
    ref: str | None,
    intent: str | None = None,
    context_mode: str | None,
    profile: str,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    audit_log: str,
    measurement_log: str,
    config: dict[str, object],
) -> tuple[dict[str, object], dict[str, object] | None]:
    context_bundle = _build_hybrid_context(
        repo_root,
        flow_name,
        ref=ref,
        intent=intent,
        context_mode=context_mode,
        profile=profile,
        include_graph=include_graph,
        include_registry=include_registry,
        include_doctor=include_doctor,
        config=config,
    )
    context_bundle["repo_root"] = str(repo_root)
    validation_payload = None
    if flow_name in {"validation-summary", "doc-consistency", "review-checklist"}:
        validation_payload = _hybrid_validation_payload(repo_root)
        context_bundle["validation_payload"] = validation_payload
    if flow_name == "hybrid-insights-explainer":
        context_bundle["roi_report"] = build_hybrid_roi_report(
            repo_root=repo_root,
            audit_log=(repo_root / audit_log).resolve(),
            measurement_log=(repo_root / measurement_log).resolve(),
        )
    return context_bundle, validation_payload


def _resolve_runtime_context_profile(
    *,
    flow_name: str,
    requested_profile: str | None,
    backend_status: HybridBackendStatus,
) -> tuple[str, str | None, str]:
    resolved_profile = requested_profile or str(default_context_spec(flow_name)["profile"])
    if flow_name != "handoff-packet":
        return resolved_profile, None, resolved_profile
    if requested_profile == "deep":
        return resolved_profile, None, resolved_profile
    if resolved_profile != "deep":
        return resolved_profile, None, resolved_profile
    if backend_status.selected_backend not in {"openai", "gemini", "codex"}:
        return resolved_profile, None, resolved_profile
    return "normal", "profile-downgrade", resolved_profile


def _deterministic_backend_status(
    *,
    requested_backend: str,
    model_selection: dict[str, object],
) -> HybridBackendStatus:
    return HybridBackendStatus(
        requested_backend=requested_backend,
        selected_backend="deterministic",
        host=DEFAULT_HYBRID_HOST,
        model_profile=str(model_selection["name"]),
        model_family=str(model_selection["family"]),
        configured_model=str(model_selection["configured_model"]),
        model=str(model_selection["resolved_model"]),
        ollama_reachable=False,
        model_available=True,
        healthy=True,
        reasons=[],
        response_time_ms=None,
        version=None,
        selection_reason="deterministic-preclassified",
        policy_mode=None,
    )


def _build_hybrid_context(
    repo_root: Path,
    flow_name: str,
    *,
    ref: str | None,
    intent: str | None = None,
    context_mode: str | None,
    profile: str | None,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    config: dict[str, object],
) -> dict[str, object]:
    spec = default_context_spec(flow_name)
    resolved_mode = context_mode or spec["mode"]
    resolved_profile = profile or spec["profile"]
    resolved_graph = spec["include_graph"] if include_graph is None else include_graph
    resolved_registry = spec["include_registry"] if include_registry is None else include_registry
    resolved_doctor = spec["include_doctor"] if include_doctor is None else include_doctor

    bundle: dict[str, object] = {
        "schema_version": CURRENT_WORKFLOW_SCHEMA_VERSION,
        "assist_schema_version": build_shared_hybrid_contract()["schema_version"],
        "flow": flow_name,
        "seed_ref": ref,
        "context_profile": {
            "mode": resolved_mode,
            "profile": resolved_profile,
            "include_graph": resolved_graph,
            "include_registry": resolved_registry,
            "include_doctor": resolved_doctor,
        },
        "contract": build_flow_contract(flow_name),
        "git_snapshot": collect_git_snapshot(repo_root),
        "claude_bridge": _claude_bridge_status(repo_root),
        "claude_bridge_available": _claude_bridge_available(repo_root),
    }
    if ref:
        bundle["context_pack"] = _build_context_pack(repo_root, ref, mode=resolved_mode, profile=resolved_profile, config=config)
        if resolved_graph:
            bundle["graph"] = _dispatcher_graph_slice(repo_root, ref, config=config)
    else:
        bundle["context_pack"] = {
            "ref": None,
            "mode": resolved_mode,
            "profile": resolved_profile,
            "docs": [],
            "budgets": {"max_docs": 0},
            "changed_paths": bundle["git_snapshot"]["changed_paths"],
            "estimates": {"doc_count": 0, "char_count": 0},
        }
    normalized_intent = " ".join(str(intent or "").split()).strip()
    if normalized_intent:
        bundle["operator_input"] = {"intent": normalized_intent}
    if resolved_registry:
        bundle["registry"] = _dispatcher_registry_summary(repo_root, config=config)
    if resolved_doctor:
        doctor_payload = _doctor_payload(repo_root, config=config)
        bundle["doctor"] = {
            "ok": doctor_payload["ok"],
            "issue_count": len(doctor_payload["issues"]),
            "issues": doctor_payload["issues"],
        }
    return bundle


def _hybrid_validation_payload(repo_root: Path) -> dict[str, object]:
    commands = [
        [sys.executable, str(Path(__file__).resolve().parents[2] / "logics.py"), "lint", "--format", "json"],
        [sys.executable, str(Path(__file__).resolve().parents[2] / "logics.py"), "audit", "--group-by-doc", "--format", "json"],
        [sys.executable, str(Path(__file__).resolve().parents[2] / "logics.py"), "doctor", "--format", "json"],
    ]
    return run_validation_commands(repo_root, commands)


def cmd_assist_runtime_status(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    model_selection = _hybrid_model_selection(
        config,
        requested_model_profile=getattr(args, "model_profile", None),
        requested_model=args.model,
    )
    payload = build_runtime_status(
        repo_root=repo_root,
        requested_backend=args.backend or _hybrid_default_backend(config),
        requested_model=args.model,
        config=config,
        host=args.ollama_host or _hybrid_default_host(config),
        model_profile=model_selection,
        supported_model_profiles=model_selection["supported_profiles"],
        model=str(model_selection["resolved_model"]),
        timeout_seconds=args.timeout or _hybrid_default_timeout(config),
        claude_bridge_status=_claude_bridge_status(repo_root),
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "runtime-status"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_hybrid_context(
        repo_root,
        args.flow_name,
        ref=getattr(args, "ref", None),
        context_mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "context"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_roi_report(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    audit_path = (repo_root / (args.audit_log or _hybrid_audit_log(config))).resolve()
    measurement_path = (repo_root / (args.measurement_log or _hybrid_measurement_log(config))).resolve()
    payload = build_hybrid_roi_report(
        repo_root=repo_root,
        audit_log=audit_path,
        measurement_log=measurement_path,
        recent_limit=args.recent_limit,
        window_days=args.window_days,
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "roi-report"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _run_hybrid_assist(
    repo_root: Path,
    *,
    flow_name: str,
    ref: str | None,
    intent: str | None = None,
    requested_backend: str,
    requested_model_profile: str | None,
    requested_model: str | None,
    ollama_host: str,
    timeout_seconds: float,
    context_mode: str | None,
    profile: str | None,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    execution_mode: str,
    audit_log: str,
    measurement_log: str,
    config: dict[str, object],
    dry_run: bool,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    normalized_intent = " ".join(str(intent or "").split()).strip()
    if flow_name == "request-draft" and not normalized_intent:
        raise SystemExit("`request-draft` requires `--intent`.")
    if flow_name == "spec-first-pass" and not ref:
        raise SystemExit("`spec-first-pass` requires a backlog ref.")
    if flow_name == "backlog-groom" and not ref:
        raise SystemExit("`backlog-groom` requires a request ref.")
    docs_by_ref = _load_workflow_docs(repo_root, config=config)
    model_selection = _hybrid_model_selection(
        config,
        requested_model_profile=requested_model_profile,
        requested_model=requested_model,
    )
    resolved_profile = profile or str(default_context_spec(flow_name)["profile"])
    context_bundle, validation_payload = _prepare_hybrid_context_bundle(
        repo_root,
        flow_name=flow_name,
        ref=ref,
        intent=normalized_intent or None,
        context_mode=context_mode,
        profile=resolved_profile,
        include_graph=include_graph,
        include_registry=include_registry,
        include_doctor=include_doctor,
        audit_log=audit_log,
        measurement_log=measurement_log,
        config=config,
    )
    preclassified_result = _deterministic_preclassified_result(flow_name, context_bundle)
    profile_adjustment_reason: str | None = None

    if preclassified_result is not None:
        backend_status = _deterministic_backend_status(
            requested_backend=requested_backend,
            model_selection=model_selection,
        )
        degraded_reasons: list[str] = []
        raw_payload = dict(preclassified_result["validated"])
        transport = {
            "transport": "deterministic",
            "reason": "deterministic-preclassified",
            "selected_backend": "deterministic",
            "preclassification_reason": preclassified_result["reason"],
        }
        validated = dict(preclassified_result["validated"])
        active_model_profile = {
            "name": model_selection["name"],
            "family": model_selection["family"],
            "configured_model": model_selection["configured_model"],
            "resolved_model": model_selection["resolved_model"],
            "description": model_selection["description"],
            "example_tags": model_selection["example_tags"],
        }
        cache_path = (repo_root / _hybrid_result_cache_path(config)).resolve()
        cache_key = ""
        diff_fingerprint = ""
        cache_hit = False
    else:
        backend_status = select_hybrid_backend(
            requested_backend=requested_backend,
            flow_name=flow_name,
            repo_root=repo_root,
            config=config,
            requested_model=requested_model,
            host=ollama_host,
            model_profile=str(model_selection["name"]),
            model_family=str(model_selection["family"]),
            configured_model=str(model_selection["configured_model"]),
            model=str(model_selection["resolved_model"]),
            timeout_seconds=timeout_seconds,
        )
        effective_profile, profile_adjustment_reason, requested_profile_label = _resolve_runtime_context_profile(
            flow_name=flow_name,
            requested_profile=profile,
            backend_status=backend_status,
        )
        if effective_profile != resolved_profile:
            context_bundle, validation_payload = _prepare_hybrid_context_bundle(
                repo_root,
                flow_name=flow_name,
                ref=ref,
                context_mode=context_mode,
                profile=effective_profile,
                include_graph=include_graph,
                include_registry=include_registry,
                include_doctor=include_doctor,
                audit_log=audit_log,
                measurement_log=measurement_log,
                config=config,
            )
            context_bundle["context_profile"]["requested_profile"] = requested_profile_label
            context_bundle["context_profile"]["profile_adjustment"] = "capped-to-normal-for-remote-or-codex"
            resolved_profile = effective_profile
        cache_eligible = (
            execution_mode != "execute"
            and flow_name != "hybrid-insights-explainer"
            and context_bundle["contract"]["safety_class"] == "proposal-only"
        )
        cache_path, cache_key, diff_fingerprint, cached_entry = _read_hybrid_result_cache_entry(
            repo_root=repo_root,
            config=config,
            flow_name=flow_name,
            requested_backend=requested_backend,
            model_selection=model_selection,
            context_bundle=context_bundle,
            dry_run=dry_run,
        )
        cache_hit = cache_eligible and cached_entry is not None

        if cache_hit:
            backend_status = _cached_backend_status(cached_entry, requested_backend)
            degraded_reasons = []
            raw_payload = cached_entry.get("raw_payload") if isinstance(cached_entry.get("raw_payload"), dict) else None
            transport = {
                "transport": "cache",
                "reason": "cache-hit",
                "selected_backend": backend_status.selected_backend,
                "cache_key": cache_key,
            }
            validated = dict(cached_entry["validated_payload"])
            active_model_profile = (
                cached_entry.get("active_model_profile")
                if isinstance(cached_entry.get("active_model_profile"), dict)
                else None
            )
        else:
            execution = execute_hybrid_backend(
                backend_status=backend_status,
                requested_backend=requested_backend,
                flow_name=flow_name,
                context_bundle=context_bundle,
                repo_root=repo_root,
                config=config,
                requested_model=requested_model,
                timeout_seconds=timeout_seconds,
                docs_by_ref=docs_by_ref,
                validation_payload=validation_payload,
            )
            backend_status = execution["backend_status"]
            degraded_reasons = execution["degraded_reasons"]
            raw_payload = execution["raw_payload"]
            transport = execution["transport"]
            validated = execution["validated"]
            active_model_profile = {
                "name": model_selection["name"],
                "family": model_selection["family"],
                "configured_model": model_selection["configured_model"],
                "resolved_model": model_selection["resolved_model"],
                "description": model_selection["description"],
                "example_tags": model_selection["example_tags"],
            }

    if profile_adjustment_reason and profile_adjustment_reason not in degraded_reasons:
        degraded_reasons = [profile_adjustment_reason, *degraded_reasons]

    execution_result = None
    executed = False
    if flow_name == "next-step":
        decision = validate_dispatcher_decision(validated, docs_by_ref)
        mapped_command = map_decision_to_command(decision, docs_by_ref)
        if execution_mode == "execute":
            execution_result = _run_mapped_command(repo_root, mapped_command["argv"])
            executed = True
        validated = {"decision": decision.to_dict(), "mapped_command": mapped_command}
    elif flow_name == "commit-all":
        raise SystemExit("Internal error: commit-all should route through cmd_assist_commit_all.")
    elif flow_name == "prepare-release":
        raise SystemExit("Internal error: prepare-release should route through cmd_assist_prepare_release.")
    elif flow_name == "publish-release":
        raise SystemExit("Internal error: publish-release should route through cmd_assist_publish_release.")

    result_status = "degraded" if degraded_reasons else "ok"
    audit_path = (repo_root / audit_log).resolve()
    measurement_path = (repo_root / measurement_log).resolve()
    confidence = None
    if flow_name == "next-step":
        confidence = float(validated["decision"]["confidence"])
    elif isinstance(validated, dict) and "confidence" in validated:
        confidence = float(validated["confidence"])
    review_recommended = bool(degraded_reasons) or (confidence is not None and confidence < 0.7)
    if not dry_run:
        append_jsonl_record(
            audit_path,
            build_hybrid_audit_record(
                flow_name=flow_name,
                result_status=result_status,
                backend_status=backend_status,
                context_bundle=context_bundle,
                raw_payload=raw_payload,
                validated_payload=validated,
                transport=transport,
                degraded_reasons=degraded_reasons,
                execution_result=execution_result,
            ),
        )
        append_jsonl_record(
            measurement_path,
            build_measurement_record(
                flow_name=flow_name,
                backend_status=backend_status,
                result_status=result_status,
                confidence=confidence,
                degraded_reasons=degraded_reasons,
                review_recommended=review_recommended,
                execution_path_override=(
                    "cache-hit"
                    if cache_hit
                    else ("deterministic-preclassified" if preclassified_result is not None else None)
                ),
                cache_hit=cache_hit,
            ),
        )
        if (
            preclassified_result is None
            and cache_eligible
            and not cache_hit
            and result_status == "ok"
            and isinstance(validated, dict)
            and isinstance(transport, dict)
            and _hybrid_result_cache_enabled(config)
        ):
            _write_hybrid_result_cache_entry(
                cache_path=cache_path,
                cache_key=cache_key,
                diff_fingerprint=diff_fingerprint,
                ttl_seconds=_hybrid_result_cache_ttl_seconds(config),
                flow_name=flow_name,
                requested_backend=requested_backend,
                model_selection=model_selection,
                backend_status=backend_status,
                result_status=result_status,
                raw_payload=raw_payload if isinstance(raw_payload, dict) else None,
                validated_payload=validated,
                transport=transport,
                confidence=confidence,
                review_recommended=review_recommended,
            )
    return {
        "command": "assist",
        "assist_kind": "run",
        "flow": flow_name,
        "seed_ref": ref,
        "backend_requested": requested_backend,
        "backend_used": backend_status.selected_backend,
        "backend_status": backend_status.to_dict(),
        "active_model_profile": active_model_profile,
        "result_status": result_status,
        "degraded_reasons": degraded_reasons,
        "context_bundle": context_bundle,
        "raw_result": raw_payload,
        "result": validated,
        "transport": transport,
        "cache_hit": cache_hit,
        "result_cache_path": _rel(repo_root, cache_path),
        "executed": executed,
        "execution_mode": execution_mode,
        "execution_result": execution_result,
        "audit_log": _rel(repo_root, audit_path),
        "measurement_log": _rel(repo_root, measurement_path),
        "review_recommended": review_recommended,
        "ok": True,
    }


def cmd_assist_run(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _run_hybrid_assist(
        repo_root,
        flow_name=args.flow_name,
        ref=getattr(args, "ref", None),
        intent=getattr(args, "intent", None),
        requested_backend=args.backend or _hybrid_default_backend(config),
        requested_model_profile=getattr(args, "model_profile", None),
        requested_model=args.model,
        ollama_host=args.ollama_host or _hybrid_default_host(config),
        timeout_seconds=args.timeout or _hybrid_default_timeout(config),
        context_mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        execution_mode=args.execution_mode,
        audit_log=args.audit_log or _hybrid_audit_log(config),
        measurement_log=args.measurement_log or _hybrid_measurement_log(config),
        config=config,
        dry_run=args.dry_run,
    )
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_commit_all(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": args.backend or _hybrid_default_backend(config),
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": args.include_graph,
        "include_registry": args.include_registry,
        "include_doctor": args.include_doctor,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }
    plan_payload = _run_hybrid_assist(flow_name="commit-plan", ref=None, **base_kwargs)
    root_message_payload = _run_hybrid_assist(flow_name="commit-message", ref=None, **base_kwargs)
    execution_result = None
    executed = False
    if args.execution_mode == "execute":
        plan = plan_payload["result"]
        steps = plan["steps"]
        step_results = []
        for step in steps:
            target_repo = repo_root / "logics" / "skills" if step["scope"] == "submodule" else repo_root
            target_snapshot = collect_git_snapshot(target_repo, refresh=True)
            if not target_snapshot.get("has_changes"):
                step_results.append(
                    {
                        "scope": step["scope"],
                        "message": None,
                        "stdout": "",
                        "stderr": "",
                        "skipped": True,
                        "reason": "working-tree-clean",
                    }
                )
                continue
            message_payload = _run_hybrid_assist(
                flow_name="commit-message",
                ref=None,
                repo_root=target_repo,
                requested_backend=args.backend or _hybrid_default_backend(config),
                requested_model_profile=getattr(args, "model_profile", None),
                requested_model=args.model,
                ollama_host=args.ollama_host or _hybrid_default_host(config),
                timeout_seconds=args.timeout or _hybrid_default_timeout(config),
                context_mode=args.context_mode,
                profile=args.profile,
                include_graph=args.include_graph,
                include_registry=args.include_registry,
                include_doctor=args.include_doctor,
                execution_mode="suggestion-only",
                audit_log=args.audit_log or _hybrid_audit_log(config),
                measurement_log=args.measurement_log or _hybrid_measurement_log(config),
                config=config,
                dry_run=True,
            )
            message = message_payload["result"]["subject"]
            commit_result = execute_commit_step(target_repo, message)
            step_results.append({"scope": step["scope"], "message": message, **commit_result})
        execution_result = {"steps": step_results}
        executed = True
    payload = {
        "command": "assist",
        "assist_kind": "commit-all",
        "flow": "commit-all",
        "plan": plan_payload["result"],
        "root_message": root_message_payload["result"],
        "executed": executed,
        "execution_mode": args.execution_mode,
        "execution_result": execution_result,
        "backend_requested": plan_payload["backend_requested"],
        "backend_used": plan_payload["backend_used"],
        "audit_log": plan_payload["audit_log"],
        "measurement_log": plan_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_prepare_release(args: argparse.Namespace) -> dict[str, object]:
    import re

    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": args.backend or _hybrid_default_backend(config),
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": args.include_graph,
        "include_registry": args.include_registry,
        "include_doctor": args.include_doctor,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }

    # Capture the git snapshot before any assist calls so audit log creation does not
    # pollute the working-tree status check.
    git_snapshot = collect_git_snapshot(repo_root, refresh=True)

    # release-changelog-status is policy-deterministic; always use auto so the backend
    # policy routes it correctly regardless of what the operator requested.
    changelog_status_payload = _run_hybrid_assist(
        flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
    )
    validation_payload = _run_hybrid_assist(flow_name="validation-checklist", ref=None, **base_kwargs)
    diff_risk_payload = _run_hybrid_assist(flow_name="diff-risk", ref=None, **base_kwargs)

    changelog_status = _rdict(changelog_status_payload["result"])
    changelog_ready = bool(changelog_status.get("exists", False))
    already_published = bool(changelog_status.get("already_published", False))
    version_mismatch = bool(changelog_status.get("version_mismatch", False))
    has_uncommitted = bool(git_snapshot.get("has_changes", False))
    readme_badge_ok = changelog_status.get("readme_badge_ok")
    version = str(changelog_status.get("version", "0.0.0"))

    prep_steps: list[str] = []
    prep_errors: list[str] = []

    if args.execution_mode == "execute":
        if already_published:
            next_version = str(changelog_status.get("next_version") or "").strip() or _next_patch_release_version(version)
            if next_version:
                if not args.dry_run:
                    updated_paths = _update_release_version_artifacts(repo_root, next_version)
                    if updated_paths:
                        prep_steps.append(f"bumped release version to {next_version}")
                    else:
                        prep_steps.append(f"release version already aligned at {next_version}")
                else:
                    prep_steps.append(f"(dry-run) would bump release version to {next_version}")

                collect_git_snapshot(repo_root, refresh=True)
                refreshed_status_payload = _run_hybrid_assist(
                    flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
                )
                changelog_status = _rdict(refreshed_status_payload["result"])
                changelog_ready = bool(changelog_status.get("exists", False))
                already_published = bool(changelog_status.get("already_published", False))
                version_mismatch = bool(changelog_status.get("version_mismatch", False))
                readme_badge_ok = changelog_status.get("readme_badge_ok")
                version = str(changelog_status.get("version", next_version))

        if version_mismatch:
            if not args.dry_run:
                _update_release_version_artifacts(repo_root, version)
                prep_steps.append("updated VERSION to match package.json")
                version_mismatch = False
            else:
                prep_steps.append("(dry-run) would update VERSION to match package.json")

        # Step 1: generate changelog via AI if missing
        if not changelog_ready:
            gen_payload = _run_hybrid_assist(flow_name="generate-changelog", ref=None, **base_kwargs)
            gen_result = _rdict(gen_payload["result"])
            changelog_content = str(gen_result.get("content", ""))
            relative_path = str(changelog_status.get("relative_path", f"changelogs/CHANGELOGS_{version.replace('.', '_')}.md"))
            changelog_file = repo_root / relative_path
            changelog_file.parent.mkdir(parents=True, exist_ok=True)
            if not args.dry_run:
                changelog_file.write_text(changelog_content, encoding="utf-8")
                prep_steps.append(f"wrote {relative_path}")
                changelog_ready = True
                collect_git_snapshot(repo_root, refresh=True)
            else:
                prep_steps.append(f"(dry-run) would write {relative_path}")

        # Step 2: update README version badge if stale
        if readme_badge_ok is False:
            for readme_name in ("README.md", "readme.md", "Readme.md"):
                readme_path = repo_root / readme_name
                if readme_path.is_file():
                    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
                    updated = re.sub(r"version-v[\d]+\.[\d]+\.[\d]+", f"version-v{version}", readme_text)
                    updated = re.sub(r"version/[\d]+\.[\d]+\.[\d]+", f"version/{version}", updated)
                    if updated != readme_text:
                        if not args.dry_run:
                            readme_path.write_text(updated, encoding="utf-8")
                            prep_steps.append(f"updated version badge in {readme_name}")
                            collect_git_snapshot(repo_root, refresh=True)
                        else:
                            prep_steps.append(f"(dry-run) would update version badge in {readme_name}")
                    break

        # Step 3: commit any prep changes
        if prep_steps and any("(dry-run)" not in s for s in prep_steps):
            try:
                execute_commit_step(repo_root, f"Prepare {version} release")
                prep_steps.append(f"committed prep changes for {version}")
                has_uncommitted = False
            except Exception as exc:  # noqa: BLE001
                prep_errors.append(str(exc))

        # Re-evaluate readiness after prep
        if not prep_errors:
            collect_git_snapshot(repo_root, refresh=True)
            updated_status_payload = _run_hybrid_assist(
                flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
            )
            changelog_status = _rdict(updated_status_payload["result"])
            changelog_ready = bool(changelog_status.get("exists", False))
            already_published = bool(changelog_status.get("already_published", False))
            version_mismatch = bool(changelog_status.get("version_mismatch", False))

    ready = changelog_ready and not has_uncommitted and not already_published and not version_mismatch

    payload = {
        "command": "assist",
        "assist_kind": "prepare-release",
        "flow": "prepare-release",
        "changelog_status": changelog_status,
        "validation_checklist": validation_payload["result"],
        "diff_risk": diff_risk_payload["result"],
        "git_snapshot": git_snapshot,
        "ready": ready,
        "execution_mode": args.execution_mode,
        "prep_steps": prep_steps,
        "prep_errors": prep_errors,
        "backend_requested": changelog_status_payload["backend_requested"],
        "backend_used": changelog_status_payload["backend_used"],
        "audit_log": changelog_status_payload["audit_log"],
        "measurement_log": changelog_status_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_publish_release(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": "auto",
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": False,
        "include_registry": False,
        "include_doctor": False,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }

    # Capture git snapshot before assist calls.
    git_snapshot = collect_git_snapshot(repo_root, refresh=True)

    changelog_status_payload = _run_hybrid_assist(
        flow_name="release-changelog-status", ref=None, **base_kwargs
    )
    changelog_status = _rdict(changelog_status_payload["result"])
    release_branch = _release_branch_status(repo_root)
    changelog_ready = bool(changelog_status.get("exists", False))
    already_published = bool(changelog_status.get("already_published", False))
    version_mismatch = bool(changelog_status.get("version_mismatch", False))
    has_uncommitted = bool(git_snapshot.get("has_changes", False))
    ready = changelog_ready and not has_uncommitted and not already_published and not version_mismatch

    publish_result: dict[str, object] | None = None
    executed = False

    if args.execution_mode == "execute":
        _plugin_relative = repo_root / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
        _kit_direct = repo_root / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
        publish_script = _plugin_relative if _plugin_relative.is_file() else _kit_direct
        if not publish_script.is_file():
            publish_result = {"ok": False, "error": f"Publish script not found: {publish_script}"}
        elif not ready:
            blocking: list[str] = []
            if not changelog_ready:
                blocking.append("changelog not ready — run 'flow assist prepare-release --execution-mode execute' first")
            if already_published:
                blocking.append("version already published or tagged — bump the version before publishing again")
            if version_mismatch:
                blocking.append("VERSION is out of sync with package.json — run 'flow assist prepare-release --execution-mode execute' first")
            if has_uncommitted:
                blocking.append("uncommitted changes present")
            publish_result = {"ok": False, "error": "Release prerequisites not met.", "blocking": blocking}
        else:
            cmd = [sys.executable, str(publish_script)]
            version_override = getattr(args, "version", None)
            if version_override:
                cmd += ["--version", version_override]
            if getattr(args, "draft", False):
                cmd += ["--draft"]
            if getattr(args, "push", False):
                cmd += ["--create-tag", "--push"]
            if args.dry_run:
                cmd += ["--dry-run"]
            completed = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
            publish_result = {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "command": cmd,
            }
            executed = completed.returncode == 0
    else:
        # suggestion-only: show what would be done
        version = str(changelog_status.get("version", "0.0.0"))
        tag = str(changelog_status.get("tag", f"v{version}"))
        release_note = str(release_branch.get("suggestion", "")).strip()
        release_command = str(release_branch.get("command", "")).strip()
        release_guidance = ""
        if release_note:
            release_guidance = f"\n{release_note}"
            if release_command:
                release_guidance += f"\nSuggested command: {release_command}"
        publish_result = {
            "ok": True,
            "suggestion": (
                f"When ready, run: flow assist publish-release --execution-mode execute --push"
                f"\nThis will create tag {tag}, push main+tag, and publish the GitHub release."
                f"{release_guidance}"
                if ready
                else f"Release is not ready yet. Run 'flow assist prepare-release --execution-mode execute' first."
            ),
            "ready": ready,
        }

    payload = {
        "command": "assist",
        "assist_kind": "publish-release",
        "flow": "publish-release",
        "changelog_status": changelog_status,
        "release_branch": release_branch,
        "git_snapshot": git_snapshot,
        "ready": ready,
        "executed": executed,
        "execution_mode": args.execution_mode,
        "publish_result": publish_result,
        "backend_requested": changelog_status_payload["backend_requested"],
        "backend_used": changelog_status_payload["backend_used"],
        "audit_log": changelog_status_payload["audit_log"],
        "measurement_log": changelog_status_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _mutation_mode(args: argparse.Namespace, config: dict[str, object]) -> str:
    if getattr(args, "mutation_mode", None):
        return str(args.mutation_mode)
    return str(get_config_value(config, "mutations", "mode", default="transactional"))


def _mutation_audit_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "mutations", "audit_log", default="logics/mutation_audit.jsonl"))


def _enforce_split_policy(titles: list[str], args: argparse.Namespace, config: dict[str, object]) -> None:
    policy = str(get_config_value(config, "workflow", "split", "policy", default="minimal-coherent"))
    max_children = int(get_config_value(config, "workflow", "split", "max_children_without_override", default=2))
    if policy != "minimal-coherent":
        return
    if len(titles) <= max_children or getattr(args, "allow_extra_slices", False):
        return
    raise SystemExit(
        "Split policy `minimal-coherent` only allows "
        + f"{max_children} child slice(s) by default. "
        + "Reduce the split or pass `--allow-extra-slices` when the extra decomposition is genuinely required."
    )


def _run_mapped_command(repo_root: Path, argv: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *argv, "--format", "json"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "Mapped command failed."
        raise DispatcherError(
            "dispatcher_command_failed",
            error_message,
            details={"argv": argv, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DispatcherError(
            "dispatcher_command_invalid_json",
            f"Mapped command did not return valid JSON: {exc}",
            details={"argv": argv, "stdout": result.stdout},
        ) from exc
    return payload


def cmd_sync_dispatch_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_dispatcher_context(
        repo_root,
        args.ref,
        mode=args.mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "dispatch-context", **payload}


def cmd_sync_dispatch(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    context_bundle = _build_dispatcher_context(
        repo_root,
        args.ref,
        mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    docs_by_ref = _load_workflow_docs(repo_root, config=config)

    transport: dict[str, object]
    if args.decision_json:
        decision_payload = extract_json_object(args.decision_json)
        transport = {"transport": "inline", "source": "decision-json"}
    elif args.decision_file:
        decision_payload = extract_json_object(Path(args.decision_file).read_text(encoding="utf-8"))
        transport = {"transport": "file", "source": args.decision_file}
    elif args.model:
        transport = run_ollama_dispatch(
            host=args.ollama_host,
            model=args.model,
            context_bundle=context_bundle,
            timeout_seconds=args.timeout,
        )
        decision_payload = transport["decision_payload"]
    else:
        raise SystemExit("Provide exactly one of --decision-json, --decision-file, or --model.")

    validated = validate_dispatcher_decision(decision_payload, docs_by_ref)
    mapped = map_decision_to_command(validated, docs_by_ref)

    execution_result: dict[str, object] | None = None
    executed = False
    if args.execution_mode == "execute":
        execution_result = _run_mapped_command(repo_root, mapped["argv"])
        executed = True

    audit_path = (repo_root / args.audit_log).resolve()
    audit_record = build_audit_record(
        seed_ref=args.ref,
        execution_mode=args.execution_mode,
        context_bundle=context_bundle,
        decision_payload=decision_payload,
        validated_decision=validated,
        mapped_command=mapped,
        execution_result=execution_result,
        transport=transport,
    )
    if not args.dry_run:
        append_audit_record(audit_path, audit_record)

    if executed:
        print(f"Executed dispatcher action `{validated.action}` via {' '.join(mapped['argv'])}.")
    else:
        print(f"Suggested dispatcher action `{validated.action}` via {' '.join(mapped['argv'])}.")
    print(f"Audit log: {audit_path.relative_to(repo_root)}")

    return {
        "command": "sync",
        "sync_kind": "dispatch",
        "seed_ref": args.ref,
        "execution_mode": args.execution_mode,
        "executed": executed,
        "decision_source": transport["transport"],
        "audit_log": _rel(repo_root, audit_path),
        "context_bundle": context_bundle,
        "raw_decision": decision_payload,
        "validated_decision": validated.to_dict(),
        "mapped_command": mapped,
        "execution_result": execution_result,
        "transport": transport,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "dry_run": args.dry_run,
    }

def cmd_new(args: argparse.Namespace) -> None:
    doc_kind = DOC_KINDS[args.kind]
    repo_root = _find_repo_root(Path.cwd())
    planned = _reserve_doc(repo_root / doc_kind.directory, doc_kind.prefix, args.slug or args.title, args.dry_run)

    template_text = _template_path(Path(__file__), doc_kind.template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, args.title, doc_kind.include_progress, doc_kind.kind)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(args.title))
    assessment = _assess_decision_framing(args.title, "")
    product_refs: list[str] = []
    architecture_refs: list[str] = []
    if doc_kind.kind in {"backlog", "task"}:
        product_refs, architecture_refs = _auto_create_companion_docs(
            repo_root,
            args.title,
            request_ref=None,
            backlog_ref=planned.ref if doc_kind.kind == "backlog" else None,
            task_ref=planned.ref if doc_kind.kind == "task" else None,
            assessment=assessment,
            product_refs=product_refs,
            architecture_refs=architecture_refs,
            args=args,
        )
        _apply_decision_assessment(values, assessment)
        if product_refs:
            values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
        if architecture_refs:
            values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _render_workflow_mermaid(doc_kind.kind, args.title, values)
    content = _render_template(template_text, values).rstrip() + "\n"
    _write(planned.path, content, args.dry_run)
    if doc_kind.kind in {"backlog", "task"}:
        _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return {
        "command": "new",
        "kind": doc_kind.kind,
        "ref": planned.ref,
        "path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_promote_request_to_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Promoted backlog item"
    repo_root = _find_repo_root(Path.cwd())
    planned = _create_backlog_from_request(repo_root, source_path, title, args)
    print(
        "Created a backlog slice from the request. "
        "If the request spans multiple deliverables, use `python logics/skills/logics.py flow assist suggest-split <request-ref> --format json` "
        "followed by `python logics/skills/logics.py flow split request ...` so the request is covered by several bounded backlog items instead of one oversized item."
    )
    return {
        "command": "promote",
        "promotion": "request-to-backlog",
        "source": _rel(repo_root, source_path),
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_promote_backlog_to_task(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Implementation task"
    repo_root = _find_repo_root(Path.cwd())
    planned = _create_task_from_backlog(repo_root, source_path, title, args)
    return {
        "command": "promote",
        "promotion": "backlog-to-task",
        "source": _rel(repo_root, source_path),
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_split_request(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    config, _config_path = _effective_config(repo_root)
    titles = _split_titles(args.title)
    _enforce_split_policy(titles, args, config)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_backlog_from_request(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split request into {len(created_refs)} backlog item(s): {', '.join(created_refs)}")
    return {
        "command": "split",
        "kind": "request",
        "source": _rel(repo_root, source_path),
        "created_refs": created_refs,
        "dry_run": args.dry_run,
    }


def cmd_split_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    config, _config_path = _effective_config(repo_root)
    titles = _split_titles(args.title)
    _enforce_split_policy(titles, args, config)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_task_from_backlog(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split backlog item into {len(created_refs)} task(s): {', '.join(created_refs)}")
    return {
        "command": "split",
        "kind": "backlog",
        "source": _rel(repo_root, source_path),
        "created_refs": created_refs,
        "dry_run": args.dry_run,
    }


def _maybe_close_request_chain(repo_root: Path, request_ref: str, dry_run: bool) -> None:
    request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
    if request_path is None:
        return

    linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
    if not linked_items:
        return

    if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
        if not _is_doc_done(request_path, DOC_KINDS["request"]):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")


def _sync_close_eligible_requests(repo_root: Path, dry_run: bool) -> tuple[int, int]:
    request_dir = repo_root / DOC_KINDS["request"].directory
    closed = 0
    scanned = 0
    for request_path in sorted(request_dir.glob("req_*.md")):
        request_ref = request_path.stem
        scanned += 1
        if _is_doc_done(request_path, DOC_KINDS["request"]):
            continue
        linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
        if not linked_items:
            continue
        if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")
            closed += 1
    return scanned, closed


def cmd_sync_close_eligible_requests(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    scanned, closed = _sync_close_eligible_requests(repo_root, args.dry_run)
    print(f"Scanned {scanned} requests, auto-closed {closed}.")
    return {"command": "sync", "sync_kind": "close-eligible-requests", "scanned": scanned, "closed": closed, "dry_run": args.dry_run}


def cmd_sync_refresh_mermaid_signatures(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    refreshed: list[Path] = []
    for kind_name in ("request", "backlog", "task"):
        kind = DOC_KINDS[kind_name]
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"{kind.prefix}_*.md")):
            if refresh_workflow_mermaid_signature_file(path, kind_name, args.dry_run):
                refreshed.append(path.relative_to(repo_root))

    if args.dry_run:
        print(f"Dry run: {len(refreshed)} Mermaid signature update(s) would be applied.")
    else:
        print(f"Refreshed Mermaid signatures in {len(refreshed)} workflow doc(s).")
    for path in refreshed:
        print(f"- {path}")
    return {
        "command": "sync",
        "sync_kind": "refresh-mermaid-signatures",
        "modified_files": [path.as_posix() for path in refreshed],
        "dry_run": args.dry_run,
    }


def cmd_sync_refresh_ai_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    modified: list[dict[str, object]] = []
    writes: list[TransactionWrite] = []
    for kind_name, path in _resolve_target_docs(repo_root, args.sources):
        original = path.read_text(encoding="utf-8")
        refreshed, changed = refresh_ai_context_text(original, kind_name)
        if not changed:
            continue
        mutation = build_planned_mutation(path, before=original, after=refreshed, reason="refresh AI Context", repo_root=repo_root)
        modified.append(mutation.to_dict())
        writes.append(TransactionWrite(path=path, content=refreshed, reason="refresh AI Context"))
    try:
        transaction = apply_transaction(
            repo_root,
            writes=writes,
            mode=_mutation_mode(args, config),
            audit_log=_mutation_audit_log(config),
            dry_run=args.preview or args.dry_run,
            command_name="sync refresh-ai-context",
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    if args.preview:
        print(f"Previewed AI Context refresh for {len(modified)} workflow doc(s).")
    else:
        print(f"Refreshed AI Context in {len(modified)} workflow doc(s).")
    for mutation in modified:
        print(f"- {mutation['path']}")
    return {
        "command": "sync",
        "sync_kind": "refresh-ai-context",
        "preview": args.preview,
        "dry_run": args.dry_run,
        "modified_files": modified,
        "mutation_mode": transaction.mode,
        "mutation_audit_log": transaction.audit_path,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
    }


def cmd_sync_context_pack(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_context_pack(repo_root, args.ref, mode=args.mode, profile=args.profile, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        _write(out_path, serialized, args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "context-pack", **payload}


def cmd_sync_schema_status(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    payload = _schema_status(repo_root, args.sources)
    print(f"Schema status: {payload['doc_count']} workflow doc(s) scanned.")
    for version, count in payload["counts"].items():
        print(f"- {version}: {count}")
    return {"command": "sync", "sync_kind": "schema-status", **payload}


def cmd_sync_migrate_schema(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    modified: list[dict[str, object]] = []
    writes: list[TransactionWrite] = []
    for kind_name, path in _resolve_target_docs(repo_root, args.sources):
        original = path.read_text(encoding="utf-8")
        refreshed, changed = _ensure_schema_version_text(original)
        if args.refresh_ai_context:
            refreshed, ai_changed = refresh_ai_context_text(refreshed, kind_name)
            changed = changed or ai_changed
        if not changed:
            continue
        mutation = build_planned_mutation(path, before=original, after=refreshed, reason="migrate workflow schema", repo_root=repo_root)
        modified.append(mutation.to_dict())
        writes.append(TransactionWrite(path=path, content=refreshed, reason="migrate workflow schema"))
    try:
        transaction = apply_transaction(
            repo_root,
            writes=writes,
            mode=_mutation_mode(args, config),
            audit_log=_mutation_audit_log(config),
            dry_run=args.preview or args.dry_run,
            command_name="sync migrate-schema",
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    if args.preview:
        print(f"Previewed schema migration for {len(modified)} workflow doc(s).")
    else:
        print(f"Migrated schema for {len(modified)} workflow doc(s).")
    for mutation in modified:
        print(f"- {mutation['path']}")
    return {
        "command": "sync",
        "sync_kind": "migrate-schema",
        "preview": args.preview,
        "dry_run": args.dry_run,
        "refresh_ai_context": args.refresh_ai_context,
        "modified_files": modified,
        "mutation_mode": transaction.mode,
        "mutation_audit_log": transaction.audit_path,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
    }


def cmd_sync_export_graph(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _graph_payload(repo_root, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "export-graph", **payload}


def cmd_sync_validate_skills(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _validate_skills_payload(repo_root, config=config)
    print(f"Validated {payload['skill_count']} skill package(s).")
    if payload["issues"]:
        for issue in payload["issues"]:
            print(f"- {issue['path']}: {'; '.join(issue['issues'])}")
    else:
        print("- No skill package issues detected.")
    return {"command": "sync", "sync_kind": "validate-skills", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_export_registry(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _export_registry_payload(repo_root, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "export-registry", **payload}


def cmd_sync_doctor(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _doctor_payload(repo_root, config=config)
    if payload["ok"]:
        print("Kit doctor: OK")
    else:
        print("Kit doctor: FAILED")
        for issue in payload["issues"]:
            print(f"- [{issue['code']}] {issue['path']}: {issue['message']}")
            print(f"  remediation: {issue['remediation']}")
    return {"command": "sync", "sync_kind": "doctor", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_benchmark_skills(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _benchmark_payload(repo_root, config=config)
    print(f"Benchmarked {payload['skill_count']} skill package(s) in {payload['duration_ms']} ms.")
    return {"command": "sync", "sync_kind": "benchmark-skills", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_build_index(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = load_runtime_index(repo_root, config=config, force=args.force, dry_run=args.dry_run)
    print(
        "Runtime index: "
        + f"{payload['stats']['workflow_doc_count']} workflow doc(s), "
        + f"{payload['stats']['skill_count']} skill package(s), "
        + f"{payload['stats']['cache_hits']} cache hit(s), "
        + f"{payload['stats']['cache_misses']} cache miss(es)."
    )
    return {
        "command": "sync",
        "sync_kind": "build-index",
        "dry_run": args.dry_run,
        "force": args.force,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        **payload,
    }


def cmd_sync_show_config(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = {
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "config": config,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "show-config", **payload}


def cmd_close(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    kind = DOC_KINDS[args.kind]
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{kind.prefix}_"):
        raise SystemExit(f"Expected a `{kind.prefix}_...` file for kind `{kind.kind}`. Got: {source_path.name}")

    _close_doc(source_path, kind, args.dry_run)
    print(f"Closed {kind.kind}: {source_path.relative_to(repo_root)}")

    text = _strip_mermaid_blocks(source_path.read_text(encoding="utf-8"))
    processed_request_refs: set[str] = set()

    if kind.kind == "task":
        linked_item_refs = sorted(_extract_refs(text, REF_PREFIXES["backlog"]))
        for item_ref in linked_item_refs:
            item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
            if item_path is None:
                continue
            linked_tasks = _collect_docs_linking_ref(repo_root, DOC_KINDS["task"], item_ref)
            if linked_tasks and all(_is_doc_done(task_path, DOC_KINDS["task"]) for task_path in linked_tasks):
                if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
                    _close_doc(item_path, DOC_KINDS["backlog"], args.dry_run)
                    print(f"Auto-closed backlog item {item_ref} (all linked tasks are done).")

            item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
            for request_ref in sorted(_extract_refs(item_text, REF_PREFIXES["request"])):
                if request_ref in processed_request_refs:
                    continue
                processed_request_refs.add(request_ref)
                _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "backlog":
        for request_ref in sorted(_extract_refs(text, REF_PREFIXES["request"])):
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "request":
        request_ref = source_path.stem
        _maybe_close_request_chain(repo_root, request_ref, args.dry_run)
    return {
        "command": "close",
        "kind": kind.kind,
        "source": _rel(repo_root, source_path),
        "dry_run": args.dry_run,
    }


def _verify_finished_task_chain(repo_root: Path, task_path: Path) -> list[str]:
    issues: list[str] = []
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))

    if not item_refs:
        return [f"task `{task_ref}` has no linked backlog item reference"]

    processed_request_refs: set[str] = set()
    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            issues.append(f"task `{task_ref}` references missing backlog item `{item_ref}`")
            continue
        if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
            issues.append(f"linked backlog item `{item_ref}` is not closed after finishing task `{task_ref}`")

        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs = sorted(_extract_refs(item_text, REF_PREFIXES["request"]))
        if not request_refs:
            issues.append(f"linked backlog item `{item_ref}` has no request reference")
            continue

        for request_ref in request_refs:
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
            if request_path is None:
                issues.append(f"backlog item `{item_ref}` references missing request `{request_ref}`")
                continue

            linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
            if linked_items and all(_is_doc_done(linked_item, DOC_KINDS["backlog"]) for linked_item in linked_items):
                if not _is_doc_done(request_path, DOC_KINDS["request"]):
                    issues.append(
                        f"request `{request_ref}` should be closed because all linked backlog items are done"
                    )

    return issues


def _record_finished_task_follow_up(repo_root: Path, task_path: Path, dry_run: bool) -> None:
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))
    request_refs: set[str] = set()

    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            continue
        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs.update(_extract_refs(item_text, REF_PREFIXES["request"]))
        _append_section_bullets(
            item_path,
            "Notes",
            [f"- Task `{task_ref}` was finished via `logics_flow.py finish task` on {date.today().isoformat()}."],
            dry_run,
        )

    validation_bullets = [
        f"- Finish workflow executed on {date.today().isoformat()}.",
        "- Linked backlog/request close verification passed.",
    ]
    report_bullets = [
        f"- Finished on {date.today().isoformat()}.",
        f"- Linked backlog item(s): {', '.join(f'`{ref}`' for ref in item_refs) if item_refs else '(none)'}",
        f"- Related request(s): {', '.join(f'`{ref}`' for ref in sorted(request_refs)) if request_refs else '(none)'}",
    ]
    _append_section_bullets(task_path, "Validation", validation_bullets, dry_run)
    _append_section_bullets(task_path, "Report", report_bullets, dry_run)


def cmd_finish_task(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{DOC_KINDS['task'].prefix}_"):
        raise SystemExit(f"Expected a `{DOC_KINDS['task'].prefix}_...` task file. Got: {source_path.name}")

    close_args = argparse.Namespace(kind="task", source=args.source, dry_run=args.dry_run)
    cmd_close(close_args)
    _mark_section_checkboxes_done(source_path, "Definition of Done (DoD)", args.dry_run)
    _record_finished_task_follow_up(repo_root, source_path, args.dry_run)

    if args.dry_run:
        print("Dry run: skipped post-close verification.")
        return

    issues = _verify_finished_task_chain(repo_root, source_path)
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        raise SystemExit(f"Finish verification failed:\n{details}")

    print(f"Finish verification: OK for {source_path.relative_to(repo_root)}")
    return {
        "command": "finish",
        "kind": "task",
        "source": _rel(repo_root, source_path),
        "dry_run": args.dry_run,
    }


def _add_common_doc_args(parser: argparse.ArgumentParser, kind: str) -> None:
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--status", default=STATUS_BY_KIND_DEFAULT[kind])
    parser.add_argument("--complexity", default="Medium", choices=ALLOWED_COMPLEXITIES)
    parser.add_argument("--theme", default="General")
    if DOC_KINDS[kind].include_progress:
        parser.add_argument("--progress", default="0%")
    else:
        parser.add_argument("--progress", default="")
    if kind in {"backlog", "task"}:
        parser.add_argument("--auto-create-product-brief", action="store_true")
        parser.add_argument("--auto-create-adr", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_flow.py",
        description="Create/promote/close/finish Logics docs with consistent IDs, templates, and workflow transitions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new Logics doc from a template.")
    new_sub = new_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        kind_parser = new_sub.add_parser(kind, help=f"Create a new {kind} doc.")
        kind_parser.add_argument("--title", required=True)
        kind_parser.add_argument("--slug", help="Override slug derived from the title.")
        _add_common_doc_args(kind_parser, kind)
        kind_parser.set_defaults(func=cmd_new)

    promote_parser = sub.add_parser("promote", help="Promote between Logics stages.")
    promote_sub = promote_parser.add_subparsers(dest="promotion", required=True)

    r2b = promote_sub.add_parser(
        "request-to-backlog",
        help="Create a backlog slice from an already atomic request. Prefer `split request` for broad requests.",
    )
    r2b.add_argument("source")
    _add_common_doc_args(r2b, "backlog")
    r2b.set_defaults(func=cmd_promote_request_to_backlog)

    b2t = promote_sub.add_parser("backlog-to-task", help="Create a task from a backlog item.")
    b2t.add_argument("source")
    _add_common_doc_args(b2t, "task")
    b2t.set_defaults(func=cmd_promote_backlog_to_task)

    split_parser = sub.add_parser("split", help="Split a request/backlog doc into multiple executable children.")
    split_sub = split_parser.add_subparsers(dest="split_kind", required=True)

    split_request = split_sub.add_parser("request", help="Split a request into multiple backlog items.")
    split_request.add_argument("source")
    split_request.add_argument(
        "--title",
        action="append",
        required=True,
        help="Child backlog item title. Repeat the flag for multiple bounded slices so the request coverage does not collapse into one or two oversized items.",
    )
    split_request.add_argument("--allow-extra-slices", action="store_true", help="Override the repo split policy when more child slices are explicitly justified.")
    _add_common_doc_args(split_request, "backlog")
    split_request.set_defaults(func=cmd_split_request)

    split_backlog = split_sub.add_parser("backlog", help="Split a backlog item into multiple tasks.")
    split_backlog.add_argument("source")
    split_backlog.add_argument("--title", action="append", required=True, help="Child task title. Repeat the flag for multiple children, keeping the split to the minimum coherent slice count.")
    split_backlog.add_argument("--allow-extra-slices", action="store_true", help="Override the repo split policy when more child slices are explicitly justified.")
    _add_common_doc_args(split_backlog, "task")
    split_backlog.set_defaults(func=cmd_split_backlog)

    close_parser = sub.add_parser("close", help="Close a request/backlog/task and propagate transitions.")
    close_sub = close_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        close_kind = close_sub.add_parser(kind, help=f"Close a {kind} doc.")
        close_kind.add_argument("source")
        close_kind.add_argument("--format", choices=("text", "json"), default="text")
        close_kind.add_argument("--dry-run", action="store_true")
        close_kind.set_defaults(func=cmd_close)

    finish_parser = sub.add_parser(
        "finish",
        help="Finish a completed Logics doc using the recommended workflow guardrails.",
    )
    finish_sub = finish_parser.add_subparsers(dest="finish_kind", required=True)
    finish_task = finish_sub.add_parser(
        "task",
        help="Close a task, propagate task -> backlog -> request transitions, and verify the linked chain.",
    )
    finish_task.add_argument("source")
    finish_task.add_argument("--format", choices=("text", "json"), default="text")
    finish_task.add_argument("--dry-run", action="store_true")
    finish_task.set_defaults(func=cmd_finish_task)

    assist_parser = sub.add_parser(
        "assist",
        help="Run bounded hybrid assist flows that can prefer Ollama locally and degrade cleanly otherwise.",
    )
    assist_sub = assist_parser.add_subparsers(dest="assist_kind", required=True)

    assist_runtime = assist_sub.add_parser(
        "runtime-status",
        help="Report the hybrid assist backend, bridge, and degraded-mode status for this repository.",
    )
    assist_runtime.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    assist_runtime.add_argument("--model-profile")
    assist_runtime.add_argument("--model")
    assist_runtime.add_argument("--ollama-host")
    assist_runtime.add_argument("--timeout", type=float)
    assist_runtime.add_argument("--out", help="Write the JSON status payload to this relative path.")
    assist_runtime.add_argument("--format", choices=("text", "json"), default="text")
    assist_runtime.add_argument("--dry-run", action="store_true")
    assist_runtime.set_defaults(func=cmd_assist_runtime_status)

    assist_context = assist_sub.add_parser(
        "context",
        help="Build a shared hybrid assist context bundle for a named flow.",
    )
    assist_context.add_argument(
        "flow_name",
        choices=tuple(sorted(build_shared_hybrid_contract()["flows"].keys())),
        help="Hybrid assist flow name.",
    )
    assist_context.add_argument("ref", nargs="?", help="Optional workflow ref for flows that operate on a target doc.")
    assist_context.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    assist_context.add_argument("--profile", choices=("tiny", "normal", "deep"))
    assist_context.add_argument("--include-graph", action="store_true", default=None)
    assist_context.add_argument("--include-registry", action="store_true", default=None)
    assist_context.add_argument("--include-doctor", action="store_true", default=None)
    assist_context.add_argument("--out", help="Write the JSON context bundle to this relative path.")
    assist_context.add_argument("--format", choices=("text", "json"), default="text")
    assist_context.add_argument("--dry-run", action="store_true")
    assist_context.set_defaults(func=cmd_assist_context)

    assist_roi = assist_sub.add_parser(
        "roi-report",
        help="Aggregate hybrid assist measurement and audit logs into a stable ROI dispatch report.",
    )
    assist_roi.add_argument("--audit-log")
    assist_roi.add_argument("--measurement-log")
    assist_roi.add_argument("--recent-limit", type=int, default=DEFAULT_HYBRID_ROI_RECENT_LIMIT)
    assist_roi.add_argument("--window-days", type=int, default=DEFAULT_HYBRID_ROI_WINDOW_DAYS)
    assist_roi.add_argument("--out", help="Write the JSON report payload to this relative path.")
    assist_roi.add_argument("--format", choices=("text", "json"), default="text")
    assist_roi.add_argument("--dry-run", action="store_true")
    assist_roi.set_defaults(func=cmd_assist_roi_report)

    assist_run = assist_sub.add_parser(
        "run",
        help="Run a shared hybrid assist flow and return structured output plus backend provenance.",
    )
    assist_run.add_argument(
        "flow_name",
        choices=tuple(sorted(build_shared_hybrid_contract()["flows"].keys())),
        help="Hybrid assist flow name.",
    )
    assist_run.add_argument("ref", nargs="?", help="Optional workflow ref for flows that operate on a target doc.")
    assist_run.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    assist_run.add_argument("--model-profile")
    assist_run.add_argument("--model")
    assist_run.add_argument("--ollama-host")
    assist_run.add_argument("--timeout", type=float)
    assist_run.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    assist_run.add_argument("--profile", choices=("tiny", "normal", "deep"))
    assist_run.add_argument("--include-graph", action="store_true", default=None)
    assist_run.add_argument("--include-registry", action="store_true", default=None)
    assist_run.add_argument("--include-doctor", action="store_true", default=None)
    assist_run.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    assist_run.add_argument("--audit-log")
    assist_run.add_argument("--measurement-log")
    assist_run.add_argument("--intent", help="Short operator intent for request-draft authoring proposals.")
    assist_run.add_argument("--format", choices=("text", "json"), default="text")
    assist_run.add_argument("--dry-run", action="store_true")
    assist_run.set_defaults(func=cmd_assist_run)

    def add_assist_alias(name: str, flow_name: str, help_text: str, *, takes_ref: bool) -> argparse.ArgumentParser:
        alias = assist_sub.add_parser(name, help=help_text)
        if takes_ref:
            alias.add_argument("ref", help="Workflow ref for the assist flow target.")
        alias.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
        alias.add_argument("--model-profile")
        alias.add_argument("--model")
        alias.add_argument("--ollama-host")
        alias.add_argument("--timeout", type=float)
        alias.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
        alias.add_argument("--profile", choices=("tiny", "normal", "deep"))
        alias.add_argument("--include-graph", action="store_true", default=None)
        alias.add_argument("--include-registry", action="store_true", default=None)
        alias.add_argument("--include-doctor", action="store_true", default=None)
        alias.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
        alias.add_argument("--audit-log")
        alias.add_argument("--measurement-log")
        alias.add_argument("--format", choices=("text", "json"), default="text")
        alias.add_argument("--dry-run", action="store_true")
        alias.set_defaults(func=cmd_assist_run, flow_name=flow_name)
        return alias

    add_assist_alias("summarize-pr", "pr-summary", "Generate a bounded PR summary.", takes_ref=False)
    add_assist_alias("summarize-changelog", "changelog-summary", "Generate a bounded changelog summary.", takes_ref=False)
    add_assist_alias("summarize-validation", "validation-summary", "Summarize shared validation results.", takes_ref=False)
    add_assist_alias("next-step", "next-step", "Suggest the next bounded workflow action for a target doc.", takes_ref=True)
    request_draft_alias = add_assist_alias("request-draft", "request-draft", "Draft bounded request Needs and Context blocks.", takes_ref=False)
    request_draft_alias.add_argument("--intent", required=True, help="Short operator intent to draft the request from.")
    add_assist_alias("spec-first-pass", "spec-first-pass", "Draft a first-pass spec outline from a backlog item.", takes_ref=True)
    add_assist_alias("backlog-groom", "backlog-groom", "Draft a bounded backlog proposal from a request doc.", takes_ref=True)
    add_assist_alias("triage", "triage", "Triage a target request or backlog doc.", takes_ref=True)
    add_assist_alias("handoff", "handoff-packet", "Generate a compact handoff packet for a target workflow doc.", takes_ref=True)
    add_assist_alias("suggest-split", "suggest-split", "Suggest a bounded split for a broad request or backlog item.", takes_ref=True)
    add_assist_alias("diff-risk", "diff-risk", "Classify the current diff risk.", takes_ref=False)
    add_assist_alias("commit-plan", "commit-plan", "Suggest the minimal coherent commit plan for the current diff.", takes_ref=False)
    add_assist_alias("closure-summary", "closure-summary", "Summarize a delivered request, backlog item, or task.", takes_ref=True)
    add_assist_alias("validation-checklist", "validation-checklist", "Generate a validation checklist for the current diff.", takes_ref=False)
    add_assist_alias("doc-consistency", "doc-consistency", "Review workflow docs for consistency issues without mutating them.", takes_ref=False)
    add_assist_alias("changed-surface-summary", "changed-surface-summary", "Summarize the current changed surface deterministically.", takes_ref=False)
    add_assist_alias("release-changelog-status", "release-changelog-status", "Resolve the current curated release changelog contract deterministically.", takes_ref=False)
    add_assist_alias("test-impact-summary", "test-impact-summary", "Summarize deterministic validation impact for the current diff.", takes_ref=False)
    add_assist_alias("hybrid-insights-explainer", "hybrid-insights-explainer", "Explain the current Hybrid Insights report with bounded operator guidance.", takes_ref=False)
    add_assist_alias("windows-compat-risk", "windows-compat-risk", "Review the current change surface for Windows compatibility risk.", takes_ref=False)
    add_assist_alias("review-checklist", "review-checklist", "Generate a bounded review checklist for the current change surface.", takes_ref=False)
    add_assist_alias("doc-link-suggestion", "doc-link-suggestion", "Suggest missing workflow or companion-doc links for a target doc.", takes_ref=True)

    commit_all = assist_sub.add_parser(
        "commit-all",
        help="Suggest or execute a minimal coherent commit plan using the shared hybrid assist runtime.",
    )
    commit_all.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    commit_all.add_argument("--model-profile")
    commit_all.add_argument("--model")
    commit_all.add_argument("--ollama-host")
    commit_all.add_argument("--timeout", type=float)
    commit_all.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    commit_all.add_argument("--profile", choices=("tiny", "normal", "deep"))
    commit_all.add_argument("--include-graph", action="store_true", default=None)
    commit_all.add_argument("--include-registry", action="store_true", default=None)
    commit_all.add_argument("--include-doctor", action="store_true", default=None)
    commit_all.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    commit_all.add_argument("--audit-log")
    commit_all.add_argument("--measurement-log")
    commit_all.add_argument("--format", choices=("text", "json"), default="text")
    commit_all.add_argument("--dry-run", action="store_true")
    commit_all.set_defaults(func=cmd_assist_commit_all)

    prepare_release = assist_sub.add_parser(
        "prepare-release",
        help="Generate changelog via AI if missing, update README badge, commit prep changes, and report readiness.",
    )
    prepare_release.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    prepare_release.add_argument("--model-profile")
    prepare_release.add_argument("--model")
    prepare_release.add_argument("--ollama-host")
    prepare_release.add_argument("--timeout", type=float)
    prepare_release.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    prepare_release.add_argument("--profile", choices=("tiny", "normal", "deep"))
    prepare_release.add_argument("--include-graph", action="store_true", default=None)
    prepare_release.add_argument("--include-registry", action="store_true", default=None)
    prepare_release.add_argument("--include-doctor", action="store_true", default=None)
    prepare_release.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    prepare_release.add_argument("--audit-log")
    prepare_release.add_argument("--measurement-log")
    prepare_release.add_argument("--format", choices=("text", "json"), default="text")
    prepare_release.add_argument("--dry-run", action="store_true")
    prepare_release.set_defaults(func=cmd_assist_prepare_release)

    publish_release = assist_sub.add_parser(
        "publish-release",
        help="Create the release tag, push main and the tag, and publish the GitHub release.",
    )
    publish_release.add_argument("--model-profile")
    publish_release.add_argument("--model")
    publish_release.add_argument("--ollama-host")
    publish_release.add_argument("--timeout", type=float)
    publish_release.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    publish_release.add_argument("--profile", choices=("tiny", "normal", "deep"))
    publish_release.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    publish_release.add_argument("--push", action="store_true", default=False, help="Create tag, push main+tag, and publish the GitHub release.")
    publish_release.add_argument("--draft", action="store_true", default=False, help="Create a draft GitHub release instead of publishing immediately.")
    publish_release.add_argument("--version", default=None, help="Override the version to release.")
    publish_release.add_argument("--audit-log")
    publish_release.add_argument("--measurement-log")
    publish_release.add_argument("--format", choices=("text", "json"), default="text")
    publish_release.add_argument("--dry-run", action="store_true")
    publish_release.set_defaults(func=cmd_assist_publish_release)

    sync_parser = sub.add_parser("sync", help="Sync workflow metadata and closure transitions.")
    sync_sub = sync_parser.add_subparsers(dest="sync_kind", required=True)
    close_eligible = sync_sub.add_parser(
        "close-eligible-requests",
        help="Auto-close requests when all linked backlog items are done.",
    )
    close_eligible.add_argument("--format", choices=("text", "json"), default="text")
    close_eligible.add_argument("--dry-run", action="store_true")
    close_eligible.set_defaults(func=cmd_sync_close_eligible_requests)

    refresh_mermaid = sync_sub.add_parser(
        "refresh-mermaid-signatures",
        help="Refresh stale workflow Mermaid signatures without rewriting the full diagram body.",
    )
    refresh_mermaid.add_argument("--format", choices=("text", "json"), default="text")
    refresh_mermaid.add_argument("--dry-run", action="store_true")
    refresh_mermaid.set_defaults(func=cmd_sync_refresh_mermaid_signatures)

    refresh_ai = sync_sub.add_parser(
        "refresh-ai-context",
        help="Backfill or refresh compact AI Context sections for managed workflow docs.",
    )
    refresh_ai.add_argument("sources", nargs="*", help="Optional workflow refs or paths to limit the refresh.")
    refresh_ai.add_argument("--preview", action="store_true", help="Preview the mutation plan without writing files.")
    refresh_ai.add_argument("--mutation-mode", choices=("direct", "transactional"), help="Override the repo mutation mode for this bulk update.")
    refresh_ai.add_argument("--format", choices=("text", "json"), default="text")
    refresh_ai.add_argument("--dry-run", action="store_true")
    refresh_ai.set_defaults(func=cmd_sync_refresh_ai_context)

    context_pack = sync_sub.add_parser(
        "context-pack",
        help="Build a kit-native compact context-pack artifact from workflow docs.",
    )
    context_pack.add_argument("ref", help="Seed workflow ref for the context pack.")
    context_pack.add_argument("--mode", choices=("summary-only", "diff-first", "full"), default="summary-only")
    context_pack.add_argument("--profile", choices=("tiny", "normal", "deep"), default="normal")
    context_pack.add_argument("--out", help="Write the JSON artifact to this relative path.")
    context_pack.add_argument("--format", choices=("text", "json"), default="text")
    context_pack.add_argument("--dry-run", action="store_true")
    context_pack.set_defaults(func=cmd_sync_context_pack)

    schema_status = sync_sub.add_parser(
        "schema-status",
        help="Report schema-version coverage for workflow docs.",
    )
    schema_status.add_argument("sources", nargs="*", help="Optional workflow refs or paths to scope the scan.")
    schema_status.add_argument("--format", choices=("text", "json"), default="text")
    schema_status.set_defaults(func=cmd_sync_schema_status)

    migrate_schema = sync_sub.add_parser(
        "migrate-schema",
        help="Normalize workflow docs to the current schema version.",
    )
    migrate_schema.add_argument("sources", nargs="*", help="Optional workflow refs or paths to limit the migration.")
    migrate_schema.add_argument("--refresh-ai-context", action="store_true", help="Refresh AI Context while migrating schema.")
    migrate_schema.add_argument("--preview", action="store_true", help="Preview the mutation plan without writing files.")
    migrate_schema.add_argument("--mutation-mode", choices=("direct", "transactional"), help="Override the repo mutation mode for this bulk update.")
    migrate_schema.add_argument("--format", choices=("text", "json"), default="text")
    migrate_schema.add_argument("--dry-run", action="store_true")
    migrate_schema.set_defaults(func=cmd_sync_migrate_schema)

    export_graph = sync_sub.add_parser(
        "export-graph",
        help="Export workflow relationships as a machine-readable graph.",
    )
    export_graph.add_argument("--out", help="Write the JSON graph to this relative path.")
    export_graph.add_argument("--format", choices=("text", "json"), default="text")
    export_graph.add_argument("--dry-run", action="store_true")
    export_graph.set_defaults(func=cmd_sync_export_graph)

    validate_skills = sync_sub.add_parser(
        "validate-skills",
        help="Validate skill packages against the kit contract.",
    )
    validate_skills.add_argument("--format", choices=("text", "json"), default="text")
    validate_skills.set_defaults(func=cmd_sync_validate_skills)

    export_registry = sync_sub.add_parser(
        "export-registry",
        help="Export conventions, governance profiles, capability metadata, and release metadata.",
    )
    export_registry.add_argument("--out", help="Write the JSON registry to this relative path.")
    export_registry.add_argument("--format", choices=("text", "json"), default="text")
    export_registry.add_argument("--dry-run", action="store_true")
    export_registry.set_defaults(func=cmd_sync_export_registry)

    doctor = sync_sub.add_parser(
        "doctor",
        help="Diagnose common Logics kit setup, schema, and skill-package issues.",
    )
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    doctor.set_defaults(func=cmd_sync_doctor)

    benchmark = sync_sub.add_parser(
        "benchmark-skills",
        help="Run a lightweight benchmark over skill-package discovery and validation.",
    )
    benchmark.add_argument("--format", choices=("text", "json"), default="text")
    benchmark.set_defaults(func=cmd_sync_benchmark_skills)

    build_index = sync_sub.add_parser(
        "build-index",
        help="Build or refresh the incremental runtime index used by repeated workflow and skill operations.",
    )
    build_index.add_argument("--force", action="store_true", help="Ignore unchanged cache entries and rebuild the runtime index.")
    build_index.add_argument("--format", choices=("text", "json"), default="text")
    build_index.add_argument("--dry-run", action="store_true")
    build_index.set_defaults(func=cmd_sync_build_index)

    show_config = sync_sub.add_parser(
        "show-config",
        help="Show the effective repo-native Logics configuration merged with kit defaults.",
    )
    show_config.add_argument("--format", choices=("text", "json"), default="text")
    show_config.set_defaults(func=cmd_sync_show_config)

    dispatch_context = sync_sub.add_parser(
        "dispatch-context",
        help="Build the compact local-dispatch context bundle used by the deterministic dispatcher.",
    )
    dispatch_context.add_argument("ref", help="Seed workflow ref for the dispatcher context.")
    dispatch_context.add_argument("--mode", choices=("summary-only", "diff-first", "full"), default=DEFAULT_DISPATCH_CONTEXT_MODE)
    dispatch_context.add_argument("--profile", choices=("tiny", "normal", "deep"), default=DEFAULT_DISPATCH_PROFILE)
    dispatch_context.add_argument("--include-graph", action="store_true", help="Include a local graph slice around the seed ref.")
    dispatch_context.add_argument("--include-registry", action="store_true", help="Include a compact registry summary.")
    dispatch_context.add_argument("--include-doctor", action="store_true", help="Include a doctor summary in the context bundle.")
    dispatch_context.add_argument("--out", help="Write the JSON context bundle to this relative path.")
    dispatch_context.add_argument("--format", choices=("text", "json"), default="text")
    dispatch_context.add_argument("--dry-run", action="store_true")
    dispatch_context.set_defaults(func=cmd_sync_dispatch_context)

    dispatch = sync_sub.add_parser(
        "dispatch",
        help="Validate and optionally execute a local dispatcher decision through whitelisted Logics commands.",
    )
    dispatch.add_argument("ref", help="Seed workflow ref for dispatcher context assembly.")
    decision_source = dispatch.add_mutually_exclusive_group(required=True)
    decision_source.add_argument("--decision-json", help="Inline dispatcher decision payload.")
    decision_source.add_argument("--decision-file", help="Path to a JSON file containing the dispatcher decision payload.")
    decision_source.add_argument("--model", help="Use Ollama with this local model to produce the dispatcher decision.")
    dispatch.add_argument("--ollama-host", default="http://127.0.0.1:11434", help="Base URL for Ollama when --model is used.")
    dispatch.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds for Ollama dispatch.")
    dispatch.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"), default=DEFAULT_DISPATCH_CONTEXT_MODE)
    dispatch.add_argument("--profile", choices=("tiny", "normal", "deep"), default=DEFAULT_DISPATCH_PROFILE)
    dispatch.add_argument("--include-graph", action="store_true", help="Include a local graph slice around the seed ref.")
    dispatch.add_argument("--include-registry", action="store_true", help="Include a compact registry summary.")
    dispatch.add_argument("--include-doctor", action="store_true", help="Include a doctor summary in the context bundle.")
    dispatch.add_argument(
        "--execution-mode",
        choices=("suggestion-only", "execute"),
        default=DEFAULT_DISPATCH_EXECUTION_MODE,
        help="Keep the default suggestion-only posture or explicitly execute the mapped command.",
    )
    dispatch.add_argument("--audit-log", default=DEFAULT_DISPATCH_AUDIT_LOG, help="Relative path to the JSONL dispatcher audit log.")
    dispatch.add_argument("--format", choices=("text", "json"), default="text")
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.set_defaults(func=cmd_sync_dispatch)

    return parser


def _run_json_command(args: argparse.Namespace) -> int:
    stdout_buffer = io.StringIO()
    payload: dict[str, object]
    exit_code = 0

    with redirect_stdout(stdout_buffer):
        try:
            result = args.func(args)
            payload = result if isinstance(result, dict) else {"result": result}
            payload.setdefault("ok", True)
        except HybridAssistError as exc:
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            }
        except DispatcherError as exc:
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            }
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
            payload = {
                "ok": False,
                "error": exc.code if isinstance(exc.code, str) else "command failed",
            }
        except Exception as exc:  # pragma: no cover - defensive JSON contract fallback
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc) or exc.__class__.__name__,
            }

    logs = [line for line in stdout_buffer.getvalue().splitlines() if line.strip()]
    if logs:
        payload["logs"] = logs
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "format", "text") == "json":
        return _run_json_command(args)
    try:
        result = args.func(args)
    except HybridAssistError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except DispatcherError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
