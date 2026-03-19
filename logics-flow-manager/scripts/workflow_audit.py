#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DocKind:
    kind: str
    directory: str
    prefix: str
    has_progress: bool


DOC_KINDS = {
    "request": DocKind("request", "logics/request", "req", False),
    "backlog": DocKind("backlog", "logics/backlog", "item", True),
    "task": DocKind("task", "logics/tasks", "task", True),
    "product": DocKind("product", "logics/product", "prod", False),
    "architecture": DocKind("architecture", "logics/architecture", "adr", False),
}

REF_PREFIXES = ("req", "item", "task", "prod", "adr", "spec")

STATUS_IN_PROGRESS = {"draft", "ready", "in progress", "blocked"}
STATUS_DONE = {"done", "archived"}

COMPANION_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "product": (
        "Summarize the product direction, the targeted user value, and the main expected outcomes.",
        "Describe the user or business problem this brief resolves.",
        "Primary user or segment",
        "Primary product goal",
        "Main open product question to resolve",
    ),
    "architecture": (
        "Summarize the chosen direction, what changes, and the main impacted areas.",
        "Describe the problem, constraints, and drivers.",
        "State the chosen option and rationale.",
        "Describe the rollout or migration step.",
    ),
}


@dataclass
class DocMeta:
    kind: DocKind
    path: Path
    ref: str
    status: str | None
    progress: int | None
    from_version: tuple[int, int, int] | None
    text: str


@dataclass(frozen=True)
class AuditIssue:
    code: str
    path: Path | None
    message: str


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _indicator_value(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*(.+)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def _status_normalized(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()).lower()


def _progress_value(value: str | None) -> int | None:
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


def _parse_semver(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", value.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _extract_refs(text: str, prefix: str) -> set[str]:
    text = re.sub(r"```mermaid\s*\n.*?\n```", "", text, flags=re.DOTALL)
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return {m.group(0) for m in pattern.finditer(text)}


def _has_mermaid_block(text: str) -> bool:
    return "```mermaid" in text


def _decision_framing_value(text: str, label: str) -> str | None:
    pattern = re.compile(rf"^\s*-\s*{re.escape(label)}\s*:\s*(.+)\s*$", re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1).strip()


def _extract_section_lines(text: str, heading_title: str) -> list[str]:
    lines = text.splitlines()
    start_idx = None
    target = heading_title.strip().lower()
    for idx, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip().lower() == target:
            start_idx = idx + 1
            break
    if start_idx is None:
        return []

    section: list[str] = []
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if line.startswith("# "):
            break
        section.append(line)
    return section


def _extract_checkboxes(section_lines: Iterable[str]) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []
    pattern = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+)$")
    for line in section_lines:
        match = pattern.match(line)
        if match:
            out.append((match.group(1).lower() == "x", match.group(2).strip()))
    return out


def _extract_section_bounds(lines: list[str], heading_title: str) -> tuple[int, int] | None:
    start_idx = None
    target = heading_title.strip().lower()
    for idx, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip().lower() == target:
            start_idx = idx
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].startswith("# "):
            end_idx = idx
            break
    return start_idx, end_idx


def _extract_request_ac_ids(request: DocMeta) -> list[str]:
    section = _extract_section_lines(request.text, "Acceptance criteria")
    ids: set[str] = set()
    pattern = re.compile(r"\b(AC\d+[a-z]?)\b", re.IGNORECASE)
    for line in section:
        for match in pattern.finditer(line):
            ids.add(match.group(1).upper())
    return sorted(ids)


def _is_done(doc: DocMeta) -> bool:
    status = doc.status
    if status is not None and status in STATUS_DONE:
        return True
    if doc.kind.has_progress and doc.progress == 100:
        return True
    return False


