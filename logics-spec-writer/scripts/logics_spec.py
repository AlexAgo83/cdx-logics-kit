#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
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


def _next_id(directory: Path, prefix: str) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)_.*\.md$")
    max_id = -1
    for file_path in directory.glob(f"{prefix}_*.md"):
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


def cmd_new(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    specs_dir = repo_root / "logics/specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    doc_id = _next_id(specs_dir, "spec")
    slug = _slugify(args.slug or args.title)
    filename = f"spec_{doc_id:03d}_{slug}.md"
    doc_ref = f"spec_{doc_id:03d}_{slug}"
    output_path = specs_dir / filename

    template_path = repo_root / "logics/skills/logics-spec-writer/assets/templates/spec.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": args.title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "OVERVIEW": "Describe the user-facing behavior and context.",
        "GOAL_1": "Primary goal",
        "NON_GOAL_1": "Explicitly out of scope",
        "USE_CASE_1": "Key use case",
        "REQ_1": "Requirement",
        "AC_1": "Acceptance criterion",
        "TEST_1": "How to validate it",
        "QUESTION_1": "Open question",
    }
    content = _render_template(template_text, values).rstrip() + "\n"

    if args.dry_run:
        preview = content if len(content) <= 2000 else content[:2000] + "\n...\n"
        print(f"[dry-run] would write: {output_path}")
        print(preview)
        return

    output_path.write_text(content, encoding="utf-8")
    try:
        printable = output_path.relative_to(repo_root)
    except ValueError:
        printable = output_path
    print(f"Wrote {printable}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="logics_spec.py", description="Create spec docs in logics/specs.")
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new spec doc from a template.")
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--slug")
    new_parser.add_argument("--from-version", default="X.X.X")
    new_parser.add_argument("--understanding", default="??%")
    new_parser.add_argument("--confidence", default="??%")
    new_parser.add_argument("--dry-run", action="store_true")
    new_parser.set_defaults(func=cmd_new)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
