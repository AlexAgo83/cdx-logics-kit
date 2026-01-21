#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DIRS = (
    "logics",
    "logics/architecture",
    "logics/request",
    "logics/backlog",
    "logics/tasks",
    "logics/specs",
)


@dataclass(frozen=True)
class Action:
    kind: str
    path: Path


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


def _plan_actions(repo_root: Path) -> list[Action]:
    actions: list[Action] = []
    for rel in DEFAULT_DIRS:
        path = repo_root / rel
        if not path.exists():
            actions.append(Action("mkdir", path))

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
    args = parser.parse_args(argv)

    repo_root = _resolve_root(args.root)
    actions = _plan_actions(repo_root)
    if not actions:
        print("Logics bootstrap: OK (nothing to do)")
        return 0

    dry_run = args.dry_run or args.check
    _apply(actions, dry_run=dry_run)
    if args.check:
        print("Logics bootstrap: FAIL (actions needed)")
        return 1
    print("Logics bootstrap: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
