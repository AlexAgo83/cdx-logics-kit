#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "untitled"


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _next_id(directory: Path) -> int:
    pattern = re.compile(r"^adr_(\d{3})_.*\.md$")
    max_id = -1
    for file_path in directory.glob("adr_*.md"):
        match = pattern.match(file_path.name)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
    return max_id + 1


def _render_template(template_text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", repl, template_text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a new ADR in logics/architecture.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out-dir", default="logics/architecture")
    parser.add_argument("--status", default="Proposed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    doc_id = _next_id(out_dir)
    slug = _slugify(args.title)
    filename = f"adr_{doc_id:03d}_{slug}.md"
    doc_ref = f"adr_{doc_id:03d}_{slug}"
    output_path = out_dir / filename

    template_path = repo_root / "logics/skills/logics-architecture-decision-writer/assets/templates/adr.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": args.title,
        "DATE": date.today().isoformat(),
        "STATUS": args.status,
        "CONTEXT": "Describe the problem, constraints, and drivers.",
        "DECISION": "State the chosen option and rationale.",
        "ALT_1": "Alternative option",
        "CONSEQUENCE_1": "Operational/product consequence",
    }
    content = _render_template(template_text, values).rstrip() + "\n"

    if args.dry_run:
        preview = content if len(content) <= 2000 else content[:2000] + "\n...\n"
        print(f"[dry-run] would write: {output_path}")
        print(preview)
        return 0

    output_path.write_text(content, encoding="utf-8")
    try:
        printable = output_path.relative_to(repo_root)
    except ValueError:
        printable = output_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

