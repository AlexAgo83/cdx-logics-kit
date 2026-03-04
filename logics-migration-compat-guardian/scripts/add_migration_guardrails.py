#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SECTION_HEADING = "# Migration & compatibility"


def _find_heading_index(lines: list[str], heading: str) -> int | None:
    target = heading.strip().lower()
    for i, line in enumerate(lines):
        if line.strip().lower() == target:
            return i
    return None


def _insert_before(lines: list[str], heading: str, block: list[str]) -> list[str]:
    index = _find_heading_index(lines, heading)
    if index is None:
        return lines + [""] + block
    return lines[:index] + [""] + block + [""] + lines[index:]


def _apply(path: Path) -> bool:
    original = path.read_text(encoding="utf-8").splitlines()
    if _find_heading_index(original, SECTION_HEADING) is not None:
        return False

    block = [
        SECTION_HEADING,
        "- Data contract change:",
        "- Backward compatibility strategy:",
        "- Migration strategy:",
        "  - [ ] No migration required",
        "  - [ ] Version/schema bump required",
        "  - [ ] Backfill/transform required",
        "- Import/export impact (CSV/JSON):",
        "- Fixture and regression coverage:",
        "- Rollback for persisted data:",
    ]

    updated = original
    for anchor in ("# Validation", "# Risks & rollback", "# Report"):
        if _find_heading_index(updated, anchor) is not None:
            updated = _insert_before(updated, anchor, block)
            break
    else:
        updated = updated + [""] + block

    if updated == original:
        return False
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure a migration and compatibility guardrails section exists in Logics docs."
    )
    parser.add_argument("paths", nargs="+", help="Markdown files to update.")
    args = parser.parse_args(argv)

    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
        changed = _apply(path)
        print(("Updated " if changed else "No change ") + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
