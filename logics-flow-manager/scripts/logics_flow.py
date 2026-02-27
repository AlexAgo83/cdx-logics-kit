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

ALLOWED_STATUSES = (
    "Draft",
    "Ready",
    "In progress",
    "Blocked",
    "Done",
    "Archived",
)

STATUS_BY_KIND_DEFAULT = {
    "request": "Draft",
    "backlog": "Ready",
    "task": "Ready",
}

ALLOWED_COMPLEXITIES = ("Low", "Medium", "High")


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


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _parse_indicator(lines: list[str], key: str) -> tuple[int | None, str | None]:
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*(.+)\s*$")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            return idx, match.group(1).strip()
    return None, None


def _upsert_indicators(path: Path, updates: dict[str, str], dry_run: bool) -> None:
    lines = _read_lines(path)
    heading_idx = next((idx for idx, line in enumerate(lines) if line.startswith("## ")), None)
    if heading_idx is None:
        raise SystemExit(f"Cannot update indicators (missing heading): {path}")

    insert_at = heading_idx + 1
    while insert_at < len(lines) and lines[insert_at].lstrip().startswith(">"):
        insert_at += 1

    for key, value in updates.items():
        indicator_idx, _ = _parse_indicator(lines, key)
        rendered = f"> {key}: {value}"
        if indicator_idx is None:
            lines.insert(insert_at, rendered)
            insert_at += 1
        else:
            lines[indicator_idx] = rendered

    _write(path, "\n".join(lines).rstrip() + "\n", dry_run)


def _normalize_status(value: str) -> str:
    normalized = " ".join(value.strip().split()).lower()
    for allowed in ALLOWED_STATUSES:
        if normalized == allowed.lower():
            return allowed
    allowed_display = ", ".join(ALLOWED_STATUSES)
    raise SystemExit(f"Invalid status '{value}'. Allowed values: {allowed_display}")


def _resolve_doc_path(repo_root: Path, kind: DocKind, doc_ref: str) -> Path | None:
    candidate = repo_root / kind.directory / f"{doc_ref}.md"
    if candidate.is_file():
        return candidate
    return None


def _extract_refs(text: str, kind: DocKind) -> set[str]:
    pattern = re.compile(rf"\b{re.escape(kind.prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return {match.group(0) for match in pattern.finditer(text)}


def _progress_value_to_int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"(\d{1,3})", value)
    if match is None:
        return None
    try:
        parsed = int(match.group(1))
    except ValueError:
        return None
    return max(0, min(100, parsed))


def _is_doc_done(path: Path, kind: DocKind) -> bool:
    lines = _read_lines(path)
    _, status_value = _parse_indicator(lines, "Status")
    if status_value is not None and _normalize_status(status_value) in {"Done", "Archived"}:
        return True
    if kind.include_progress:
        _, progress_value = _parse_indicator(lines, "Progress")
        return _progress_value_to_int(progress_value) == 100
    return False


def _collect_docs_linking_ref(repo_root: Path, kind: DocKind, ref: str) -> list[Path]:
    directory = repo_root / kind.directory
    linked: list[Path] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if ref in text:
            linked.append(path)
    return linked


def _close_doc(path: Path, kind: DocKind, dry_run: bool) -> None:
    updates = {"Status": "Done"}
    if kind.include_progress:
        updates["Progress"] = "100%"
    _upsert_indicators(path, updates, dry_run)


def _update_request_backlog_links(
    request_path: Path,
    backlog_ref: str,
    dry_run: bool,
) -> None:
    lines = request_path.read_text(encoding="utf-8").splitlines()
    backlog_line = f"- `{backlog_ref}`"

    section_start = None
    for idx, line in enumerate(lines):
        if line.strip() == "# Backlog":
            section_start = idx
            break

    if section_start is None:
        updated_lines = lines + ["", "# Backlog", backlog_line]
    else:
        section_end = len(lines)
        for idx in range(section_start + 1, len(lines)):
            if lines[idx].startswith("# "):
                section_end = idx
                break

        if any(backlog_ref in line for line in lines[section_start + 1 : section_end]):
            return

        section_body = [
            line
            for line in lines[section_start + 1 : section_end]
            if "(none yet)" not in line
        ]
        updated_lines = (
            lines[: section_start + 1]
            + section_body
            + [backlog_line]
            + lines[section_end:]
        )

    updated = "\n".join(updated_lines).rstrip() + "\n"
    _write(request_path, updated, dry_run)


