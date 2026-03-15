#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

MANAGED_DIRS = {
    "req_": "logics/request",
    "item_": "logics/backlog",
    "task_": "logics/tasks",
    "prod_": "logics/product",
    "adr_": "logics/architecture",
    "spec_": "logics/specs",
}


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


def _normalize_ref(value: str) -> str:
    normalized = value.strip().strip("`").replace("\\", "/")
    normalized = re.sub(r"^\./", "", normalized)
    if not normalized:
        return normalized
    if "/" in normalized or normalized.endswith(".md"):
        return normalized
    for prefix, directory in MANAGED_DIRS.items():
        if normalized.startswith(prefix):
            return f"{directory}/{normalized}.md"
    return normalized


def _indicator_value(refs: list[str]) -> str:
    if not refs:
        return "(none yet)"
    ids = [Path(ref).stem for ref in refs]
    return ", ".join(f"`{ref_id}`" for ref_id in ids)


def _references_block(*groups: list[str]) -> str:
    refs: list[str] = []
    for group in groups:
        refs.extend(group)
    deduped = list(dict.fromkeys(refs))
    if not deduped:
        return "- (none yet)"
    return "\n".join(f"- `{ref}`" for ref in deduped)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a new ADR in logics/architecture.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out-dir", default="logics/architecture")
    parser.add_argument("--status", default="Proposed")
    parser.add_argument("--request", action="append", default=[])
    parser.add_argument("--backlog", action="append", default=[])
    parser.add_argument("--task", action="append", default=[])
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
    request_refs = [_normalize_ref(value) for value in args.request if _normalize_ref(value)]
    backlog_refs = [_normalize_ref(value) for value in args.backlog if _normalize_ref(value)]
    task_refs = [_normalize_ref(value) for value in args.task if _normalize_ref(value)]

    template_path = repo_root / "logics/skills/logics-architecture-decision-writer/assets/templates/adr.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": args.title,
        "DATE": date.today().isoformat(),
        "STATUS": args.status,
        "DRIVERS": "List the main architectural drivers.",
        "REQUEST_REF": _indicator_value(request_refs),
        "BACKLOG_REF": _indicator_value(backlog_refs),
        "TASK_REF": _indicator_value(task_refs),
        "OVERVIEW": "Summarize the chosen direction, what changes, and the main impacted areas.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Current[Current architecture] --> Decision[Chosen direction]\n"
            "    Decision --> App[Application layer]\n"
            "    Decision --> Data[Data and contracts]\n"
            "    Decision --> Ops[Deployment and observability]\n"
            "    Decision --> Team[Delivery and maintenance]"
        ),
        "CONTEXT": "Describe the problem, constraints, and drivers.",
        "DECISION": "State the chosen option and rationale.",
        "ALT_1": "Alternative option",
        "CONSEQUENCE_1": "Operational/product consequence",
        "MIGRATION_1": "Describe the rollout or migration step.",
        "REFERENCES": _references_block(request_refs, backlog_refs, task_refs),
        "FOLLOW_UP_1": "List the backlog or task work enabled by this decision.",
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
