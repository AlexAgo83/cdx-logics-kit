#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Kind:
    directory: str
    prefix: str
    requires_progress: bool


KINDS = {
    "request": Kind("logics/request", "req", False),
    "backlog": Kind("logics/backlog", "item", True),
    "task": Kind("logics/tasks", "task", True),
}

ALLOWED_STATUSES = {
    "draft",
    "ready",
    "in progress",
    "blocked",
    "done",
    "archived",
}


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _extract_first_heading(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("## "):
            return line
    return None


def _indicator_value(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*(.+)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def _has_indicator(lines: list[str], key: str) -> bool:
    return _indicator_value(lines, key) is not None


def _run_git(repo_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _git_modified_paths(repo_root: Path) -> set[Path]:
    paths: set[Path] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMRT"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRT"],
    ):
        output = _run_git(repo_root, args)
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            paths.add(Path(line))
    return paths


def _diff_has_indicator_changes(repo_root: Path, rel_path: Path, indicators: set[str]) -> bool:
    if not indicators:
        return True
    diff = _run_git(repo_root, ["diff", "--unified=0", "--", str(rel_path)])
    diff += _run_git(repo_root, ["diff", "--cached", "--unified=0", "--", str(rel_path)])
    if not diff:
        return False
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        for key in indicators:
            if f"> {key}:" in line:
                return True
    return False


def _diff_is_status_only_normalization(repo_root: Path, rel_path: Path) -> bool:
    diff = _run_git(repo_root, ["diff", "--unified=0", "--", str(rel_path)])
    diff += _run_git(repo_root, ["diff", "--cached", "--unified=0", "--", str(rel_path)])
    if not diff:
        return False

    saw_change = False
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith(("+++ ", "--- ")):
            continue

        changed = line[1:].strip()
        if not changed:
            continue

        saw_change = True
        if changed.startswith("> Status:"):
            continue
        return False

    return saw_change


def _lint_file(path: Path, kind: Kind, require_status: bool) -> list[str]:
    issues: list[str] = []
    name = path.name
    if not re.match(rf"^{re.escape(kind.prefix)}_\d{{3}}_[a-z0-9_]+\.md$", name):
        issues.append(f"bad filename: {name}")

    stem = path.stem
    lines = _read_lines(path)
    heading = _extract_first_heading(lines)
    if heading is None:
        issues.append("missing first heading (expected '## ...')")
    else:
        expected_prefix = f"## {stem} - "
        if not heading.startswith(expected_prefix):
            issues.append(f"bad heading: expected '{expected_prefix}<Title>'")

    for key in ("From version", "Understanding", "Confidence"):
        if not _has_indicator(lines, key):
            issues.append(f"missing indicator: {key}")

    if kind.requires_progress and not _has_indicator(lines, "Progress"):
        issues.append("missing indicator: Progress")

    status_value = _indicator_value(lines, "Status")
    if status_value is None:
        if require_status:
            issues.append("missing indicator: Status")
    elif " ".join(status_value.split()).lower() not in ALLOWED_STATUSES:
        issues.append(
            "invalid Status value: "
            + status_value
            + " (allowed: Draft | Ready | In progress | Blocked | Done | Archived)"
        )

    return issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_lint.py",
        description="Lint Logics docs (filenames, headings, indicators).",
    )
    parser.add_argument(
        "--require-status",
        action="store_true",
        help="Require `Status` indicator in all request/backlog/task docs.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    all_issues: list[tuple[Path, list[str]]] = []
    modified_paths = _git_modified_paths(repo_root)

    for kind in KINDS.values():
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            issues = _lint_file(path, kind, require_status=args.require_status)
            rel_path = path.relative_to(repo_root)
            if rel_path in modified_paths:
                required = {"Understanding", "Confidence"}
                if kind.requires_progress:
                    required.add("Progress")
                if (
                    not _diff_has_indicator_changes(repo_root, rel_path, required)
                    and not _diff_is_status_only_normalization(repo_root, rel_path)
                ):
                    issues.append(
                        "modified without updating indicators: "
                        + ", ".join(sorted(required))
                    )
            if issues:
                all_issues.append((rel_path, issues))

    if not all_issues:
        print("Logics lint: OK")
        return 0

    print("Logics lint: FAILED")
    for path, issues in all_issues:
        for issue in issues:
            print(f"- {path}: {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
