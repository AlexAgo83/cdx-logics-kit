#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


INDICATOR_DEFAULTS = {
    "From version": "X.X.X",
    "Understanding": "??%",
    "Confidence": "??%",
    "Progress": "0%",
}

REQUEST_SECTIONS = [
    ("# Needs", ["- Describe the need"]),
    ("# Context", ["Add context and constraints."]),
    ("# Backlog", ["- (none yet)"]),
]

BACKLOG_SECTIONS = [
    ("# Problem", ["Describe the problem and user impact."]),
    ("# Scope", ["- In:", "- Out:"]),
    ("# Acceptance criteria", ["- Define acceptance criteria"]),
    ("# Priority", ["- Impact:", "- Urgency:"]),
    ("# Notes", []),
]

TASK_SECTIONS = [
    ("# Context", ["Derived from: <backlog item>"]),
    ("# Plan", ["- [ ] First implementation step", "- [ ] Second implementation step"]),
    ("# Validation", ["- npm run tests", "- npm run lint"]),
    ("# Report", ["- "]),
    ("# Notes", []),
]


@dataclass
class DocRef:
    path: Path
    kind: str
    slug: str


def _slug_from_path(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_", 2)
    if len(parts) >= 3:
        return parts[2]
    return stem


def _detect_kind(path: Path) -> str:
    path_str = path.as_posix()
    if "/logics/request/" in path_str:
        return "request"
    if "/logics/backlog/" in path_str:
        return "backlog"
    if "/logics/tasks/" in path_str:
        return "task"
    raise ValueError(f"Unknown doc kind for {path}")


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory).")


def _find_section_bounds(lines: list[str], header: str) -> tuple[int | None, int | None]:
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == header:
            start = idx + 1
            break
    if start is None:
        return None, None
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("# "):
            end = idx
            break
    return start, end


def _ensure_sections(lines: list[str], sections: list[tuple[str, list[str]]]) -> tuple[list[str], bool]:
    updated = False
    existing_headers = {line.strip() for line in lines if line.startswith("# ")}
    for header, body in sections:
        if header in existing_headers:
            continue
        updated = True
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(header)
        lines.extend(body)
    return lines, updated


def _count_checkboxes(lines: list[str], header: str) -> tuple[int, int]:
    start, end = _find_section_bounds(lines, header)
    if start is None:
        return 0, 0
    done = 0
    total = 0
    pattern = re.compile(r"^\s*- \[(x|X| )\]")
    for line in lines[start:end]:
        match = pattern.match(line)
        if not match:
            continue
        total += 1
        if match.group(1).lower() == "x":
            done += 1
    return done, total


def _compute_progress(lines: list[str], kind: str) -> str | None:
    headers = ["# Plan"] if kind == "task" else ["# Plan", "# Acceptance criteria"]
    for header in headers:
        done, total = _count_checkboxes(lines, header)
        if total:
            pct = int(round((done / total) * 100))
            return f"{pct}%"
    return None


def _parse_indicators(lines: list[str]) -> dict[str, str]:
    indicators: dict[str, str] = {}
    for line in lines:
        if not line.startswith("> "):
            continue
        match = re.match(r">\s*([^:]+):\s*(.+)$", line)
        if match:
            indicators[match.group(1).strip()] = match.group(2).strip()
    return indicators


def _ensure_indicators(lines: list[str], kind: str, auto_progress: bool) -> tuple[list[str], bool]:
    updated = False
    title_idx = None
    for idx, line in enumerate(lines):
        if line.startswith("## "):
            title_idx = idx
            break
    if title_idx is None:
        return lines, False

    indicator_start = title_idx + 1
    indicator_end = indicator_start
    while indicator_end < len(lines) and lines[indicator_end].startswith("> "):
        indicator_end += 1

    existing = _parse_indicators(lines[indicator_start:indicator_end])
    required = ["From version", "Understanding", "Confidence"]
    if kind in {"backlog", "task"}:
        required.append("Progress")

    if auto_progress and kind in {"backlog", "task"}:
        computed = _compute_progress(lines, kind)
        if computed:
            existing["Progress"] = computed

    for key in required:
        if key not in existing:
            existing[key] = INDICATOR_DEFAULTS[key]
            updated = True

    new_indicators = [f"> {key}: {existing[key]}" for key in required]
    content_start = indicator_end
    while content_start < len(lines) and lines[content_start].strip() == "":
        content_start += 1

    if lines[indicator_start:indicator_end] != new_indicators:
        updated = True

    new_lines = lines[: title_idx + 1] + new_indicators + [""] + lines[content_start:]
    return new_lines, updated


