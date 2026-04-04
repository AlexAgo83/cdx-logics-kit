#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DIRS = (
    "logics",
    "logics/architecture",
    "logics/product",
    "logics/request",
    "logics/backlog",
    "logics/tasks",
    "logics/specs",
    "logics/external",
)

GITIGNORE_COMMENT = "# Generated Logics runtime artifacts"
GITIGNORE_ENTRIES = (
    ".env.local",
    "logics/.cache/",
    "logics/.cache/hybrid_assist_audit.jsonl",
    "logics/.cache/hybrid_assist_measurements.jsonl",
    "logics/hybrid_assist_audit.jsonl",
    "logics/hybrid_assist_measurements.jsonl",
    "logics/mutation_audit.jsonl",
)
ENV_COMMENT = "# Generated Logics provider credentials"
ENV_KEYS = (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
)


@dataclass(frozen=True)
class Action:
    kind: str
    path: Path


def _template_instructions_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "instructions.md"


def _template_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "logics.yaml"


def _find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _resolve_root(root_arg: str | None) -> Path:
    if root_arg:
        return Path(root_arg).expanduser().resolve()
    return _find_git_root(Path.cwd()) or Path.cwd().resolve()


def _is_effectively_empty_dir(directory: Path) -> bool:
    if not directory.is_dir():
        return True
    for child in directory.iterdir():
        if child.name == ".gitkeep":
            continue
        return False
    return True


def _missing_gitignore_entries(gitignore_path: Path) -> list[str]:
    if gitignore_path.exists():
        existing_lines = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    else:
        existing_lines = set()
    return [entry for entry in GITIGNORE_ENTRIES if entry not in existing_lines]


def _parse_env_keys(env_path: Path) -> set[str]:
    if not env_path.exists():
        return set()
    keys: set[str] = set()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _env_paths(repo_root: Path) -> tuple[Path, Path]:
    return repo_root / ".env", repo_root / ".env.local"


def _env_target_and_missing_keys(repo_root: Path) -> tuple[Path, list[str]]:
    env_path, env_local_path = _env_paths(repo_root)
    existing_keys = _parse_env_keys(env_path) | _parse_env_keys(env_local_path)
    missing_keys = [key for key in ENV_KEYS if key not in existing_keys]
    if env_local_path.exists() or not env_path.exists():
        return env_local_path, missing_keys
    return env_path, missing_keys


def _render_env(env_path: Path, missing_keys: list[str]) -> str:
    if env_path.exists():
        existing_text = env_path.read_text(encoding="utf-8")
        lines = existing_text.splitlines()
    else:
        existing_text = ""
        lines = []

    if not missing_keys:
        return existing_text if existing_text.endswith("\n") or not existing_text else existing_text + "\n"

    rendered_lines = list(lines)
    if rendered_lines and rendered_lines[-1].strip():
        rendered_lines.append("")
    if ENV_COMMENT not in {line.strip() for line in rendered_lines}:
        rendered_lines.append(ENV_COMMENT)
    rendered_lines.extend(f"{key}=" for key in missing_keys)
    return "\n".join(rendered_lines) + "\n"


def _render_gitignore(gitignore_path: Path) -> str:
    if gitignore_path.exists():
        existing_text = gitignore_path.read_text(encoding="utf-8")
        lines = existing_text.splitlines()
    else:
        existing_text = ""
        lines = []

    missing_entries = _missing_gitignore_entries(gitignore_path)
    if not missing_entries:
        return existing_text if existing_text.endswith("\n") or not existing_text else existing_text + "\n"

    rendered_lines = list(lines)
    if rendered_lines and rendered_lines[-1].strip():
        rendered_lines.append("")
    if GITIGNORE_COMMENT not in {line.strip() for line in rendered_lines}:
        rendered_lines.append(GITIGNORE_COMMENT)
    rendered_lines.extend(missing_entries)
    return "\n".join(rendered_lines) + "\n"


def _plan_actions(repo_root: Path) -> list[Action]:
    actions: list[Action] = []
    for rel in DEFAULT_DIRS:
        path = repo_root / rel
        if not path.exists():
            actions.append(Action("mkdir", path))

    instructions_path = repo_root / "logics" / "instructions.md"
    if not instructions_path.exists():
        actions.append(Action("instructions", instructions_path))

    config_path = repo_root / "logics.yaml"
    if not config_path.exists():
        actions.append(Action("config", config_path))

    gitignore_path = repo_root / ".gitignore"
    if _missing_gitignore_entries(gitignore_path):
        actions.append(Action("gitignore", gitignore_path))

    env_path, missing_env_keys = _env_target_and_missing_keys(repo_root)
    if missing_env_keys:
        actions.append(Action("env", env_path))

    # Only add .gitkeep to empty dirs (and never to logics/skills which may be a submodule).
    for rel in DEFAULT_DIRS:
        if rel == "logics":
            continue
        path = repo_root / rel
        gitkeep = path / ".gitkeep"
        if _is_effectively_empty_dir(path) and not gitkeep.exists():
            actions.append(Action("gitkeep", gitkeep))

    return actions


def _apply(actions: list[Action], dry_run: bool) -> None:
    for action in actions:
        if action.kind == "mkdir":
            if dry_run:
                print(f"[dry-run] mkdir -p {action.path}")
            else:
                action.path.mkdir(parents=True, exist_ok=True)
        elif action.kind == "gitkeep":
            if dry_run:
                print(f"[dry-run] touch {action.path}")
            else:
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text("", encoding="utf-8")
        elif action.kind == "instructions":
            template_path = _template_instructions_path()
            if dry_run:
                print(f"[dry-run] write {action.path} (from {template_path})")
            else:
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text(template_path.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
        elif action.kind == "config":
            template_path = _template_config_path()
            if dry_run:
                print(f"[dry-run] write {action.path} (from {template_path})")
            else:
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text(template_path.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
        elif action.kind == "gitignore":
            if dry_run:
                print(f"[dry-run] update {action.path} (append Logics runtime ignores)")
            else:
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text(_render_gitignore(action.path), encoding="utf-8")
        elif action.kind == "env":
            _, missing_keys = _env_target_and_missing_keys(action.path.parent)
            if dry_run:
                print(f"[dry-run] update {action.path} (append provider credential placeholders)")
            else:
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text(_render_env(action.path, missing_keys), encoding="utf-8")
        else:
            raise SystemExit(f"Unknown action: {action.kind}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Logics folder structure in a repository.")
    parser.add_argument("--root", help="Repository root (defaults to git root or CWD).")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if actions are needed (implies dry-run; does not write).",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    template_path = _template_instructions_path()
    if not template_path.is_file():
        raise SystemExit(f"Missing template: {template_path}")
    config_template_path = _template_config_path()
    if not config_template_path.is_file():
        raise SystemExit(f"Missing template: {config_template_path}")

    repo_root = _resolve_root(args.root)
    actions = _plan_actions(repo_root)
    payload = {
        "ok": True,
        "repo_root": repo_root.as_posix(),
        "actions_needed": [
            {"kind": action.kind, "path": action.path.relative_to(repo_root).as_posix()}
            for action in actions
        ],
        "check": args.check,
        "dry_run": args.dry_run or args.check,
    }
    if not actions:
        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Logics bootstrap: OK (nothing to do)")
        return 0

    dry_run = args.dry_run or args.check
    _apply(actions, dry_run=dry_run)
    if args.check:
        payload["ok"] = False
        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Logics bootstrap: FAIL (actions needed)")
        return 1
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Logics bootstrap: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
