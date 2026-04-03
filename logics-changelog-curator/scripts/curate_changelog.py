#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


DOC_REF_PREFIX_RE = re.compile(r"^\s*-\s*\[[^\]]+\]\([^)]+\)\s*-\s*")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
REPO_PATH_STARTERS = (
    "logics/",
    "src/",
    "media/",
    "tests/",
    "scripts/",
    "debug/",
    "changelogs/",
    ".github/",
    ".vscode/",
    ".claude/",
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "package.json",
    "VERSION",
    ".gitattributes",
    ".vscodeignore",
)


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _repo_relative_path_hint(value: str) -> str:
    candidate = value.strip().strip("<>")
    if not candidate:
        return candidate
    if candidate.startswith("file://"):
        candidate = candidate.removeprefix("file://")
    normalized = candidate.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        return value.strip()
    for starter in REPO_PATH_STARTERS:
        if normalized == starter or normalized.startswith(starter):
            return normalized
        marker = f"/{starter}"
        index = normalized.find(marker)
        if index != -1:
            return normalized[index + 1 :]
    return value.strip()


def _sanitize_links(line: str) -> str:
    def repl(match: re.Match[str]) -> str:
        label, target = match.groups()
        cleaned_target = _repo_relative_path_hint(target)
        return f"[{label}]({cleaned_target})"

    return MARKDOWN_LINK_RE.sub(repl, line)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Curate a user-facing changelog from release notes.")
    parser.add_argument("--in", dest="input_path", default="logics/RELEASE_NOTES.md")
    parser.add_argument("--out", default="logics/CHANGELOG.md")
    parser.add_argument("--title", default="Changelog")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    input_path = (repo_root / args.input_path).resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    raw_lines = input_path.read_text(encoding="utf-8").splitlines()
    curated: list[str] = []
    for line in raw_lines:
        if line.lstrip().startswith("- "):
            curated.append(_sanitize_links(DOC_REF_PREFIX_RE.sub("- ", line).strip()))

    lines: list[str] = [f"# {args.title}", "", f"## {date.today().isoformat()}", ""]
    if curated:
        lines.extend(curated)
    else:
        lines.append("_No entries found._")
    lines.append("")

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
