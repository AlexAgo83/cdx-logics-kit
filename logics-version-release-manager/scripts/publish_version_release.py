#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import re

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit("Could not locate git repository root.")


def normalize_version(value: str) -> str:
    match = SEMVER_RE.match(value.strip())
    if not match:
        raise SystemExit(f"Invalid version: {value}")
    return ".".join(match.groups())


def read_version(repo_root: Path) -> str:
    version_path = repo_root / "VERSION"
    if not version_path.is_file():
        raise SystemExit(f"Missing VERSION file at {version_path}")
    return normalize_version(version_path.read_text(encoding="utf-8").strip())


def changelog_path_for_version(repo_root: Path, version: str) -> Path:
    return repo_root / "changelogs" / f"CHANGELOGS_{normalize_version(version).replace('.', '_')}.md"


def git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def ensure_clean_git(repo_root: Path) -> None:
    status = git(repo_root, "status", "--porcelain")
    if status.strip():
        raise SystemExit("Git working tree is not clean.")


def tag_exists(repo_root: Path, tag_name: str) -> bool:
    output = git(repo_root, "tag", "--list", tag_name)
    return bool(output.strip())


def build_release_commands(
    version: str,
    notes_file: Path,
    title: str,
    create_tag: bool,
    push: bool,
    draft: bool,
) -> list[list[str]]:
    normalized = normalize_version(version)
    tag_name = f"v{normalized}"
    commands: list[list[str]] = []
    if create_tag:
        commands.append(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"])
    if push:
        commands.append(["git", "push", "origin", "main"])
        commands.append(["git", "push", "origin", tag_name])
    release_command = [
        "gh",
        "release",
        "create",
        tag_name,
        "--title",
        title,
        "--notes-file",
        str(notes_file),
    ]
    if draft:
        release_command.append("--draft")
    commands.append(release_command)
    return commands


def run_command(repo_root: Path, command: list[str]) -> None:
    completed = subprocess.run(command, cwd=repo_root, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Publish a kit release from VERSION and changelogs/.")
    parser.add_argument("--version", help="Version to publish (defaults to VERSION file).")
    parser.add_argument("--notes-file", help="Release notes file to use.")
    parser.add_argument("--title", help="GitHub release title.")
    parser.add_argument("--create-tag", action="store_true", help="Create the annotated git tag if missing.")
    parser.add_argument("--push", action="store_true", help="Push main and the tag before creating the GitHub release.")
    parser.add_argument("--draft", action="store_true", help="Create the GitHub release as a draft.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without executing them.")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())
    version = normalize_version(args.version) if args.version else read_version(repo_root)
    tag_name = f"v{version}"
    notes_file = Path(args.notes_file).resolve() if args.notes_file else changelog_path_for_version(repo_root, version)
    if not notes_file.is_absolute():
        notes_file = (repo_root / notes_file).resolve()
    if not notes_file.is_file():
        raise SystemExit(f"Missing release notes file: {notes_file}")

    title = args.title or f"Stable {tag_name}"
    if not args.dry_run:
        ensure_clean_git(repo_root)
        if tag_exists(repo_root, tag_name) and args.create_tag:
            raise SystemExit(f"Tag already exists: {tag_name}")

    commands = build_release_commands(
        version=version,
        notes_file=notes_file,
        title=title,
        create_tag=args.create_tag,
        push=args.push,
        draft=args.draft,
    )

    if args.dry_run:
        for command in commands:
            print("DRY-RUN:", " ".join(command))
        return 0

    for command in commands:
        run_command(repo_root, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