def _collect_docs(repo_root: Path) -> dict[str, DocMeta]:
    docs: dict[str, DocMeta] = {}
    for kind in DOC_KINDS.values():
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            status = _status_normalized(_indicator_value(lines, "Status"))
            progress = _progress_value(_indicator_value(lines, "Progress"))
            from_version = _parse_semver(_indicator_value(lines, "From version"))
            docs[path.stem] = DocMeta(
                kind=kind,
                path=path,
                ref=path.stem,
                status=status,
                progress=progress,
                from_version=from_version,
                text=text,
            )
    return docs


def _scope_by_paths(docs: dict[str, DocMeta], repo_root: Path, raw_paths: list[str]) -> set[str]:
    included: set[str] = set()
    resolved_targets = [(repo_root / raw_path).resolve() for raw_path in raw_paths]
    for ref, doc in docs.items():
        doc_path = doc.path.resolve()
        for target in resolved_targets:
            if doc_path == target or target in doc_path.parents:
                included.add(ref)
                break
    return included


def _scope_by_refs(docs: dict[str, DocMeta], seed_refs: set[str]) -> set[str]:
    included: set[str] = set()
    queue = list(seed_refs)
    while queue:
        ref = queue.pop()
        if ref in included:
            continue
        doc = docs.get(ref)
        if doc is None:
            continue
        included.add(ref)

        linked_refs: set[str] = set()
        for prefix in REF_PREFIXES:
            linked_refs.update(_extract_refs(doc.text, prefix))
        for candidate in docs.values():
            if ref in candidate.text:
                linked_refs.add(candidate.ref)

        for linked_ref in linked_refs:
            if linked_ref not in included:
                queue.append(linked_ref)
    return included


def _apply_scope(
    docs: dict[str, DocMeta],
    repo_root: Path,
    scope_paths: list[str],
    scope_refs: list[str],
    scope_since_version: tuple[int, int, int] | None,
) -> dict[str, DocMeta]:
    allowed_refs = set(docs)

    if scope_paths:
        allowed_refs &= _scope_by_paths(docs, repo_root, scope_paths)
    if scope_refs:
        allowed_refs &= _scope_by_refs(docs, set(scope_refs))
    if scope_since_version is not None:
        allowed_refs &= {
            ref
            for ref, doc in docs.items()
            if doc.from_version is not None and doc.from_version >= scope_since_version
        }

    return {ref: doc for ref, doc in docs.items() if ref in allowed_refs}


def _linked_items_for_request(request: DocMeta, docs: dict[str, DocMeta]) -> list[DocMeta]:
    refs = _extract_refs(request.text, DOC_KINDS["backlog"].prefix)
    return [docs[ref] for ref in sorted(refs) if ref in docs and docs[ref].kind.kind == "backlog"]


def _linked_tasks_for_item(item: DocMeta, docs: dict[str, DocMeta]) -> list[DocMeta]:
    linked: list[DocMeta] = []
    for doc in docs.values():
        if doc.kind.kind != "task":
            continue
        if item.ref in doc.text:
            linked.append(doc)
    return linked


def _linked_requests_for_item(item: DocMeta, docs: dict[str, DocMeta]) -> list[DocMeta]:
    refs = _extract_refs(item.text, DOC_KINDS["request"].prefix)
    return [docs[ref] for ref in sorted(refs) if ref in docs and docs[ref].kind.kind == "request"]


def _last_modified_age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400.0


def _is_strict_scope(doc: DocMeta, cutoff: tuple[int, int, int] | None) -> bool:
    if cutoff is None:
        return True
    if doc.from_version is None:
        return False
    return doc.from_version >= cutoff


def _has_ac_with_proof(text: str, ac_id: str) -> bool:
    return (ac_id in text.upper()) and ("proof:" in text.lower())


