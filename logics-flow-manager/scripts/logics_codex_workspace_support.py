#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


ENV_GLOBAL_HOME = "LOGICS_CODEX_GLOBAL_HOME"
ENV_WORKSPACES_HOME = "LOGICS_CODEX_WORKSPACES_HOME"
SCHEMA_VERSION = 1
MANIFEST_NAME = "logics-codex-overlay.json"
REGISTRY_NAME = "logics-codex-workspaces.json"


@dataclass
class PublishedEntry:
    name: str
    source_path: str
    destination_path: str
    source_scope: str
    mode: str
    source_mtime_ns: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class SharedAssetEntry:
    name: str
    source_path: str
    destination_path: str
    kind: str
    mode: str
    present: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class OverlayIdentity:
    workspace_id: str
    repo_root: str
    overlay_root: str
    codex_home: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def resolve_repo_root(raw_repo: str | None) -> Path:
    if raw_repo:
        return _find_repo_root(Path(raw_repo))
    return _find_repo_root(Path.cwd())


def codex_global_home() -> Path:
    raw = os.environ.get(ENV_GLOBAL_HOME)
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def codex_workspaces_home() -> Path:
    raw = os.environ.get(ENV_WORKSPACES_HOME)
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codex-workspaces").resolve()


def compute_workspace_id(repo_root: Path) -> str:
    real_root = str(repo_root.resolve())
    digest = hashlib.sha256(real_root.encode("utf-8")).hexdigest()[:12]
    slug = repo_root.name.lower().replace(" ", "-") or "workspace"
    safe_slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug).strip("-") or "workspace"
    return f"{safe_slug}-{digest}"


def overlay_identity(repo_root: Path) -> OverlayIdentity:
    workspace_id = compute_workspace_id(repo_root)
    overlay_root = codex_workspaces_home() / workspace_id
    return OverlayIdentity(
        workspace_id=workspace_id,
        repo_root=str(repo_root.resolve()),
        overlay_root=str(overlay_root),
        codex_home=str(overlay_root),
    )


def manifest_path(identity: OverlayIdentity) -> Path:
    return Path(identity.overlay_root) / MANIFEST_NAME


