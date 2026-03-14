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
    pattern = re.compile(r"^prod_(\d{3})_.*\.md$")
    max_id = -1
    for file_path in directory.glob("prod_*.md"):
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
    parser = argparse.ArgumentParser(description="Create a new product brief in logics/product.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out-dir", default="logics/product")
    parser.add_argument("--status", default="Proposed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    doc_id = _next_id(out_dir)
    slug = _slugify(args.title)
    filename = f"prod_{doc_id:03d}_{slug}.md"
    doc_ref = f"prod_{doc_id:03d}_{slug}"
    output_path = out_dir / filename

    template_path = repo_root / "logics/skills/logics-product-brief-writer/assets/templates/product_brief.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": args.title,
        "DATE": date.today().isoformat(),
        "STATUS": args.status,
        "REQUEST_REF": "`req_XXX_example`",
        "BACKLOG_REF": "`item_XXX_example`",
        "TASK_REF": "`task_XXX_example`",
        "ARCHITECTURE_REF": "`adr_XXX_example`",
        "OVERVIEW": "Summarize the product direction, the targeted user value, and the main expected outcomes.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Problem[User problem] --> Direction[Chosen product direction]\n"
            "    Direction --> Value[User value]\n"
            "    Direction --> Scope[Scoped experience]\n"
            "    Direction --> Outcome[Expected product outcomes]"
        ),
        "PROBLEM": "Describe the user or business problem this brief resolves.",
        "USER_1": "Primary user or segment",
        "GOAL_1": "Primary product goal",
        "NON_GOAL_1": "Explicit non-goal or excluded expectation",
        "IN_SCOPE_1": "Main capability or experience slice included",
        "OUT_OF_SCOPE_1": "Main capability explicitly excluded for now",
        "DECISION_1": "Key product trade-off or framing decision",
        "SUCCESS_SIGNAL_1": "Observable success signal or product metric",
        "QUESTION_1": "Main open product question to resolve",
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