def _build_template_values(args: argparse.Namespace, doc_ref: str, title: str, include_progress: bool) -> dict[str, str]:
    values: dict[str, str] = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "STATUS": _normalize_status(args.status),
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "COMPLEXITY": args.complexity,
        "THEME": args.theme,
        "NEEDS_PLACEHOLDER": "Describe the need",
        "CONTEXT_PLACEHOLDER": "Add context and constraints",
        "BACKLOG_PLACEHOLDER": "- (none yet)",
        "ACCEPTANCE_PLACEHOLDER": "AC1: Define an objective acceptance check",
        "PROBLEM_PLACEHOLDER": "Describe the problem and user impact",
        "NOTES_PLACEHOLDER": "",
        "STEP_1": "First implementation step",
        "STEP_2": "Second implementation step",
        "STEP_3": "Third implementation step",
        "VALIDATION_1": "npm run tests",
        "VALIDATION_2": "npm run lint",
        "REPORT_PLACEHOLDER": "",
    }

    if not include_progress:
        values["PROGRESS"] = ""

    return values


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
    values = _build_template_values(args, doc_ref, args.title, doc_kind.include_progress)

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
    values = _build_template_values(args, doc_ref, title, include_progress=True)
    values["NOTES_PLACEHOLDER"] = f"- Derived from `{source_path.relative_to(repo_root)}`."

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)
    _update_request_backlog_links(
        source_path,
        str(output_path.relative_to(repo_root)),
        args.dry_run,
    )


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
    values = _build_template_values(args, doc_ref, title, include_progress=True)
    values["CONTEXT_PLACEHOLDER"] = f"Derived from `{source_path.relative_to(repo_root)}`"
    values["STEP_1"] = "Clarify scope and acceptance criteria"
    values["STEP_2"] = "Implement changes"
    values["STEP_3"] = "Add/adjust tests and polish UX"

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)


def _maybe_close_request_chain(repo_root: Path, request_ref: str, dry_run: bool) -> None:
    request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
    if request_path is None:
        return

    linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
    if not linked_items:
        return

    if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
        if not _is_doc_done(request_path, DOC_KINDS["request"]):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")


def cmd_close(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    kind = DOC_KINDS[args.kind]
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{kind.prefix}_"):
        raise SystemExit(f"Expected a `{kind.prefix}_...` file for kind `{kind.kind}`. Got: {source_path.name}")

    _close_doc(source_path, kind, args.dry_run)
    print(f"Closed {kind.kind}: {source_path.relative_to(repo_root)}")

    text = source_path.read_text(encoding="utf-8")
    processed_request_refs: set[str] = set()

    if kind.kind == "task":
        linked_item_refs = sorted(_extract_refs(text, DOC_KINDS["backlog"]))
        for item_ref in linked_item_refs:
            item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
            if item_path is None:
                continue
            linked_tasks = _collect_docs_linking_ref(repo_root, DOC_KINDS["task"], item_ref)
            if linked_tasks and all(_is_doc_done(task_path, DOC_KINDS["task"]) for task_path in linked_tasks):
                if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
                    _close_doc(item_path, DOC_KINDS["backlog"], args.dry_run)
                    print(f"Auto-closed backlog item {item_ref} (all linked tasks are done).")

            item_text = item_path.read_text(encoding="utf-8")
            for request_ref in sorted(_extract_refs(item_text, DOC_KINDS["request"])):
                if request_ref in processed_request_refs:
                    continue
                processed_request_refs.add(request_ref)
                _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "backlog":
        for request_ref in sorted(_extract_refs(text, DOC_KINDS["request"])):
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            _maybe_close_request_chain(repo_root, request_ref, args.dry_run)


def _add_common_doc_args(parser: argparse.ArgumentParser, kind: str) -> None:
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--status", default=STATUS_BY_KIND_DEFAULT[kind])
    parser.add_argument("--complexity", default="Medium", choices=ALLOWED_COMPLEXITIES)
    parser.add_argument("--theme", default="General")
    if DOC_KINDS[kind].include_progress:
        parser.add_argument("--progress", default="0%")
    else:
        parser.add_argument("--progress", default="")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_flow.py",
        description="Create/promote/close Logics docs with consistent IDs, templates, and workflow transitions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new Logics doc from a template.")
    new_sub = new_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        kind_parser = new_sub.add_parser(kind, help=f"Create a new {kind} doc.")
        kind_parser.add_argument("--title", required=True)
        kind_parser.add_argument("--slug", help="Override slug derived from the title.")
        _add_common_doc_args(kind_parser, kind)
        kind_parser.set_defaults(func=cmd_new)

    promote_parser = sub.add_parser("promote", help="Promote between Logics stages.")
    promote_sub = promote_parser.add_subparsers(dest="promotion", required=True)

    r2b = promote_sub.add_parser("request-to-backlog", help="Create a backlog item from a request.")
    r2b.add_argument("source")
    _add_common_doc_args(r2b, "backlog")
    r2b.set_defaults(func=cmd_promote_request_to_backlog)

    b2t = promote_sub.add_parser("backlog-to-task", help="Create a task from a backlog item.")
    b2t.add_argument("source")
    _add_common_doc_args(b2t, "task")
    b2t.set_defaults(func=cmd_promote_backlog_to_task)

    close_parser = sub.add_parser("close", help="Close a request/backlog/task and propagate transitions.")
    close_sub = close_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        close_kind = close_sub.add_parser(kind, help=f"Close a {kind} doc.")
        close_kind.add_argument("source")
        close_kind.add_argument("--dry-run", action="store_true")
        close_kind.set_defaults(func=cmd_close)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