def registry_path() -> Path:
    return codex_global_home() / REGISTRY_NAME


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON file at {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _registry_payload() -> dict[str, Any]:
    payload = _load_json(registry_path(), {"schema_version": SCHEMA_VERSION, "workspaces": []})
    if not isinstance(payload, dict):
        return {"schema_version": SCHEMA_VERSION, "workspaces": []}
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("workspaces", [])
    return payload


def update_registry(identity: OverlayIdentity, *, synced_at: str | None = None) -> None:
    payload = _registry_payload()
    workspaces = [entry for entry in payload.get("workspaces", []) if entry.get("workspace_id") != identity.workspace_id]
    workspaces.append(
        {
            "workspace_id": identity.workspace_id,
            "repo_root": identity.repo_root,
            "overlay_root": identity.overlay_root,
            "codex_home": identity.codex_home,
            "synced_at": synced_at,
            "identity_mode": "realpath-hash",
        }
    )
    payload["workspaces"] = sorted(workspaces, key=lambda entry: entry.get("workspace_id", ""))
    _write_json(registry_path(), payload)


def remove_registry_entry(workspace_id: str) -> None:
    payload = _registry_payload()
    payload["workspaces"] = [entry for entry in payload.get("workspaces", []) if entry.get("workspace_id") != workspace_id]
    _write_json(registry_path(), payload)


def discover_repo_skills(repo_root: Path) -> list[Path]:
    skills_root = repo_root / "logics" / "skills"
    if not skills_root.is_dir():
        return []
    skills: list[Path] = []
    for candidate in sorted(skills_root.iterdir()):
        if not candidate.is_dir():
            continue
        if (candidate / "SKILL.md").is_file():
            skills.append(candidate)
    return skills


def discover_global_skills(global_home: Path, excluded_names: set[str]) -> list[Path]:
    skills_root = global_home / "skills"
    if not skills_root.is_dir():
        return []
    skills: list[Path] = []
    for candidate in sorted(skills_root.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name in excluded_names:
            continue
        if candidate.name.startswith("."):
            continue
        if (candidate / "SKILL.md").is_file():
            skills.append(candidate)
    return skills


def _remove_path(target: Path) -> None:
    if not target.exists() and not target.is_symlink():
        return
    if target.is_symlink() or target.is_file():
        target.unlink()
        return
    shutil.rmtree(target)


def _link_directory(source: Path, destination: Path, mode: str) -> str:
    if mode == "symlink":
        os.symlink(source, destination, target_is_directory=True)
        return "symlink"
    if mode == "junction":
        if os.name != "nt":
            raise OSError("junction mode is only supported on Windows")
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(destination), str(source)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise OSError(completed.stderr.strip() or completed.stdout.strip() or "mklink /J failed")
        return "junction"
    raise OSError(f"Unsupported link mode for directory: {mode}")


def _materialize_directory(source: Path, destination: Path, publication_mode: str) -> str:
    _remove_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preferred_modes = {
        "copy": ["copy"],
        "symlink": ["symlink"],
        "junction": ["junction"],
        "auto": ["junction", "symlink", "copy"] if os.name == "nt" else ["symlink", "copy"],
    }.get(publication_mode)
    if preferred_modes is None:
        raise SystemExit(f"Unsupported publication mode: {publication_mode}")

    errors: list[str] = []
    for mode in preferred_modes:
        try:
            if mode == "copy":
                shutil.copytree(source, destination)
                return "copy"
            return _link_directory(source, destination, mode)
        except OSError as exc:
            errors.append(f"{mode}: {exc}")
            _remove_path(destination)
            continue
    raise SystemExit(f"Could not materialize {source} -> {destination}. Tried {', '.join(errors)}")


def _materialize_file(source: Path, destination: Path, publication_mode: str) -> str:
    _remove_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preferred_modes = {
        "copy": ["copy"],
        "symlink": ["symlink"],
        "auto": ["symlink", "copy"],
    }.get(publication_mode)
    if preferred_modes is None:
        raise SystemExit(f"Unsupported publication mode for file: {publication_mode}")

    errors: list[str] = []
    for mode in preferred_modes:
        try:
            if mode == "copy":
                shutil.copy2(source, destination)
                return "copy"
            os.symlink(source, destination)
            return "symlink"
        except OSError as exc:
            errors.append(f"{mode}: {exc}")
            _remove_path(destination)
            continue
    raise SystemExit(f"Could not materialize {source} -> {destination}. Tried {', '.join(errors)}")


def _detect_entry_mode(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    if path.is_symlink():
        return "symlink"
    return "copy"


def _skill_mtime(path: Path) -> int | None:
    marker = path / "SKILL.md"
    if marker.exists():
        return marker.stat().st_mtime_ns
    if path.exists():
        return path.stat().st_mtime_ns
    return None


def _manifest_payload(
    identity: OverlayIdentity,
    repo_root: Path,
    publication_mode: str,
    repo_entries: list[PublishedEntry],
    global_entries: list[PublishedEntry],
    shared_entries: list[SharedAssetEntry],
    shadowed_global_skills: list[str],
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": identity.workspace_id,
        "identity_mode": "realpath-hash",
        "repo_root": str(repo_root.resolve()),
        "overlay_root": identity.overlay_root,
        "codex_home": identity.codex_home,
        "publication_mode": publication_mode,
        "policy": {
            "repo_skills_precedence": "repo-over-global",
            "global_system_skills": "referenced-when-available",
            "global_user_skills": "included-unless-shadowed",
            "moved_repo_behavior": "new-overlay-created-old-overlay-reported-stale",
        },
        "shadowed_global_skills": sorted(shadowed_global_skills),
        "repo_skill_entries": [asdict(entry) for entry in repo_entries],
        "global_skill_entries": [asdict(entry) for entry in global_entries],
        "shared_asset_entries": [asdict(entry) for entry in shared_entries],
        "created_at": now,
        "updated_at": now,
    }


def sync_workspace(repo_root: Path, publication_mode: str = "auto") -> dict[str, Any]:
    identity = overlay_identity(repo_root)
    overlay_root = Path(identity.overlay_root)
    skills_root = overlay_root / "skills"
    repo_skills = discover_repo_skills(repo_root)
    repo_skill_names = {skill.name for skill in repo_skills}
    global_home = codex_global_home()
    shared_entries: list[SharedAssetEntry] = []
    repo_entries: list[PublishedEntry] = []
    global_entries: list[PublishedEntry] = []
    shadowed_global_skills: list[str] = []

    overlay_root.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    for current in skills_root.iterdir() if skills_root.exists() else []:
        _remove_path(current)

    for shared_file in ("auth.json", "config.toml"):
        source = global_home / shared_file
        destination = overlay_root / shared_file
        if source.exists():
            mode = _materialize_file(source, destination, publication_mode if publication_mode != "junction" else "auto")
            shared_entries.append(
                SharedAssetEntry(
                    name=shared_file,
                    source_path=str(source),
                    destination_path=str(destination),
                    kind="file",
                    mode=mode,
                    present=True,
                )
            )
        else:
            shared_entries.append(
                SharedAssetEntry(
                    name=shared_file,
                    source_path=str(source),
                    destination_path=str(destination),
                    kind="file",
                    mode="missing",
                    present=False,
                    notes=["Global Codex asset not found."],
                )
            )

    system_skill = global_home / "skills" / ".system"
    system_destination = skills_root / ".system"
    if system_skill.exists():
        mode = _materialize_directory(system_skill, system_destination, publication_mode)
        shared_entries.append(
            SharedAssetEntry(
                name=".system",
                source_path=str(system_skill),
                destination_path=str(system_destination),
                kind="directory",
                mode=mode,
                present=True,
            )
        )
    else:
        shared_entries.append(
            SharedAssetEntry(
                name=".system",
                source_path=str(system_skill),
                destination_path=str(system_destination),
                kind="directory",
                mode="missing",
                present=False,
                notes=["Global Codex system skills directory not found."],
            )
        )

    for skill in repo_skills:
        destination = skills_root / skill.name
        mode = _materialize_directory(skill, destination, publication_mode)
        repo_entries.append(
            PublishedEntry(
                name=skill.name,
                source_path=str(skill),
                destination_path=str(destination),
                source_scope="repo",
                mode=mode,
                source_mtime_ns=_skill_mtime(skill),
            )
        )

    for skill in discover_global_skills(global_home, repo_skill_names):
        destination = skills_root / skill.name
        mode = _materialize_directory(skill, destination, publication_mode)
        global_entries.append(
            PublishedEntry(
                name=skill.name,
                source_path=str(skill),
                destination_path=str(destination),
                source_scope="global",
                mode=mode,
                source_mtime_ns=_skill_mtime(skill),
            )
        )

    for skill in discover_global_skills(global_home, set()):
        if skill.name in repo_skill_names:
            shadowed_global_skills.append(skill.name)

    payload = _manifest_payload(identity, repo_root, publication_mode, repo_entries, global_entries, shared_entries, shadowed_global_skills)
    _write_json(manifest_path(identity), payload)
    update_registry(identity, synced_at=payload["updated_at"])
    return payload


def _read_manifest(identity: OverlayIdentity) -> dict[str, Any] | None:
    path = manifest_path(identity)
    if not path.exists():
        return None
    return _load_json(path, None)


def _entry_issues(entry: dict[str, Any], *, require_target: bool = False) -> list[str]:
    issues: list[str] = []
    source = Path(entry["source_path"])
    destination = Path(entry["destination_path"])
    if not source.exists():
        issues.append(f"Source is missing for `{entry['name']}`.")
    if require_target and not destination.exists() and not destination.is_symlink():
        issues.append(f"Destination is missing for `{entry['name']}`.")
    if entry.get("mode") == "copy" and source.exists() and destination.exists():
        source_mtime = entry.get("source_mtime_ns")
        current_source_mtime = _skill_mtime(source)
        if source_mtime is not None and current_source_mtime is not None and current_source_mtime != source_mtime:
            issues.append(f"Copied overlay content is stale for `{entry['name']}`.")
    return issues


def status_for_repo(repo_root: Path) -> dict[str, Any]:
    identity = overlay_identity(repo_root)
    overlay_root = Path(identity.overlay_root)
    manifest = _read_manifest(identity)
    issues: list[str] = []
    warnings: list[str] = []
    repo_skills = discover_repo_skills(repo_root)
    repo_skill_names = sorted(skill.name for skill in repo_skills)

    if not overlay_root.exists():
        issues.append("Overlay root is missing.")
    if manifest is None:
        issues.append("Overlay manifest is missing.")
    else:
        if manifest.get("repo_root") != str(repo_root.resolve()):
            warnings.append("Manifest repo root differs from the current repository path.")
        manifest_repo_entries = manifest.get("repo_skill_entries", [])
        manifest_global_entries = manifest.get("global_skill_entries", [])
        manifest_shared_entries = manifest.get("shared_asset_entries", [])

        manifest_repo_names = sorted(entry.get("name", "") for entry in manifest_repo_entries)
        if manifest_repo_names != repo_skill_names:
            issues.append("Repo skill set drift detected between the repository and the overlay manifest.")

        for entry in manifest_repo_entries:
            issues.extend(_entry_issues(entry, require_target=True))
        for entry in manifest_global_entries:
            issues.extend(_entry_issues(entry, require_target=True))
        for entry in manifest_shared_entries:
            source = Path(entry["source_path"])
            destination = Path(entry["destination_path"])
            if entry.get("present") and not source.exists():
                issues.append(f"Shared asset source is missing for `{entry['name']}`.")
            if entry.get("present") and not destination.exists() and not destination.is_symlink():
                issues.append(f"Shared asset destination is missing for `{entry['name']}`.")

        global_home = codex_global_home()
        expected_global_names = sorted(skill.name for skill in discover_global_skills(global_home, set(repo_skill_names)))
        manifest_global_names = sorted(entry.get("name", "") for entry in manifest_global_entries)
        if expected_global_names != manifest_global_names:
            warnings.append("Global non-Logics skill projection has changed since the last sync.")

    status = "healthy"
    if issues:
        status = "broken" if manifest is None else "stale"
    elif warnings:
        status = "warning"

    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": identity.workspace_id,
        "repo_root": identity.repo_root,
        "overlay_root": identity.overlay_root,
        "codex_home": identity.codex_home,
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "repo_skill_names": repo_skill_names,
        "repair_hint": "Run `sync` to rebuild the overlay, or `doctor --fix` for deterministic repair.",
        "manifest_present": manifest is not None,
        "manifest": manifest,
    }


def status_for_registry_entry(entry: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(str(entry.get("repo_root", "")))
    overlay_root = Path(str(entry.get("overlay_root", "")))
    workspace_id = str(entry.get("workspace_id", ""))
    issues: list[str] = []
    warnings: list[str] = []
    if not repo_root.exists():
        issues.append("Registered repository path no longer exists.")
    if not overlay_root.exists():
        issues.append("Registered overlay root no longer exists.")
    manifest = _load_json(overlay_root / MANIFEST_NAME, None) if overlay_root.exists() else None
    if manifest is None:
        issues.append("Registered overlay manifest is missing.")
    status = "healthy"
    if issues:
        status = "stale"
    elif warnings:
        status = "warning"
    return {
        "workspace_id": workspace_id,
        "repo_root": str(repo_root),
        "overlay_root": str(overlay_root),
        "codex_home": str(entry.get("codex_home", overlay_root)),
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "manifest_present": manifest is not None,
    }


def all_registered_statuses() -> list[dict[str, Any]]:
    payload = _registry_payload()
    return [status_for_registry_entry(entry) for entry in payload.get("workspaces", [])]


def doctor_workspace(repo_root: Path, *, fix: bool, publication_mode: str = "auto") -> dict[str, Any]:
    status = status_for_repo(repo_root)
    if not fix:
        return status
    if status["status"] == "healthy":
        status["repair_result"] = "No repair needed."
        return status
    repaired = sync_workspace(repo_root, publication_mode=publication_mode)
    refreshed = status_for_repo(repo_root)
    refreshed["repair_result"] = "Overlay rebuilt from repository state."
    refreshed["synced_manifest"] = repaired
    return refreshed


def clean_workspace(repo_root: Path) -> dict[str, Any]:
    identity = overlay_identity(repo_root)
    overlay_root = Path(identity.overlay_root)
    existed = overlay_root.exists()
    _remove_path(overlay_root)
    remove_registry_entry(identity.workspace_id)
    return {
        "workspace_id": identity.workspace_id,
        "overlay_root": identity.overlay_root,
        "repo_root": identity.repo_root,
        "removed": existed,
    }


def register_workspace(repo_root: Path, *, sync_now: bool, publication_mode: str = "auto") -> dict[str, Any]:
    identity = overlay_identity(repo_root)
    update_registry(identity, synced_at=None)
    if sync_now:
        return sync_workspace(repo_root, publication_mode=publication_mode)
    return {
        "workspace_id": identity.workspace_id,
        "repo_root": identity.repo_root,
        "overlay_root": identity.overlay_root,
        "codex_home": identity.codex_home,
        "registered": True,
        "synced": False,
    }


def run_workspace_command(
    repo_root: Path,
    command: Sequence[str],
    *,
    publication_mode: str = "auto",
    sync_before_run: bool = True,
    print_only: bool = False,
) -> int:
    if sync_before_run:
        sync_workspace(repo_root, publication_mode=publication_mode)
    identity = overlay_identity(repo_root)
    env = dict(os.environ)
    env["CODEX_HOME"] = identity.codex_home
    resolved_command = list(command) if command else ["codex"]
    if print_only:
        print(json.dumps({"workspace_id": identity.workspace_id, "codex_home": identity.codex_home, "command": resolved_command}, indent=2))
        return 0
    completed = subprocess.run(resolved_command, env=env, check=False)
    return completed.returncode


def print_payload(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, list):
        for entry in payload:
            print_status_payload(entry)
            print("")
        return
    if isinstance(payload, dict):
        print_status_payload(payload)
        return
    print(payload)


def print_status_payload(payload: dict[str, Any]) -> None:
    print(f"Workspace: {payload.get('workspace_id', '(unknown)')}")
    if payload.get("repo_root"):
        print(f"Repo root: {payload['repo_root']}")
    if payload.get("codex_home"):
        print(f"CODEX_HOME: {payload['codex_home']}")
    if payload.get("status"):
        print(f"Status: {payload['status']}")
    issues = payload.get("issues", [])
    warnings = payload.get("warnings", [])
    if issues:
        print("Issues:")
        for issue in issues:
            print(f"- {issue}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    repair_hint = payload.get("repair_hint")
    if repair_hint:
        print(f"Repair: {repair_hint}")
    if payload.get("removed") is True:
        print("Overlay removed.")
    if payload.get("registered") is True and payload.get("synced") is False:
        print("Workspace registered. Run sync to materialize the overlay.")


def ensure_command_payload(command: Sequence[str]) -> list[str]:
    values = list(command)
    if values and values[0] == "--":
        return values[1:]
    return values


def fail_if_windows_junction_requested_on_non_windows(mode: str) -> None:
    if mode == "junction" and os.name != "nt":
        raise SystemExit("`junction` publication mode is only supported on Windows.")