def _autofix_ac_traceability(path: Path, ac_ids: set[str]) -> bool:
    if not ac_ids:
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    section_bounds = _extract_section_bounds(lines, "AC Traceability")
    if section_bounds is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# AC Traceability")
        section_bounds = _extract_section_bounds(lines, "AC Traceability")
        if section_bounds is None:
            return False

    modified = False
    ac_pattern = re.compile(r"\b(AC\d+[a-z]?)\b", re.IGNORECASE)

    for ac_id in sorted(ac_ids):
        section_bounds = _extract_section_bounds(lines, "AC Traceability")
        if section_bounds is None:
            break
        start_idx, end_idx = section_bounds
        body_start = start_idx + 1

        handled = False
        for idx in range(body_start, end_idx):
            line = lines[idx]
            if ac_id not in line.upper():
                continue
            if "proof:" in line.lower():
                handled = True
                break
            lines[idx] = line.rstrip() + " Proof: TODO."
            modified = True
            handled = True
            break

        if handled:
            continue

        insert_at = end_idx
        while insert_at > body_start and not lines[insert_at - 1].strip():
            insert_at -= 1

        lines.insert(
            insert_at,
            f"- {ac_id} -> TODO: map this acceptance criterion to scope. Proof: TODO.",
        )
        modified = True

    if not modified:
        return False

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def _rel(repo_root: Path, path: Path | None) -> str:
    if path is None:
        return "(global)"
    return path.relative_to(repo_root).as_posix()


def _sorted_issues(issues: Iterable[AuditIssue], repo_root: Path) -> list[AuditIssue]:
    unique: dict[tuple[str, str, str], AuditIssue] = {}
    for issue in issues:
        key = (_rel(repo_root, issue.path), issue.code, issue.message)
        unique.setdefault(key, issue)
    return sorted(unique.values(), key=lambda i: (_rel(repo_root, i.path), i.code, i.message))


def _print_text_report(issues: list[AuditIssue], repo_root: Path, group_by_doc: bool) -> None:
    if not issues:
        print("Workflow audit: OK")
        return

    print("Workflow audit: FAILED")
    if not group_by_doc:
        for issue in issues:
            rel = _rel(repo_root, issue.path)
            if issue.path is None:
                print(f"- [{issue.code}] {issue.message}")
            else:
                print(f"- {rel}: [{issue.code}] {issue.message}")
        return

    grouped: dict[str, list[AuditIssue]] = {}
    for issue in issues:
        grouped.setdefault(_rel(repo_root, issue.path), []).append(issue)
    for rel_path in sorted(grouped):
        print(f"- {rel_path}")
        for issue in sorted(grouped[rel_path], key=lambda i: (i.code, i.message)):
            print(f"  - [{issue.code}] {issue.message}")


