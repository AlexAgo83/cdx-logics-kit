#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from logics_flow_support import *  # noqa: F401,F403

def cmd_new(args: argparse.Namespace) -> None:
    doc_kind = DOC_KINDS[args.kind]
    repo_root = _find_repo_root(Path.cwd())
    planned = _reserve_doc(repo_root / doc_kind.directory, doc_kind.prefix, args.slug or args.title, args.dry_run)

    template_text = _template_path(Path(__file__), doc_kind.template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, args.title, doc_kind.include_progress)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(args.title))
    assessment = _assess_decision_framing(args.title, "")
    product_refs: list[str] = []
    architecture_refs: list[str] = []
    if doc_kind.kind in {"backlog", "task"}:
        product_refs, architecture_refs = _auto_create_companion_docs(
            repo_root,
            args.title,
            request_ref=None,
            backlog_ref=planned.ref if doc_kind.kind == "backlog" else None,
            task_ref=planned.ref if doc_kind.kind == "task" else None,
            assessment=assessment,
            product_refs=product_refs,
            architecture_refs=architecture_refs,
            args=args,
        )
        _apply_decision_assessment(values, assessment)
        if product_refs:
            values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
        if architecture_refs:
            values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _render_workflow_mermaid(doc_kind.kind, args.title, values)
    content = _render_template(template_text, values).rstrip() + "\n"
    _write(planned.path, content, args.dry_run)
    if doc_kind.kind in {"backlog", "task"}:
        _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)


def cmd_promote_request_to_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Promoted backlog item"
    repo_root = _find_repo_root(Path.cwd())
    _create_backlog_from_request(repo_root, source_path, title, args)


