#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logics_flow_config import get_config_value
from logics_flow_models import SkillPackageModel, WorkflowDocModel, iter_skill_packages, parse_skill_package, parse_workflow_doc
from logics_flow_support import DOC_KINDS


@dataclass(frozen=True)
class RuntimeIndexStats:
    workflow_doc_count: int
    skill_count: int
    cache_hits: int
    cache_misses: int
    removed_entries: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _entry_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def _load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.is_file():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _collect_workflow_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for kind in DOC_KINDS.values():
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        paths.extend(sorted(directory.glob(f"{kind.prefix}_*.md")))
    return sorted(paths)


def _collect_skill_paths(repo_root: Path) -> list[Path]:
    skills_root = repo_root / "logics" / "skills"
    if not skills_root.is_dir():
        return []
    paths: list[Path] = []
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        if not (skill_dir / "SKILL.md").is_file() and not (skill_dir / "agents" / "openai.yaml").is_file():
            continue
        paths.append(skill_dir)
    return paths


def _rebuild_workflow_doc(path: Path, repo_root: Path) -> dict[str, Any]:
    return parse_workflow_doc(path, repo_root=repo_root).to_dict()


def _rebuild_skill_package(path: Path, repo_root: Path) -> dict[str, Any]:
    return parse_skill_package(path, repo_root=repo_root).to_dict()


def _restore_workflow_doc(payload: dict[str, Any]) -> WorkflowDocModel:
    return WorkflowDocModel(**payload)


def _restore_skill_package(payload: dict[str, Any]) -> SkillPackageModel:
    return SkillPackageModel(**payload)


def build_runtime_index(
    repo_root: Path,
    *,
    config: dict[str, Any],
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    cache_rel = str(get_config_value(config, "index", "path", default="logics/.cache/runtime_index.json"))
    cache_path = (repo_root / cache_rel).resolve()
    cache_enabled = bool(get_config_value(config, "index", "enabled", default=True))
    previous = _load_cache(cache_path) if cache_enabled and not force else {}
    previous_workflow = previous.get("workflow_docs", {}) if isinstance(previous.get("workflow_docs"), dict) else {}
    previous_skills = previous.get("skill_packages", {}) if isinstance(previous.get("skill_packages"), dict) else {}

    workflow_docs: dict[str, dict[str, Any]] = {}
    skill_packages: dict[str, dict[str, Any]] = {}
    cache_hits = 0
    cache_misses = 0

    workflow_paths = _collect_workflow_paths(repo_root)
    current_workflow_keys = {path.relative_to(repo_root).as_posix() for path in workflow_paths}
    for path in workflow_paths:
        rel = path.relative_to(repo_root).as_posix()
        signature = _entry_signature(path)
        cached = previous_workflow.get(rel)
        if (
            cache_enabled
            and not force
            and isinstance(cached, dict)
            and cached.get("signature") == signature
            and isinstance(cached.get("data"), dict)
        ):
            workflow_docs[rel] = {"signature": signature, "data": cached["data"]}
            cache_hits += 1
        else:
            workflow_docs[rel] = {"signature": signature, "data": _rebuild_workflow_doc(path, repo_root)}
            cache_misses += 1

    skill_paths = _collect_skill_paths(repo_root)
    current_skill_keys = {path.relative_to(repo_root).as_posix() for path in skill_paths}
    for path in skill_paths:
        rel = path.relative_to(repo_root).as_posix()
        signature_parts = []
        for tracked in (path / "SKILL.md", path / "agents" / "openai.yaml"):
            if tracked.is_file():
                signature_parts.append(_entry_signature(tracked))
        signature = {"files": signature_parts}
        cached = previous_skills.get(rel)
        if (
            cache_enabled
            and not force
            and isinstance(cached, dict)
            and cached.get("signature") == signature
            and isinstance(cached.get("data"), dict)
        ):
            skill_packages[rel] = {"signature": signature, "data": cached["data"]}
            cache_hits += 1
        else:
            skill_packages[rel] = {"signature": signature, "data": _rebuild_skill_package(path, repo_root)}
            cache_misses += 1

    previous_workflow_keys = set(previous_workflow.keys())
    previous_skill_keys = set(previous_skills.keys())
    removed_entries = len((previous_workflow_keys - current_workflow_keys) | (previous_skill_keys - current_skill_keys))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_path": cache_path.relative_to(repo_root).as_posix(),
        "workflow_docs": workflow_docs,
        "skill_packages": skill_packages,
        "stats": RuntimeIndexStats(
            workflow_doc_count=len(workflow_docs),
            skill_count=len(skill_packages),
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            removed_entries=removed_entries,
        ).to_dict(),
    }
    if cache_enabled and not dry_run:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_runtime_index(repo_root: Path, *, config: dict[str, Any], force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    return build_runtime_index(repo_root, config=config, force=force, dry_run=dry_run)


def indexed_workflow_docs(repo_root: Path, *, config: dict[str, Any], force: bool = False) -> tuple[dict[str, WorkflowDocModel], dict[str, int]]:
    payload = load_runtime_index(repo_root, config=config, force=force)
    docs = {
        entry["data"]["ref"]: _restore_workflow_doc(entry["data"])
        for entry in payload["workflow_docs"].values()
    }
    return docs, dict(payload["stats"])


def indexed_skill_packages(repo_root: Path, *, config: dict[str, Any], force: bool = False) -> tuple[list[SkillPackageModel], dict[str, int]]:
    payload = load_runtime_index(repo_root, config=config, force=force)
    packages = [_restore_skill_package(entry["data"]) for entry in payload["skill_packages"].values()]
    return packages, dict(payload["stats"])
