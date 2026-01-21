#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _has_heading(lines: list[str], heading: str) -> bool:
    return any(line.strip() == heading for line in lines)


def _find_heading_index(lines: list[str], heading: str) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == heading:
            return i
    return None


def _insert_before(lines: list[str], heading: str, block: list[str]) -> list[str]:
    index = _find_heading_index(lines, heading)
    if index is None:
        return lines + [""] + block
    return lines[:index] + [""] + block + [""] + lines[index:]


def _apply(path: Path, owner: str | None) -> bool:
    original = path.read_text(encoding="utf-8").splitlines()
    updated = original[:]

    if _has_heading(updated, "# Ownership & metrics"):
        return False

    block = [
        "# Ownership & metrics",
        f"- Owner: {owner or ''}".rstrip(),
        "- KPI / success signal:",
        "- Instrumentation (events/logging):",
        "- Review date (optional):",
    ]

    # Prefer inserting before Notes or Open questions.
    if _find_heading_index(updated, "# Notes") is not None:
        updated = _insert_before(updated, "# Notes", block)
    elif _find_heading_index(updated, "# Open questions") is not None:
        updated = _insert_before(updated, "# Open questions", block)
    else:
        updated = updated + [""] + block

    if updated == original:
        return False
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Add an Ownership & metrics section to a Logics doc.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--owner")
    args = parser.parse_args(argv)

    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
        changed = _apply(path, owner=args.owner)
        print(("Updated " if changed else "No change ") + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

