#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocKind:
    kind: str
    directory: str
    prefix: str
    template_name: str
    include_progress: bool


DOC_KINDS: dict[str, DocKind] = {
    "request": DocKind("request", "logics/request", "req", "request.md", False),
    "backlog": DocKind("backlog", "logics/backlog", "item", "backlog.md", True),
    "task": DocKind("task", "logics/tasks", "task", "task.md", True),
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


def _next_id(directory: Path, prefix: str) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)_.*\.md$")
    max_id = -1
    for file_path in directory.glob(f"{prefix}_*.md"):
        match = pattern.match(file_path.name)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
    return max_id + 1


def _template_path(script_path: Path, template_name: str) -> Path:
    return script_path.parent.parent / "assets" / "templates" / template_name


def _render_template(template_text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", repl, template_text)


def _parse_title_from_source(source_path: Path) -> str | None:
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
            return line.removeprefix("## ").strip()
    return None


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        preview = content if len(content) <= 2000 else content[:2000] + "\n...\n"
        print(f"[dry-run] would write: {path}")
        print(preview)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path}")


def cmd_new(args: argparse.Namespace) -> None:
    doc_kind = DOC_KINDS[args.kind]
    repo_root = _find_repo_root(Path.cwd())
    directory = repo_root / doc_kind.directory

    doc_id = _next_id(directory, doc_kind.prefix)
    slug = _slugify(args.slug or args.title)
    filename = f"{doc_kind.prefix}_{doc_id:03d}_{slug}.md"
    doc_ref = f"{doc_kind.prefix}_{doc_id:03d}_{slug}"
    output_path = directory / filename

    template_text = _template_path(Path(__file__), doc_kind.template_name).read_text(encoding="utf-8")
    values: dict[str, str] = {
        "DOC_REF": doc_ref,
        "TITLE": args.title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "NEEDS_PLACEHOLDER": "Describe the need",
        "CONTEXT_PLACEHOLDER": "Add context and constraints",
        "PROBLEM_PLACEHOLDER": "Describe the problem and user impact",
        "ACCEPTANCE_PLACEHOLDER": "Define an objective acceptance check",
        "NOTES_PLACEHOLDER": "",
        "STEP_1": "First implementation step",
        "STEP_2": "Second implementation step",
        "STEP_3": "Third implementation step",
        "VALIDATION_1": "npm run tests",
        "VALIDATION_2": "npm run lint",
        "REPORT_PLACEHOLDER": "",
    }

    if not doc_kind.include_progress:
        values["PROGRESS"] = ""

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)


def cmd_promote_request_to_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Promoted backlog item"
    repo_root = _find_repo_root(Path.cwd())
    directory = repo_root / DOC_KINDS["backlog"].directory

    doc_id = _next_id(directory, DOC_KINDS["backlog"].prefix)
    slug = _slugify(title)
    filename = f"item_{doc_id:03d}_{slug}.md"
    doc_ref = f"item_{doc_id:03d}_{slug}"
    output_path = directory / filename

    template_text = _template_path(Path(__file__), DOC_KINDS["backlog"].template_name).read_text(encoding="utf-8")
    values: dict[str, str] = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "PROBLEM_PLACEHOLDER": f"Promoted from `{source_path.relative_to(repo_root)}`",
        "ACCEPTANCE_PLACEHOLDER": "Define acceptance criteria",
        "NOTES_PLACEHOLDER": "",
    }

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)


def cmd_promote_backlog_to_task(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Implementation task"
    repo_root = _find_repo_root(Path.cwd())
    directory = repo_root / DOC_KINDS["task"].directory

    doc_id = _next_id(directory, DOC_KINDS["task"].prefix)
    slug = _slugify(title)
    filename = f"task_{doc_id:03d}_{slug}.md"
    doc_ref = f"task_{doc_id:03d}_{slug}"
    output_path = directory / filename

    template_text = _template_path(Path(__file__), DOC_KINDS["task"].template_name).read_text(encoding="utf-8")
    values: dict[str, str] = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "CONTEXT_PLACEHOLDER": f"Derived from `{source_path.relative_to(repo_root)}`",
        "STEP_1": "Clarify scope and acceptance criteria",
        "STEP_2": "Implement changes",
        "STEP_3": "Add/adjust tests and polish UX",
        "VALIDATION_1": "npm run tests",
        "VALIDATION_2": "npm run lint",
        "REPORT_PLACEHOLDER": "",
    }

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_flow.py",
        description="Create/promote Logics docs (request/backlog/task) with consistent IDs and templates.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new Logics doc from a template.")
    new_sub = new_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        kind_parser = new_sub.add_parser(kind, help=f"Create a new {kind} doc.")
        kind_parser.add_argument("--title", required=True)
        kind_parser.add_argument("--slug", help="Override slug derived from the title.")
        kind_parser.add_argument("--from-version", default="X.X.X")
        kind_parser.add_argument("--understanding", default="??%")
        kind_parser.add_argument("--confidence", default="??%")
        kind_parser.add_argument("--progress", default="0%")
        kind_parser.add_argument("--dry-run", action="store_true")
        kind_parser.set_defaults(func=cmd_new)

    promote_parser = sub.add_parser("promote", help="Promote between Logics stages.")
    promote_sub = promote_parser.add_subparsers(dest="promotion", required=True)

    r2b = promote_sub.add_parser("request-to-backlog", help="Create a backlog item from a request.")
    r2b.add_argument("source")
    r2b.add_argument("--from-version", default="X.X.X")
    r2b.add_argument("--understanding", default="??%")
    r2b.add_argument("--confidence", default="??%")
    r2b.add_argument("--progress", default="0%")
    r2b.add_argument("--dry-run", action="store_true")
    r2b.set_defaults(func=cmd_promote_request_to_backlog)

    b2t = promote_sub.add_parser("backlog-to-task", help="Create a task from a backlog item.")
    b2t.add_argument("source")
    b2t.add_argument("--from-version", default="X.X.X")
    b2t.add_argument("--understanding", default="??%")
    b2t.add_argument("--confidence", default="??%")
    b2t.add_argument("--progress", default="0%")
    b2t.add_argument("--dry-run", action="store_true")
    b2t.set_defaults(func=cmd_promote_backlog_to_task)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
