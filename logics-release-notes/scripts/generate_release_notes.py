#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Task:
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


def _parse_task(path: Path) -> Task:
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
        if line.startswith("> Progress:"):
            progress = line.split(":", 1)[1].strip()
    if not title:
        title = "(missing title)"
    return Task(path=path, doc_ref=doc_ref, title=title, progress=progress)


def _is_done(progress: str | None) -> bool:
    if progress is None:
        return False
    return progress.strip() in {"100%", "100"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate release notes from completed Logics tasks.")
    parser.add_argument("--out", default="logics/RELEASE_NOTES.md")
    parser.add_argument("--title", default=f"Release notes ({date.today().isoformat()})")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    tasks_dir = repo_root / "logics/tasks"
    tasks = [_parse_task(p) for p in sorted(tasks_dir.glob("*.md"))]
    done = [t for t in tasks if _is_done(t.progress)]

    lines: list[str] = [f"# {args.title}", ""]
    if not done:
        lines.append("_No completed tasks (Progress 100%) found._")
        lines.append("")
    else:
        lines.append("## Completed")
        lines.append("")
        for task in done:
            rel = task.path.relative_to(repo_root).as_posix()
            lines.append(f"- [{task.doc_ref}]({rel}) - {task.title}")
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
