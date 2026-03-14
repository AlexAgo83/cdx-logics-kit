#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    files: tuple[str, ...]


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


def version_to_tag(version: str) -> str:
    return f"v{normalize_version(version)}"


def changelog_path_for_version(repo_root: Path, version: str) -> Path:
    normalized = normalize_version(version).replace(".", "_")
    return repo_root / "changelogs" / f"CHANGELOGS_{normalized}.md"


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


def detect_previous_tag(repo_root: Path, current_tag: str) -> str | None:
    tags = [line.strip() for line in git(repo_root, "tag", "--sort=-creatordate").splitlines() if line.strip()]
    for tag in tags:
        if tag != current_tag:
            return tag
    return None


def list_commits(repo_root: Path, previous_tag: str | None) -> list[Commit]:
    rev_range = f"{previous_tag}..HEAD" if previous_tag else "HEAD"
    log_output = git(repo_root, "log", "--reverse", "--format=%H%x1f%s", rev_range)
    commits: list[Commit] = []
    for line in log_output.splitlines():
        if not line.strip():
            continue
        sha, subject = line.split("\x1f", 1)
        files_output = git(repo_root, "show", "--pretty=", "--name-only", sha)
        files = tuple(file_line.strip() for file_line in files_output.splitlines() if file_line.strip())
        commits.append(Commit(sha=sha, subject=subject.strip(), files=files))
    return commits


def classify_commit(commit: Commit) -> str:
    files = commit.files
    if any(
        file.startswith(".github/")
        or file.startswith("tests/")
        or "workflow_audit" in file
        or "logics-doc-linter" in file
        or "release_gate" in file
        for file in files
    ):
        return "Validation and CI"
    if any(
        file.startswith("changelogs/")
        or file == "CHANGELOG.md"
        or file == "VERSION"
        or file.startswith("logics-version-")
        for file in files
    ):
        return "Release and Changelog Automation"
    if any(file in {"README.md", "CONTRIBUTING.md"} or file.endswith("/SKILL.md") for file in files):
        return "Documentation"
    return "Workflow and Skills"


def build_lines(version: str, previous_tag: str | None, commits: list[Commit]) -> list[str]:
    previous_label = previous_tag.removeprefix("v") if previous_tag else "start"
    current_label = normalize_version(version)
    section_order = [
        "Workflow and Skills",
        "Validation and CI",
        "Release and Changelog Automation",
        "Documentation",
    ]
    grouped: dict[str, list[Commit]] = {section: [] for section in section_order}
    for commit in commits:
        grouped.setdefault(classify_commit(commit), []).append(commit)

    lines: list[str] = [
        f"# Changelog (`{previous_label} -> {current_label}`)",
        "",
        "## Major Highlights",
        "",
    ]
    if commits:
        lines.append(f"- Generated from {len(commits)} commit(s) between `{previous_tag or 'repo start'}` and `HEAD` on {date.today().isoformat()}.")
        touched_sections = [section for section in section_order if grouped.get(section)]
        if touched_sections:
            lines.append(f"- Touched areas: {', '.join(touched_sections)}.")
        for commit in commits[:3]:
            lines.append(f"- {commit.subject}")
    else:
        lines.append("- No commits found in the selected range.")
    lines.extend(["", "## Generated Commit Summary", ""])

    for section in section_order:
        section_commits = grouped.get(section) or []
        if not section_commits:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for commit in section_commits:
            lines.append(f"- {commit.subject}")
        lines.append("")

    lines.extend(
        [
            "## Validation and Regression Evidence",
            "",
            "- Add validation commands or evidence here before publishing the release.",
            "",
        ]
    )
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a versioned changelog entry for the kit.")
    parser.add_argument("--version", help="Version to generate (defaults to VERSION file).")
    parser.add_argument("--previous-tag", help="Previous tag to use as the changelog baseline.")
    parser.add_argument("--out", help="Output path. Defaults to changelogs/CHANGELOGS_<version>.md")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the output file if it exists.")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())
    version = normalize_version(args.version) if args.version else read_version(repo_root)
    current_tag = version_to_tag(version)
    previous_tag = args.previous_tag or detect_previous_tag(repo_root, current_tag)
    output_path = Path(args.out).resolve() if args.out else changelog_path_for_version(repo_root, version)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output_path}")

    commits = list_commits(repo_root, previous_tag)
    lines = build_lines(version, previous_tag, commits)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        printable = output_path.relative_to(repo_root)
    except ValueError:
        printable = output_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
