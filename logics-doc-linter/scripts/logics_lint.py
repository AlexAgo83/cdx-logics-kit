#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
import subprocess


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


def _has_indicator(lines: list[str], key: str) -> bool:
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*.+\s*$")
    return any(pattern.match(line) for line in lines)


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
    for args in (["diff", "--name-only", "--diff-filter=ACMRT"],
                 ["diff", "--cached", "--name-only", "--diff-filter=ACMRT"]):
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


def _lint_file(path: Path, kind: Kind) -> list[str]:
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

    return issues


def main(argv: list[str]) -> int:
    repo_root = _find_repo_root(Path.cwd())
    all_issues: list[tuple[Path, list[str]]] = []
    modified_paths = _git_modified_paths(repo_root)

    for kind in KINDS.values():
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            issues = _lint_file(path, kind)
            rel_path = path.relative_to(repo_root)
            if rel_path in modified_paths:
                required = {"Understanding", "Confidence"}
                if kind.requires_progress:
                    required.add("Progress")
                if not _diff_has_indicator_changes(repo_root, rel_path, required):
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
