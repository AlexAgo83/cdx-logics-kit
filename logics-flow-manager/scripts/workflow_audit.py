#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
}

STATUS_IN_PROGRESS = {"draft", "ready", "in progress", "blocked"}
STATUS_DONE = {"done", "archived"}


@dataclass
class DocMeta:
    kind: DocKind
    path: Path
    ref: str
    status: str | None
    progress: int | None
    from_version: tuple[int, int, int] | None
    text: str


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
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return {m.group(0) for m in pattern.finditer(text)}


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
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cutoff = _parse_semver(args.legacy_cutoff_version)
    if args.legacy_cutoff_version and cutoff is None:
        raise SystemExit(
            f"Invalid --legacy-cutoff-version `{args.legacy_cutoff_version}`. Expected semantic version like 1.3.0."
        )
    repo_root = _find_repo_root(Path.cwd())
    docs = _collect_docs(repo_root)

    issues: list[str] = []

    # 1) task done/100% while item/request closure is inconsistent.
    for doc in docs.values():
        if doc.kind.kind != "task":
            continue
        if not _is_done(doc):
            continue

        item_refs = _extract_refs(doc.text, DOC_KINDS["backlog"].prefix)
        if not item_refs:
            issues.append(f"{doc.path.relative_to(repo_root)}: done task has no linked backlog item reference")
            continue

        for item_ref in sorted(item_refs):
            item_doc = docs.get(item_ref)
            if item_doc is None or item_doc.kind.kind != "backlog":
                issues.append(
                    f"{doc.path.relative_to(repo_root)}: references missing backlog item `{item_ref}`"
                )
                continue
            if not _is_done(item_doc):
                issues.append(
                    f"{doc.path.relative_to(repo_root)}: done task linked to backlog item not closed `{item_ref}`"
                )

            for request_doc in _linked_requests_for_item(item_doc, docs):
                request_items = _linked_items_for_request(request_doc, docs)
                if request_items and all(_is_done(item) for item in request_items) and not _is_done(request_doc):
                    issues.append(
                        f"{request_doc.path.relative_to(repo_root)}: all backlog items are done but request is not closed"
                    )

    # 2) orphan backlog items (no request link).
    for doc in docs.values():
        if doc.kind.kind != "backlog":
            continue
        request_refs = _extract_refs(doc.text, DOC_KINDS["request"].prefix)
        if not request_refs:
            issues.append(f"{doc.path.relative_to(repo_root)}: orphan backlog item (no linked request)")

    # 3) delivered requests with incomplete backlog.
    for doc in docs.values():
        if doc.kind.kind != "request":
            continue
        if not _is_done(doc):
            continue
        request_items = _linked_items_for_request(doc, docs)
        if not request_items:
            issues.append(f"{doc.path.relative_to(repo_root)}: delivered request has no linked backlog items")
            continue
        for item in request_items:
            if not _is_done(item):
                issues.append(
                    f"{doc.path.relative_to(repo_root)}: delivered request linked to incomplete backlog item `{item.ref}`"
                )

    # 4) stale pending docs.
    if args.stale_days > 0:
        for doc in docs.values():
            if doc.status not in STATUS_IN_PROGRESS:
                continue
            age_days = _last_modified_age_days(doc.path)
            if age_days >= args.stale_days:
                issues.append(
                    f"{doc.path.relative_to(repo_root)}: stale pending doc ({age_days:.1f} days, status={doc.status})"
                )

    # 5) AC traceability mapping with proof (request AC -> item/task).
    if not args.skip_ac_traceability:
        for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
            if not _is_strict_scope(request, cutoff):
                continue
            ac_ids = _extract_request_ac_ids(request)
            if not ac_ids:
                continue

            linked_items = _linked_items_for_request(request, docs)
            if not linked_items:
                issues.append(f"{request.path.relative_to(repo_root)}: request has ACs but no linked backlog items")
                continue

            linked_tasks: list[DocMeta] = []
            for item in linked_items:
                linked_tasks.extend(_linked_tasks_for_item(item, docs))

            if not linked_tasks:
                issues.append(f"{request.path.relative_to(repo_root)}: request has ACs but no linked tasks")
                continue

            for ac_id in ac_ids:
                item_has_mapping = any(
                    (ac_id in item.text.upper()) and ("proof:" in item.text.lower())
                    for item in linked_items
                )
                if not item_has_mapping:
                    issues.append(
                        f"{request.path.relative_to(repo_root)}: `{ac_id}` missing item-level traceability with proof"
                    )

                task_has_mapping = any(
                    (ac_id in task.text.upper()) and ("proof:" in task.text.lower())
                    for task in linked_tasks
                )
                if not task_has_mapping:
                    issues.append(
                        f"{request.path.relative_to(repo_root)}: `{ac_id}` missing task-level traceability with proof"
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
                issues.append(f"{request.path.relative_to(repo_root)}: missing DoR checklist")
            elif any(not checked for checked, _label in dor_checks):
                issues.append(f"{request.path.relative_to(repo_root)}: DoR checklist contains unchecked items")

        for task in [doc for doc in docs.values() if doc.kind.kind == "task"]:
            if not _is_strict_scope(task, cutoff):
                continue
            if not _is_done(task):
                continue
            dod_checks = _extract_checkboxes(_extract_section_lines(task.text, "Definition of Done (DoD)"))
            if not dod_checks:
                issues.append(f"{task.path.relative_to(repo_root)}: missing DoD checklist")
            elif any(not checked for checked, _label in dod_checks):
                issues.append(f"{task.path.relative_to(repo_root)}: DoD checklist contains unchecked items")

    if not issues:
        print("Workflow audit: OK")
        return 0

    print("Workflow audit: FAILED")
    for issue in sorted(set(issues)):
        print(f"- {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