def _print_json_report(
    issues: list[AuditIssue],
    repo_root: Path,
    autofix_enabled: bool,
    autofix_modified: list[Path],
) -> None:
    by_code: dict[str, int] = {}
    by_path: dict[str, int] = {}
    serialized: list[dict[str, str]] = []

    for issue in issues:
        rel_path = _rel(repo_root, issue.path)
        by_code[issue.code] = by_code.get(issue.code, 0) + 1
        by_path[rel_path] = by_path.get(rel_path, 0) + 1
        serialized.append(
            {
                "code": issue.code,
                "path": rel_path,
                "message": issue.message,
            }
        )

    payload = {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": serialized,
        "counts": {
            "by_code": dict(sorted(by_code.items())),
            "by_path": dict(sorted(by_path.items())),
        },
        "autofix": {
            "enabled": autofix_enabled,
            "modified_files": [_rel(repo_root, path) for path in sorted(autofix_modified)],
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflow_audit.py",
        description="Audit request/backlog/task workflow consistency and traceability.",
    )
    parser.add_argument("--stale-days", type=int, default=45, help="Threshold for stale pending docs.")
    parser.add_argument(
        "--skip-ac-traceability",
        action="store_true",
        help="Skip AC mapping/proof checks between request/backlog/task.",
    )
    parser.add_argument(
        "--skip-gates",
        action="store_true",
        help="Skip DoR/DoD gate checks.",
    )
    parser.add_argument(
        "--legacy-cutoff-version",
        help=(
            "Only enforce AC traceability and DoR/DoD gates for docs with "
            "`From version` >= this semantic version (example: 1.3.0)."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for audit results.",
    )
    parser.add_argument(
        "--group-by-doc",
        action="store_true",
        help="Group text output by document path.",
    )
    parser.add_argument(
        "--autofix-ac-traceability",
        action="store_true",
        help="Auto-add missing AC traceability skeleton entries in linked backlog/tasks docs.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Limit the audit to docs under these relative paths.",
    )
    parser.add_argument(
        "--refs",
        nargs="*",
        default=[],
        help="Limit the audit to these refs and their directly linked workflow neighborhood.",
    )
    parser.add_argument(
        "--since-version",
        help="Limit the audit to docs with `From version` >= this semantic version.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cutoff = _parse_semver(args.legacy_cutoff_version)
    if args.legacy_cutoff_version and cutoff is None:
        raise SystemExit(
            f"Invalid --legacy-cutoff-version `{args.legacy_cutoff_version}`. Expected semantic version like 1.3.0."
        )
    scope_since = _parse_semver(args.since_version)
    if args.since_version and scope_since is None:
        raise SystemExit(
            f"Invalid --since-version `{args.since_version}`. Expected semantic version like 1.3.0."
        )
    repo_root = _find_repo_root(Path.cwd())
    all_docs = _collect_docs(repo_root)
    docs = _apply_scope(all_docs, repo_root, args.paths, args.refs, scope_since)

    issues: list[AuditIssue] = []
    autofix_targets: dict[Path, set[str]] = {}
    autofix_modified: list[Path] = []

    # 1) task done/100% while item/request closure is inconsistent.
    for doc in docs.values():
        if doc.kind.kind != "task":
            continue
        if not _is_done(doc):
            continue

        item_refs = _extract_refs(doc.text, DOC_KINDS["backlog"].prefix)
        if not item_refs:
            issues.append(
                AuditIssue(
                    code="task_missing_backlog_ref",
                    path=doc.path,
                    message="done task has no linked backlog item reference",
                )
            )
            continue

        for item_ref in sorted(item_refs):
            item_doc = all_docs.get(item_ref)
            if item_doc is None or item_doc.kind.kind != "backlog":
                issues.append(
                    AuditIssue(
                        code="task_refs_missing_backlog",
                        path=doc.path,
                        message=f"references missing backlog item `{item_ref}`",
                    )
                )
                continue
            if not _is_done(item_doc):
                issues.append(
                    AuditIssue(
                        code="task_links_open_backlog",
                        path=doc.path,
                        message=f"done task linked to backlog item not closed `{item_ref}`",
                    )
                )

            for request_doc in _linked_requests_for_item(item_doc, all_docs):
                request_items = _linked_items_for_request(request_doc, all_docs)
                if request_items and all(_is_done(item) for item in request_items) and not _is_done(request_doc):
                    issues.append(
                        AuditIssue(
                            code="request_not_closed_after_backlog_done",
                            path=request_doc.path,
                            message="all backlog items are done but request is not closed",
                        )
                    )

    # 2) orphan backlog items (no request link).
    for doc in docs.values():
        if doc.kind.kind != "backlog":
            continue
        request_refs = _extract_refs(doc.text, DOC_KINDS["request"].prefix)
        if not request_refs:
            issues.append(
                AuditIssue(
                    code="backlog_orphan_no_request",
                    path=doc.path,
                    message="orphan backlog item (no linked request)",
                )
            )

    # 2b) required product/architecture framing without linked companion docs.
    for doc in docs.values():
        if doc.kind.kind not in {"backlog", "task"}:
            continue
        product_framing = _decision_framing_value(doc.text, "Product framing")
        architecture_framing = _decision_framing_value(doc.text, "Architecture framing")
        product_refs = _extract_refs(doc.text, "prod")
        architecture_refs = _extract_refs(doc.text, "adr")
        if product_framing == "Required" and not product_refs:
            issues.append(
                AuditIssue(
                    code="product_brief_required_missing_ref",
                    path=doc.path,
                    message="product framing is required but no linked product brief was found",
                )
            )
        if architecture_framing == "Required" and not architecture_refs:
            issues.append(
                AuditIssue(
                    code="architecture_decision_required_missing_ref",
                    path=doc.path,
                    message="architecture framing is required but no linked ADR was found",
                )
            )

    # 2c) companion docs must be connected and maintained.
    for doc in docs.values():
        if doc.kind.kind not in {"product", "architecture"}:
            continue
        linked_refs = set()
        for prefix in ("req", "item", "task", "prod", "adr"):
            linked_refs.update(_extract_refs(doc.text, prefix))

        if not any(ref.startswith(("req_", "item_", "task_")) for ref in linked_refs):
            issues.append(
                AuditIssue(
                    code="companion_doc_missing_primary_link",
                    path=doc.path,
                    message="companion doc has no linked request, backlog item, or task reference",
                )
            )

        if not _has_mermaid_block(doc.text):
            issues.append(
                AuditIssue(
                    code="companion_doc_missing_mermaid",
                    path=doc.path,
                    message="companion doc is missing its overview Mermaid diagram",
                )
            )

        placeholders = COMPANION_PLACEHOLDERS.get(doc.kind.kind, ())
        if any(snippet in doc.text for snippet in placeholders):
            issues.append(
                AuditIssue(
                    code="companion_doc_contains_placeholders",
                    path=doc.path,
                    message="companion doc still contains generator placeholder content",
                )
            )

        for ref in sorted(linked_refs):
            if ref == doc.ref:
                continue
            if ref not in all_docs:
                issues.append(
                    AuditIssue(
                        code="companion_doc_refs_missing_target",
                        path=doc.path,
                        message=f"companion doc references missing target `{ref}`",
                    )
                )

    # 3) delivered requests with incomplete backlog.
    for doc in docs.values():
        if doc.kind.kind != "request":
            continue
        if not _is_done(doc):
            continue
        request_items = _linked_items_for_request(doc, all_docs)
        if not request_items:
            issues.append(
                AuditIssue(
                    code="request_done_without_backlog",
                    path=doc.path,
                    message="delivered request has no linked backlog items",
                )
            )
            continue
        for item in request_items:
            if not _is_done(item):
                issues.append(
                    AuditIssue(
                        code="request_done_with_open_backlog",
                        path=doc.path,
                        message=f"delivered request linked to incomplete backlog item `{item.ref}`",
                    )
                )

    # 4) stale pending docs.
    if args.stale_days > 0:
        for doc in docs.values():
            if doc.status not in STATUS_IN_PROGRESS:
                continue
            age_days = _last_modified_age_days(doc.path)
            if age_days >= args.stale_days:
                issues.append(
                    AuditIssue(
                        code="stale_pending_doc",
                        path=doc.path,
                        message=f"stale pending doc ({age_days:.1f} days, status={doc.status})",
                    )
                )

    # 5) AC traceability mapping with proof (request AC -> item/task).
    if not args.skip_ac_traceability:
        for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
            if not _is_strict_scope(request, cutoff):
                continue
            ac_ids = _extract_request_ac_ids(request)
            if not ac_ids:
                continue

            linked_items = _linked_items_for_request(request, all_docs)
            if not linked_items:
                issues.append(
                    AuditIssue(
                        code="ac_no_linked_backlog",
                        path=request.path,
                        message="request has ACs but no linked backlog items",
                    )
                )
                continue

            linked_tasks: list[DocMeta] = []
            for item in linked_items:
                linked_tasks.extend(_linked_tasks_for_item(item, all_docs))

            if not linked_tasks:
                issues.append(
                    AuditIssue(
                        code="ac_no_linked_tasks",
                        path=request.path,
                        message="request has ACs but no linked tasks",
                    )
                )
                continue

            for ac_id in ac_ids:
                item_has_mapping = any(_has_ac_with_proof(item.text, ac_id) for item in linked_items)
                if not item_has_mapping:
                    if args.autofix_ac_traceability and linked_items:
                        autofix_targets.setdefault(linked_items[0].path, set()).add(ac_id)
                    else:
                        issues.append(
                            AuditIssue(
                                code="ac_missing_item_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing item-level traceability with proof",
                            )
                        )

                task_has_mapping = any(_has_ac_with_proof(task.text, ac_id) for task in linked_tasks)
                if not task_has_mapping:
                    if args.autofix_ac_traceability and linked_tasks:
                        autofix_targets.setdefault(linked_tasks[0].path, set()).add(ac_id)
                    else:
                        issues.append(
                            AuditIssue(
                                code="ac_missing_task_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing task-level traceability with proof",
                            )
                        )

    # 6) DoR/DoD gates.
    if not args.skip_gates:
        for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
            if not _is_strict_scope(request, cutoff):
                continue
            if request.status not in {"ready", "in progress", "done"}:
                continue
            dor_checks = _extract_checkboxes(_extract_section_lines(request.text, "Definition of Ready (DoR)"))
            if not dor_checks:
                issues.append(
                    AuditIssue(
                        code="request_missing_dor",
                        path=request.path,
                        message="missing DoR checklist",
                    )
                )
            elif any(not checked for checked, _label in dor_checks):
                issues.append(
                    AuditIssue(
                        code="request_dor_unchecked",
                        path=request.path,
                        message="DoR checklist contains unchecked items",
                    )
                )

        for task in [doc for doc in docs.values() if doc.kind.kind == "task"]:
            if not _is_strict_scope(task, cutoff):
                continue
            if not _is_done(task):
                continue
            dod_checks = _extract_checkboxes(_extract_section_lines(task.text, "Definition of Done (DoD)"))
            if not dod_checks:
                issues.append(
                    AuditIssue(
                        code="task_missing_dod",
                        path=task.path,
                        message="missing DoD checklist",
                    )
                )
            elif any(not checked for checked, _label in dod_checks):
                issues.append(
                    AuditIssue(
                        code="task_dod_unchecked",
                        path=task.path,
                        message="DoD checklist contains unchecked items",
                    )
                )

    if args.autofix_ac_traceability and autofix_targets:
        for path, ac_ids in sorted(autofix_targets.items(), key=lambda pair: pair[0].as_posix()):
            if _autofix_ac_traceability(path, ac_ids):
                autofix_modified.append(path)

        if autofix_modified:
            all_docs = _collect_docs(repo_root)
            docs = _apply_scope(all_docs, repo_root, args.paths, args.refs, scope_since)
            issues = [
                issue
                for issue in issues
                if issue.code not in {"ac_missing_item_traceability", "ac_missing_task_traceability"}
            ]

            for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
                if args.skip_ac_traceability:
                    break
                if not _is_strict_scope(request, cutoff):
                    continue
                ac_ids = _extract_request_ac_ids(request)
                if not ac_ids:
                    continue
                linked_items = _linked_items_for_request(request, all_docs)
                linked_tasks: list[DocMeta] = []
                for item in linked_items:
                    linked_tasks.extend(_linked_tasks_for_item(item, all_docs))
                for ac_id in ac_ids:
                    if linked_items and not any(_has_ac_with_proof(item.text, ac_id) for item in linked_items):
                        issues.append(
                            AuditIssue(
                                code="ac_missing_item_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing item-level traceability with proof",
                            )
                        )
                    if linked_tasks and not any(_has_ac_with_proof(task.text, ac_id) for task in linked_tasks):
                        issues.append(
                            AuditIssue(
                                code="ac_missing_task_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing task-level traceability with proof",
                            )
                        )

    sorted_issues = _sorted_issues(issues, repo_root)

    if args.format == "json":
        _print_json_report(sorted_issues, repo_root, args.autofix_ac_traceability, autofix_modified)
    else:
        _print_text_report(sorted_issues, repo_root, args.group_by_doc)

    return 0 if not sorted_issues else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
