#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


INDICATOR_ALIASES = {
    "from_version": "From version",
    "understanding": "Understanding",
    "confidence": "Confidence",
    "progress": "Progress",
    "complexity": "Complexity",
    "theme": "Theme",
    "date": "Date",
    "status": "Status",
    "drivers": "Drivers",
    "related_request": "Related request",
    "related_backlog": "Related backlog",
    "related_task": "Related task",
    "related_architecture": "Related architecture",
    "reminder": "Reminder",
}


def _set_indicator(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"> {key}:"
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*.*$")
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = f"{prefix} {value}"
            return lines

    insert_at = None
    for index, line in enumerate(lines):
        if line.startswith("## "):
            insert_at = index + 1
            break

    if insert_at is None:
        lines.insert(0, f"{prefix} {value}")
        return lines

    while insert_at < len(lines) and lines[insert_at].startswith("> "):
        insert_at += 1
    lines.insert(insert_at, f"{prefix} {value}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Update Logics indicator lines in a Markdown file.")
    parser.add_argument("path")
    parser.add_argument("--from-version")
    parser.add_argument("--understanding")
    parser.add_argument("--confidence")
    parser.add_argument("--progress")
    parser.add_argument("--complexity")
    parser.add_argument("--theme")
    parser.add_argument("--date")
    parser.add_argument("--status")
    parser.add_argument("--drivers")
    parser.add_argument("--related-request")
    parser.add_argument("--related-backlog")
    parser.add_argument("--related-task")
    parser.add_argument("--related-architecture")
    parser.add_argument("--reminder")
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    original = path.read_text(encoding="utf-8").splitlines()
    updated = original[:]

    for arg_name, indicator_name in INDICATOR_ALIASES.items():
        value = getattr(args, arg_name)
        if value is not None:
            updated = _set_indicator(updated, indicator_name, value)

    if updated == original:
        print("No changes.")
        return 0

    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
