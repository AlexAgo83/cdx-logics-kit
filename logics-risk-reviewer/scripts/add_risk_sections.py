#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _detect_kind(path: Path) -> str:
    name = path.name
    if name.startswith("item_") or "/backlog/" in path.as_posix():
        return "backlog"
    if name.startswith("task_") or "/tasks/" in path.as_posix():
        return "task"
    return "unknown"


def _has_heading(lines: list[str], heading: str) -> bool:
    return any(line.strip() == heading for line in lines)


def _find_heading_index(lines: list[str], heading: str) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == heading:
            return i
    return None


def _insert_after_section(lines: list[str], heading: str, block: list[str]) -> list[str]:
    index = _find_heading_index(lines, heading)
    if index is None:
        return lines + [""] + block

    insert_at = index + 1
    while insert_at < len(lines) and not lines[insert_at].startswith("# "):
        insert_at += 1
    return lines[:insert_at] + [""] + block + lines[insert_at:]


def _ensure_backlog_risks(lines: list[str]) -> list[str]:
    # Backlog convention: keep risks under Notes.
    if _has_heading(lines, "## Risks"):
        return lines

    risks_block = [
        "## Risks",
        "- Risk:",
        "  - Mitigation:",
        "  - Dependencies:",
    ]

    if _has_heading(lines, "# Notes"):
        return _insert_after_section(lines, "# Notes", risks_block)

    return lines + ["", "# Notes", ""] + risks_block


def _ensure_task_risks(lines: list[str]) -> list[str]:
    if _has_heading(lines, "# Risks & rollback"):
        return lines

    risks_block = [
        "# Risks & rollback",
        "- What can break:",
        "- How to detect regressions:",
        "- Rollback plan:",
    ]

    # Prefer inserting before Report if present.
    report_index = _find_heading_index(lines, "# Report")
    if report_index is not None:
        return lines[:report_index] + [""] + risks_block + [""] + lines[report_index:]

    return lines + [""] + risks_block


def _apply(path: Path) -> bool:
    original = path.read_text(encoding="utf-8").splitlines()
    updated = original[:]

    kind = _detect_kind(path)
    if kind == "backlog":
        updated = _ensure_backlog_risks(updated)
    elif kind == "task":
        updated = _ensure_task_risks(updated)
    else:
        return False

    if updated == original:
        return False
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Ensure Risks sections exist in Logics backlog/tasks docs.")
    parser.add_argument("paths", nargs="+", help="Markdown file paths (backlog/task).")
    args = parser.parse_args(argv)

    changed = 0
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
        if _apply(path):
            changed += 1
            print(f"Updated {path}")
        else:
            print(f"No change {path}")

    return 0 if changed >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