def cmd_promote_backlog_to_task(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Implementation task"
    repo_root = _find_repo_root(Path.cwd())
    _create_task_from_backlog(repo_root, source_path, title, args)


def cmd_split_request(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    titles = _split_titles(args.title)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_backlog_from_request(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split request into {len(created_refs)} backlog item(s): {', '.join(created_refs)}")


def cmd_split_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    titles = _split_titles(args.title)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_task_from_backlog(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split backlog item into {len(created_refs)} task(s): {', '.join(created_refs)}")


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


def _sync_close_eligible_requests(repo_root: Path, dry_run: bool) -> tuple[int, int]:
    request_dir = repo_root / DOC_KINDS["request"].directory
    closed = 0
    scanned = 0
    for request_path in sorted(request_dir.glob("req_*.md")):
        request_ref = request_path.stem
        scanned += 1
        if _is_doc_done(request_path, DOC_KINDS["request"]):
            continue
        linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
        if not linked_items:
            continue
        if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")
            closed += 1
    return scanned, closed


def cmd_sync_close_eligible_requests(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    scanned, closed = _sync_close_eligible_requests(repo_root, args.dry_run)
    print(f"Scanned {scanned} requests, auto-closed {closed}.")


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

    text = _strip_mermaid_blocks(source_path.read_text(encoding="utf-8"))
    processed_request_refs: set[str] = set()

    if kind.kind == "task":
        linked_item_refs = sorted(_extract_refs(text, REF_PREFIXES["backlog"]))
        for item_ref in linked_item_refs:
            item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
            if item_path is None:
                continue
            linked_tasks = _collect_docs_linking_ref(repo_root, DOC_KINDS["task"], item_ref)
            if linked_tasks and all(_is_doc_done(task_path, DOC_KINDS["task"]) for task_path in linked_tasks):
                if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
                    _close_doc(item_path, DOC_KINDS["backlog"], args.dry_run)
                    print(f"Auto-closed backlog item {item_ref} (all linked tasks are done).")

            item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
            for request_ref in sorted(_extract_refs(item_text, REF_PREFIXES["request"])):
                if request_ref in processed_request_refs:
                    continue
                processed_request_refs.add(request_ref)
                _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "backlog":
        for request_ref in sorted(_extract_refs(text, REF_PREFIXES["request"])):
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "request":
        request_ref = source_path.stem
        _maybe_close_request_chain(repo_root, request_ref, args.dry_run)


def _verify_finished_task_chain(repo_root: Path, task_path: Path) -> list[str]:
    issues: list[str] = []
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))

    if not item_refs:
        return [f"task `{task_ref}` has no linked backlog item reference"]

    processed_request_refs: set[str] = set()
    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            issues.append(f"task `{task_ref}` references missing backlog item `{item_ref}`")
            continue
        if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
            issues.append(f"linked backlog item `{item_ref}` is not closed after finishing task `{task_ref}`")

        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs = sorted(_extract_refs(item_text, REF_PREFIXES["request"]))
        if not request_refs:
            issues.append(f"linked backlog item `{item_ref}` has no request reference")
            continue

        for request_ref in request_refs:
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
            if request_path is None:
                issues.append(f"backlog item `{item_ref}` references missing request `{request_ref}`")
                continue

            linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
            if linked_items and all(_is_doc_done(linked_item, DOC_KINDS["backlog"]) for linked_item in linked_items):
                if not _is_doc_done(request_path, DOC_KINDS["request"]):
                    issues.append(
                        f"request `{request_ref}` should be closed because all linked backlog items are done"
                    )

    return issues


def _record_finished_task_follow_up(repo_root: Path, task_path: Path, dry_run: bool) -> None:
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))
    request_refs: set[str] = set()

    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            continue
        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs.update(_extract_refs(item_text, REF_PREFIXES["request"]))
        _append_section_bullets(
            item_path,
            "Notes",
            [f"- Task `{task_ref}` was finished via `logics_flow.py finish task` on {date.today().isoformat()}."],
            dry_run,
        )

    validation_bullets = [
        f"- Finish workflow executed on {date.today().isoformat()}.",
        "- Linked backlog/request close verification passed.",
    ]
    report_bullets = [
        f"- Finished on {date.today().isoformat()}.",
        f"- Linked backlog item(s): {', '.join(f'`{ref}`' for ref in item_refs) if item_refs else '(none)'}",
        f"- Related request(s): {', '.join(f'`{ref}`' for ref in sorted(request_refs)) if request_refs else '(none)'}",
    ]
    _append_section_bullets(task_path, "Validation", validation_bullets, dry_run)
    _append_section_bullets(task_path, "Report", report_bullets, dry_run)


def cmd_finish_task(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{DOC_KINDS['task'].prefix}_"):
        raise SystemExit(f"Expected a `{DOC_KINDS['task'].prefix}_...` task file. Got: {source_path.name}")

    close_args = argparse.Namespace(kind="task", source=args.source, dry_run=args.dry_run)
    cmd_close(close_args)
    _mark_section_checkboxes_done(source_path, "Definition of Done (DoD)", args.dry_run)
    _record_finished_task_follow_up(repo_root, source_path, args.dry_run)

    if args.dry_run:
        print("Dry run: skipped post-close verification.")
        return

    issues = _verify_finished_task_chain(repo_root, source_path)
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        raise SystemExit(f"Finish verification failed:\n{details}")

    print(f"Finish verification: OK for {source_path.relative_to(repo_root)}")


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
    if kind in {"backlog", "task"}:
        parser.add_argument("--auto-create-product-brief", action="store_true")
        parser.add_argument("--auto-create-adr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_flow.py",
        description="Create/promote/close/finish Logics docs with consistent IDs, templates, and workflow transitions.",
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

    split_parser = sub.add_parser("split", help="Split a request/backlog doc into multiple executable children.")
    split_sub = split_parser.add_subparsers(dest="split_kind", required=True)

    split_request = split_sub.add_parser("request", help="Split a request into multiple backlog items.")
    split_request.add_argument("source")
    split_request.add_argument("--title", action="append", required=True, help="Child backlog item title. Repeat the flag for multiple children.")
    _add_common_doc_args(split_request, "backlog")
    split_request.set_defaults(func=cmd_split_request)

    split_backlog = split_sub.add_parser("backlog", help="Split a backlog item into multiple tasks.")
    split_backlog.add_argument("source")
    split_backlog.add_argument("--title", action="append", required=True, help="Child task title. Repeat the flag for multiple children.")
    _add_common_doc_args(split_backlog, "task")
    split_backlog.set_defaults(func=cmd_split_backlog)

    close_parser = sub.add_parser("close", help="Close a request/backlog/task and propagate transitions.")
    close_sub = close_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        close_kind = close_sub.add_parser(kind, help=f"Close a {kind} doc.")
        close_kind.add_argument("source")
        close_kind.add_argument("--dry-run", action="store_true")
        close_kind.set_defaults(func=cmd_close)

    finish_parser = sub.add_parser(
        "finish",
        help="Finish a completed Logics doc using the recommended workflow guardrails.",
    )
    finish_sub = finish_parser.add_subparsers(dest="finish_kind", required=True)
    finish_task = finish_sub.add_parser(
        "task",
        help="Close a task, propagate task -> backlog -> request transitions, and verify the linked chain.",
    )
    finish_task.add_argument("source")
    finish_task.add_argument("--dry-run", action="store_true")
    finish_task.set_defaults(func=cmd_finish_task)

    sync_parser = sub.add_parser("sync", help="Sync workflow metadata and closure transitions.")
    sync_sub = sync_parser.add_subparsers(dest="sync_kind", required=True)
    close_eligible = sync_sub.add_parser(
        "close-eligible-requests",
        help="Auto-close requests when all linked backlog items are done.",
    )
    close_eligible.add_argument("--dry-run", action="store_true")
    close_eligible.set_defaults(func=cmd_sync_close_eligible_requests)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
