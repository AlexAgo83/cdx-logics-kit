#!/usr/bin/env python3
from __future__ import annotations


import argparse
from copy import deepcopy
import hashlib
import io
import json
import re
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
from logics_flow_hybrid import (  # noqa: F401
    DEFAULT_HYBRID_ROI_RECENT_LIMIT,
    DEFAULT_HYBRID_ROI_WINDOW_DAYS,
    REQUESTED_BACKEND_CHOICES,
    append_jsonl_record,
    build_hybrid_roi_report,
    build_hybrid_audit_record,
    build_measurement_record,
    build_runtime_status,
    build_shared_hybrid_contract,
    collect_git_snapshot,
    default_context_spec,
    execute_hybrid_backend,
    execute_commit_step,
    run_validation_commands,
)
from logics_flow_hybrid_transport_core import _normalize_hybrid_diff_signals
from logics_flow_hybrid_helpers import (  # noqa: F401
    _build_hybrid_result_cache_key,
    _hybrid_audit_log,
    _hybrid_default_backend,
    _hybrid_default_host,
    _hybrid_default_model,
    _hybrid_default_model_profile,
    _hybrid_default_timeout,
    _hybrid_measurement_log,
    _hybrid_model_profiles,
    _hybrid_model_selection,
    _hybrid_result_cache_enabled,
    _hybrid_result_cache_path,
    _hybrid_result_cache_ttl_seconds,
    _load_hybrid_result_cache,
    _next_step_auto_backend,
    _prune_hybrid_result_cache_entries,
    _read_hybrid_result_cache_entry,
    _select_hybrid_backend_for_flow,
    _write_hybrid_result_cache,
    _write_hybrid_result_cache_entry,
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
    _generate_workflow_mermaid,
    _is_doc_done,
    _mark_section_checkboxes_done,
    _parse_indicator,
    _parse_title_from_source,
    _print_decision_summary,
    _render_references_section,
    _render_template,
    _reserve_doc,
    _resolve_doc_path,
    _split_titles,
    _strip_mermaid_blocks,
    validate_generated_workflow_doc_text,
    _template_path,
    _write,
    refresh_ai_context_text,
    refresh_workflow_mermaid_signature_text,
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


_CONTEXT_PACK_CACHE: dict[str, dict[str, object]] = {}

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


def _context_pack_cache_key(
    repo_root: Path,
    seed_ref: str,
    *,
    mode: str,
    profile: str,
    config: dict[str, object] | None,
    changed_paths: list[str],
    ordered_docs: list[WorkflowDocModel],
) -> str:
    payload = {
        "repo_root": str(repo_root.resolve()),
        "seed_ref": seed_ref,
        "mode": mode,
        "profile": profile,
        "config": config or {},
        "changed_paths": changed_paths,
        "docs": [
            {
                "ref": doc.ref,
                "kind": doc.kind,
                "path": doc.path,
                "schema_version": doc.schema_version,
                "status": doc.indicators.get("Status", ""),
                "linked_refs": {prefix: refs for prefix, refs in doc.refs.items() if refs},
            }
            for doc in ordered_docs
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


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
    changed_paths = _git_changed_paths(repo_root) if mode == "diff-first" else []
    cache_key = _context_pack_cache_key(
        repo_root,
        seed_ref,
        mode=mode,
        profile=profile,
        config=config,
        changed_paths=changed_paths,
        ordered_docs=ordered,
    )
    cached_pack = _CONTEXT_PACK_CACHE.get(cache_key)
    if isinstance(cached_pack, dict):
        return deepcopy(cached_pack)
    context_pack_doc_entry = getattr(sys.modules.get(__name__), "_context_pack_doc_entry", _context_pack_doc_entry)
    pack_docs = [context_pack_doc_entry(doc, mode) for doc in ordered]
    payload = {
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
    _CONTEXT_PACK_CACHE[cache_key] = deepcopy(payload)
    return payload


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

__all__ = [name for name in globals() if not name.startswith("__")]
