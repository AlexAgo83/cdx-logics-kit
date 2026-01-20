#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    path: Path
    doc_ref: str
    title: str
    progress: str | None


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _parse_doc(path: Path) -> Entry:
    lines = path.read_text(encoding="utf-8").splitlines()
    doc_ref = path.stem
    title = ""
    progress: str | None = None

    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+(\S+)\s*-\s*(.+?)\s*$", line)
            if match:
                doc_ref = match.group(1).strip()
                title = match.group(2).strip()
            else:
                title = line.removeprefix("## ").strip()
            continue
        if line.startswith("> Progress:"):
            progress = line.split(":", 1)[1].strip()
    if not title:
        title = "(missing title)"
    return Entry(path=path, doc_ref=doc_ref, title=title, progress=progress)


def _collect(repo_root: Path, rel_dir: str) -> list[Entry]:
    directory = repo_root / rel_dir
    if not directory.is_dir():
        return []
    return [_parse_doc(p) for p in sorted(directory.glob("*.md"))]


def _render_section(title: str, entries: list[Entry], show_progress: bool) -> str:
    lines: list[str] = [f"## {title}", ""]
    if not entries:
        lines.append("_None_")
        lines.append("")
        return "\n".join(lines)

    header = "| Doc | Title |"
    sep = "|---|---|"
    if show_progress:
        header = "| Doc | Title | Progress |"
        sep = "|---|---|---|"
    lines.extend([header, sep])

    for entry in entries:
        rel = entry.path.as_posix()
        doc_link = f"[{entry.doc_ref}]({rel})"
        if show_progress:
            lines.append(f"| {doc_link} | {entry.title} | {entry.progress or ''} |")
        else:
            lines.append(f"| {doc_link} | {entry.title} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate logics/INDEX.md from Logics docs.")
    parser.add_argument("--out", default="logics/INDEX.md")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    requests = _collect(repo_root, "logics/request")
    backlog = _collect(repo_root, "logics/backlog")
    tasks = _collect(repo_root, "logics/tasks")

    content = "\n".join(
        [
            "# Logics Index",
            "",
            _render_section("Requests", requests, False),
            _render_section("Backlog", backlog, True),
            _render_section("Tasks", tasks, True),
        ]
    ).rstrip() + "\n"

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