def _ensure_request_backlog(lines: list[str], backlog_paths: list[Path]) -> tuple[list[str], bool]:
    updated = False
    if not backlog_paths:
        return lines, False

    start, end = _find_section_bounds(lines, "# Backlog")
    backlog_lines = [f"- `{path.as_posix()}`" for path in backlog_paths]

    if start is None:
        updated = True
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# Backlog", *backlog_lines])
        return lines, updated

    existing = set(line.strip() for line in lines[start:end])
    for line in backlog_lines:
        if line not in existing:
            lines.insert(end, line)
            end += 1
            updated = True

    for idx in range(start, end):
        if "(none yet)" in lines[idx]:
            lines.pop(idx)
            updated = True
            break

    return lines, updated


def _ensure_notes_reference(
    lines: list[str],
    reference_line: str,
) -> tuple[list[str], bool]:
    updated = False
    start, end = _find_section_bounds(lines, "# Notes")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# Notes", reference_line])
        return lines, True

    if any(reference_line in line for line in lines[start:end]):
        return lines, False

    lines.insert(end, reference_line)
    updated = True
    return lines, updated


def _ensure_task_context_reference(lines: list[str], reference_line: str) -> tuple[list[str], bool]:
    updated = False
    start, end = _find_section_bounds(lines, "# Context")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# Context", reference_line])
        return lines, True

    if any(reference_line in line for line in lines[start:end]):
        return lines, False

    lines.insert(start, reference_line)
    updated = True
    return lines, updated


def _collect_docs(repo_root: Path) -> list[DocRef]:
    docs: list[DocRef] = []
    for kind, subdir in ("request", "backlog", "tasks"):
        for path in (repo_root / "logics" / subdir).glob("*.md"):
            doc_kind = "task" if kind == "tasks" else kind
            docs.append(DocRef(path=path, kind=doc_kind, slug=_slug_from_path(path)))
    return docs


def _ensure_structure(
    lines: list[str],
    kind: str,
) -> tuple[list[str], bool]:
    if kind == "request":
        return _ensure_sections(lines, REQUEST_SECTIONS)
    if kind == "backlog":
        return _ensure_sections(lines, BACKLOG_SECTIONS)
    return _ensure_sections(lines, TASK_SECTIONS)


def _process_doc(
    doc: DocRef,
    repo_root: Path,
    docs_by_slug: dict[str, dict[str, list[Path]]],
    auto_progress: bool,
) -> tuple[str, bool]:
    raw_lines = doc.path.read_text(encoding="utf-8").splitlines()
    lines = raw_lines[:]
    changed = False

    lines, updated = _ensure_indicators(lines, doc.kind, auto_progress)
    changed = changed or updated

    lines, updated = _ensure_structure(lines, doc.kind)
    changed = changed or updated

    slug_refs = docs_by_slug.get(doc.slug, {})

    if doc.kind == "request":
        backlog_paths = slug_refs.get("backlog", [])
        lines, updated = _ensure_request_backlog(lines, backlog_paths)
        changed = changed or updated

    if doc.kind == "backlog":
        request_paths = slug_refs.get("request", [])
        if len(request_paths) == 1:
            ref_line = f"- Derived from `{request_paths[0].as_posix()}`."
            lines, updated = _ensure_notes_reference(lines, ref_line)
            changed = changed or updated

    if doc.kind == "task":
        backlog_paths = slug_refs.get("backlog", [])
        if len(backlog_paths) == 1:
            ref_line = f"Derived from `{backlog_paths[0].as_posix()}`."
            lines, updated = _ensure_task_context_reference(lines, ref_line)
            changed = changed or updated

    final_text = "\n".join(lines).rstrip() + "\n"
    return final_text, changed


def _write(path: Path, content: str, write: bool) -> None:
    if write:
        path.write_text(content, encoding="utf-8")
    else:
        print(f"[dry-run] {path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and fix Logics request/backlog/task structure, indicators, and references.",
    )
    parser.add_argument("paths", nargs="*", help="Optional list of docs to check.")
    parser.add_argument("--repo-root", help="Repo root (defaults to auto-detect).")
    parser.add_argument("--write", action="store_true", help="Apply changes.")
    parser.add_argument("--no-progress", action="store_true", help="Do not auto-update Progress.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _find_repo_root(Path.cwd())
    docs = _collect_docs(repo_root)

    if args.paths:
        requested = {Path(path).resolve() for path in args.paths}
        docs = [doc for doc in docs if doc.path.resolve() in requested]

    docs_by_slug: dict[str, dict[str, list[Path]]] = {}
    for doc in docs:
        docs_by_slug.setdefault(doc.slug, {}).setdefault(doc.kind, []).append(
            doc.path.relative_to(repo_root)
        )

    changed_docs: list[Path] = []
    for doc in docs:
        updated_text, changed = _process_doc(
            doc,
            repo_root,
            docs_by_slug,
            auto_progress=not args.no_progress,
        )
        if changed:
            changed_docs.append(doc.path)
        _write(doc.path, updated_text, args.write)

    if not args.write and changed_docs:
        print("\nChanges detected (run with --write to apply):")
        for path in changed_docs:
            print(f"- {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
