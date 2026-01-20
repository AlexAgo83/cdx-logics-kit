#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BacklogItem:
    path: Path
    ref: str
    title: str
    progress: str | None
    impact: str | None
    urgency: str | None


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _parse_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
            return line.removeprefix("## ").strip()
    return fallback


def _parse_backlog(path: Path) -> BacklogItem:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = _parse_title(lines, fallback=path.stem)
    progress = None
    impact = None
    urgency = None
    for line in lines:
        if line.startswith("> Progress:"):
            progress = line.split(":", 1)[1].strip()
        if line.strip().lower().startswith("- impact:"):
            impact = line.split(":", 1)[1].strip().lower()
        if line.strip().lower().startswith("- urgency:"):
            urgency = line.split(":", 1)[1].strip().lower()
    return BacklogItem(path=path, ref=path.stem, title=title, progress=progress, impact=impact, urgency=urgency)


def _is_done(progress: str | None) -> bool:
    return progress is not None and progress.strip() in {"100%", "100"}


def _is_high(value: str | None) -> bool:
    return value in {"high", "h"}

def _is_low(value: str | None) -> bool:
    return value in {"low", "l"}


def _bucket(item: BacklogItem) -> str:
    if _is_done(item.progress):
        return "Done"
    if _is_high(item.impact) or _is_high(item.urgency):
        return "Now"
    if _is_low(item.impact) and _is_low(item.urgency):
        return "Later"
    return "Next"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a simple Logics roadmap from backlog items.")
    parser.add_argument("--out", default="logics/ROADMAP.md")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    backlog_dir = repo_root / "logics/backlog"
    items = [_parse_backlog(p) for p in sorted(backlog_dir.glob("*.md"))]

    buckets: dict[str, list[BacklogItem]] = {"Now": [], "Next": [], "Later": [], "Done": []}
    for item in items:
        buckets[_bucket(item)].append(item)

    lines: list[str] = ["# Roadmap", ""]
    lines.append("## Now")
    lines.append("")
    lines.extend(_render_items(repo_root, buckets["Now"]))
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.extend(_render_items(repo_root, buckets["Next"]))
    lines.append("")
    lines.append("## Later")
    lines.append("")
    lines.extend(_render_items(repo_root, buckets["Later"]))
    lines.append("")
    lines.append("## Done")
    lines.append("")
    lines.extend(_render_items(repo_root, buckets["Done"]))
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


def _render_items(repo_root: Path, items: list[BacklogItem]) -> list[str]:
    if not items:
        return ["_None_"]
    lines: list[str] = []
    for item in items:
        rel = item.path.relative_to(repo_root).as_posix()
        progress = f" ({item.progress})" if item.progress else ""
        lines.append(f"- [{item.ref}]({rel}) - {item.title}{progress}")
    return lines


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
