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


def _apply(path: Path, size: str | None, points: str | None) -> bool:
    original = path.read_text(encoding="utf-8").splitlines()
    updated = original[:]

    if _has_heading(updated, "# Estimate"):
        return False

    size_value = size or ""
    points_value = points or ""

    block = ["# Estimate"]
    if size_value:
        block.append(f"- Size: {size_value}")
    if points_value:
        block.append(f"- Points: {points_value}")
    if not size_value and not points_value:
        block.append("- Size: S/M/L")
    block.extend(
        [
            "- Drivers:",
            "  - Unknowns:",
            "  - Integration points:",
            "  - Migration/rollback risk:",
        ]
    )

    # Prefer inserting before Priority or Notes when present.
    if _find_heading_index(updated, "# Priority") is not None:
        updated = _insert_before(updated, "# Priority", block)
    elif _find_heading_index(updated, "# Notes") is not None:
        updated = _insert_before(updated, "# Notes", block)
    else:
        updated = updated + [""] + block

    if updated == original:
        return False
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Add an Estimate section to a Logics backlog/task/spec doc.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--size", help="S/M/L (or your scale).")
    parser.add_argument("--points", help="Story points (optional).")
    args = parser.parse_args(argv)

    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
        changed = _apply(path, size=args.size, points=args.points)
        print(("Updated " if changed else "No change ") + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

