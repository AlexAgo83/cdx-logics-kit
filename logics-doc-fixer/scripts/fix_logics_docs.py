#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


INDICATOR_DEFAULTS = {
    "From version": "X.X.X",
    "Understanding": "??%",
    "Confidence": "??%",
    "Progress": "0%",
    "Date": "YYYY-MM-DD",
    "Status": "Proposed",
    "Drivers": "List the main architectural drivers.",
    "Related request": "(none yet)",
    "Related backlog": "(none yet)",
    "Related task": "(none yet)",
    "Related architecture": "(none yet)",
    "Reminder": "Update this doc when the framing changes.",
}

REQUEST_SECTIONS = [
    ("# Needs", ["- Describe the need"]),
    ("# Context", ["Add context and constraints."]),
    ("# Companion docs", ["- Product brief(s): (none yet)", "- Architecture decision(s): (none yet)"]),
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

PRODUCT_SECTIONS = [
    ("# Overview", ["Summarize the product direction."]),
    ("# Product problem", ["Describe the user or business problem this brief resolves."]),
    ("# Target users and situations", ["- Primary user or segment"]),
    ("# Goals", ["- Primary product goal"]),
    ("# Non-goals", ["- Explicit non-goal or excluded expectation"]),
    ("# Scope and guardrails", ["- In:", "- Out:"]),
    ("# Key product decisions", ["- Key product trade-off or framing decision"]),
    ("# Success signals", ["- Observable success signal or product metric"]),
    ("# References", ["- (none yet)"]),
    ("# Open questions", ["- Main open product question to resolve"]),
]

ARCHITECTURE_SECTIONS = [
    ("# Overview", ["Summarize the chosen direction and impacted areas."]),
    ("# Context", ["Describe the problem, constraints, and drivers."]),
    ("# Decision", ["State the chosen option and rationale."]),
    ("# Alternatives considered", ["- Alternative option"]),
    ("# Consequences", ["- Operational or product consequence"]),
    ("# Migration and rollout", ["- Describe the rollout or migration step."]),
    ("# References", ["- (none yet)"]),
    ("# Follow-up work", ["- List the backlog or task work enabled by this decision."]),
]

REQUIRED_INDICATORS = {
    "request": ["From version", "Understanding", "Confidence"],
    "backlog": ["From version", "Understanding", "Confidence", "Progress"],
    "task": ["From version", "Understanding", "Confidence", "Progress"],
    "product": [
        "Date",
        "Status",
        "Related request",
        "Related backlog",
        "Related task",
        "Related architecture",
        "Reminder",
    ],
    "architecture": [
        "Date",
        "Status",
        "Drivers",
        "Related request",
        "Related backlog",
        "Related task",
        "Reminder",
    ],
}


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
    if "/logics/product/" in path_str:
        return "product"
    if "/logics/architecture/" in path_str:
        return "architecture"
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


def _parse_indicators(lines: list[str]) -> tuple[list[str], dict[str, str]]:
    order: list[str] = []
    indicators: dict[str, str] = {}
    for line in lines:
        if not line.startswith("> "):
            continue
        match = re.match(r">\s*([^:]+):\s*(.+)$", line)
        if match:
            key = match.group(1).strip()
            if key not in indicators:
                order.append(key)
            indicators[key] = match.group(2).strip()
    return order, indicators


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

    existing_order, existing = _parse_indicators(lines[indicator_start:indicator_end])
    required = REQUIRED_INDICATORS[kind][:]

    if auto_progress and kind in {"backlog", "task"}:
        computed = _compute_progress(lines, kind)
        if computed and existing.get("Progress") != computed:
            existing["Progress"] = computed
            updated = True

    for key in required:
        if key not in existing:
            existing[key] = INDICATOR_DEFAULTS[key]
            if key not in existing_order:
                existing_order.append(key)
            updated = True

    # Preserve non-required indicators already present in docs (Status, Complexity, Theme, Reminder, etc.).
    # The fixer should only add missing required keys and update Progress when requested.
    new_indicators = [f"> {key}: {existing[key]}" for key in existing_order]
    content_start = indicator_end
    while content_start < len(lines) and lines[content_start].strip() == "":
        content_start += 1

    if lines[indicator_start:indicator_end] != new_indicators:
        updated = True

    new_lines = lines[: title_idx + 1] + new_indicators + [""] + lines[content_start:]
    return new_lines, updated


def _ensure_indicator_value(lines: list[str], key: str, value: str) -> tuple[list[str], bool]:
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

    existing_order, existing = _parse_indicators(lines[indicator_start:indicator_end])
    if existing.get(key) == value:
        return lines, False

    if key not in existing_order:
        existing_order.append(key)
    existing[key] = value
    new_indicators = [f"> {indicator}: {existing[indicator]}" for indicator in existing_order]
    content_start = indicator_end
    while content_start < len(lines) and lines[content_start].strip() == "":
        content_start += 1
    new_lines = lines[: title_idx + 1] + new_indicators + [""] + lines[content_start:]
    return new_lines, True


def _normalize_managed_ref(value: str) -> str | None:
    normalized = value.strip().strip("`").replace("\\", "/")
    normalized = re.sub(r"^\./", "", normalized)
    if not normalized or normalized.startswith("("):
        return None
    if "/" in normalized or normalized.endswith(".md"):
        return normalized
    if normalized.startswith("req_"):
        return f"logics/request/{normalized}.md"
    if normalized.startswith("item_"):
        return f"logics/backlog/{normalized}.md"
    if normalized.startswith("task_"):
        return f"logics/tasks/{normalized}.md"
    if normalized.startswith("prod_"):
        return f"logics/product/{normalized}.md"
    if normalized.startswith("adr_"):
        return f"logics/architecture/{normalized}.md"
    if normalized.startswith("spec_"):
        return f"logics/specs/{normalized}.md"
    return normalized


def _extract_indicator_backticked_refs(lines: list[str], keys: list[str]) -> list[str]:
    wanted = {key.lower() for key in keys}
    refs: list[str] = []
    for line in lines:
        if not line.startswith("> "):
            continue
        match = re.match(r">\s*([^:]+):\s*(.*)$", line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        if key not in wanted:
            continue
        refs.extend(re.findall(r"`([^`]+)`", match.group(2)))

    normalized = []
    for ref in refs:
        managed = _normalize_managed_ref(ref)
        if managed:
            normalized.append(managed)
    return list(dict.fromkeys(normalized))


def _ensure_reference_section(lines: list[str], refs: list[str]) -> tuple[list[str], bool]:
    start, end = _find_section_bounds(lines, "# References")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# References", *([f"- `{ref}`" for ref in refs] if refs else ["- (none yet)"])])
        return lines, True

    existing_section = lines[start:end]
    target_section = [f"- `{ref}`" for ref in refs] if refs else ["- (none yet)"]
    if existing_section == target_section:
        return lines, False
    return lines[:start] + target_section + lines[end:], True


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


def _ensure_request_companions(
    lines: list[str],
    heading: str,
    refs: list[Path],
) -> tuple[list[str], bool]:
    updated = False
    start, end = _find_section_bounds(lines, "# Companion docs")
    if start is None:
        return lines, False

    section_lines = lines[start:end]
    normalized_refs = [f"`{path.stem}`" for path in refs]
    target_line = f"- {heading}: {', '.join(normalized_refs) if normalized_refs else '(none yet)'}"

    found = False
    new_section: list[str] = []
    for line in section_lines:
        if line.startswith(f"- {heading}:"):
            new_section.append(target_line)
            found = True
            if line != target_line:
                updated = True
        else:
            new_section.append(line)

    if not found:
        new_section.append(target_line)
        updated = True

    if new_section != section_lines:
        updated = True
    lines = lines[:start] + new_section + lines[end:]
    return lines, updated


def _ensure_notes_reference(
    lines: list[str],
    reference_line: str,
) -> tuple[list[str], bool]:
    def normalize(value: str) -> str:
        return re.sub(r"[\\s.]+$", "", value.strip())

    updated = False
    start, end = _find_section_bounds(lines, "# Notes")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# Notes", reference_line])
        return lines, True

    canonical = normalize(reference_line)
    section_lines = lines[start:end]
    found = False
    new_section: list[str] = []
    for line in section_lines:
        if normalize(line) == canonical:
            if not found:
                new_section.append(reference_line)
                found = True
            else:
                updated = True
            continue
        new_section.append(line)

    if not found:
        new_section.append(reference_line)
        updated = True

    if new_section != section_lines:
        updated = True
    lines = lines[:start] + new_section + lines[end:]
    return lines, updated


def _ensure_task_context_reference(lines: list[str], reference_line: str) -> tuple[list[str], bool]:
    def normalize(value: str) -> str:
        return re.sub(r"[\\s.]+$", "", value.strip())

    updated = False
    start, end = _find_section_bounds(lines, "# Context")
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(["# Context", reference_line])
        return lines, True

    canonical = normalize(reference_line)
    section_lines = lines[start:end]
    found = False
    new_section: list[str] = []
    for line in section_lines:
        if normalize(line) == canonical:
            if not found:
                new_section.append(reference_line)
                found = True
            else:
                updated = True
            continue
        new_section.append(line)

    if not found:
        new_section.insert(0, reference_line)
        updated = True

    if new_section != section_lines:
        updated = True
    lines = lines[:start] + new_section + lines[end:]
    return lines, updated


def _collect_docs(repo_root: Path) -> list[DocRef]:
    docs: list[DocRef] = []
    for subdir in ("request", "backlog", "tasks", "product", "architecture"):
        for path in (repo_root / "logics" / subdir).glob("*.md"):
            doc_kind = "task" if subdir == "tasks" else subdir
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
    if kind == "task":
        return _ensure_sections(lines, TASK_SECTIONS)
    if kind == "product":
        return _ensure_sections(lines, PRODUCT_SECTIONS)
    return _ensure_sections(lines, ARCHITECTURE_SECTIONS)


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
        product_paths = slug_refs.get("product", [])
        architecture_paths = slug_refs.get("architecture", [])
        if len(product_paths) == 1:
            lines, updated = _ensure_request_companions(lines, "Product brief(s)", product_paths)
            changed = changed or updated
        if len(architecture_paths) == 1:
            lines, updated = _ensure_request_companions(lines, "Architecture decision(s)", architecture_paths)
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

    if doc.kind == "product":
        request_paths = slug_refs.get("request", [])
        backlog_paths = slug_refs.get("backlog", [])
        task_paths = slug_refs.get("task", [])
        architecture_paths = slug_refs.get("architecture", [])
        if len(request_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related request", f"`{request_paths[0].stem}`")
            changed = changed or updated
        if len(backlog_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related backlog", f"`{backlog_paths[0].stem}`")
            changed = changed or updated
        if len(task_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related task", f"`{task_paths[0].stem}`")
            changed = changed or updated
        if len(architecture_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related architecture", f"`{architecture_paths[0].stem}`")
            changed = changed or updated
        lines, updated = _ensure_reference_section(
            lines,
            _extract_indicator_backticked_refs(
                lines,
                ["Related request", "Related backlog", "Related task", "Related architecture"],
            ),
        )
        changed = changed or updated

    if doc.kind == "architecture":
        request_paths = slug_refs.get("request", [])
        backlog_paths = slug_refs.get("backlog", [])
        task_paths = slug_refs.get("task", [])
        if len(request_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related request", f"`{request_paths[0].stem}`")
            changed = changed or updated
        if len(backlog_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related backlog", f"`{backlog_paths[0].stem}`")
            changed = changed or updated
        if len(task_paths) == 1:
            lines, updated = _ensure_indicator_value(lines, "Related task", f"`{task_paths[0].stem}`")
            changed = changed or updated
        lines, updated = _ensure_reference_section(
            lines,
            _extract_indicator_backticked_refs(lines, ["Related request", "Related backlog", "Related task"]),
        )
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
        description="Validate and fix Logics request/backlog/task/product/architecture structure, indicators, and references.",
    )
    parser.add_argument("paths", nargs="*", help="Optional list of docs to check.")
    parser.add_argument("--repo-root", help="Repo root (defaults to auto-detect).")
    parser.add_argument("--write", action="store_true", help="Apply changes.")
    parser.add_argument("--no-progress", action="store_true", help="Do not auto-update Progress.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _find_repo_root(Path.cwd())
    all_docs = _collect_docs(repo_root)

    if args.paths:
        requested = {Path(path).resolve() for path in args.paths}
        docs = [doc for doc in all_docs if doc.path.resolve() in requested]
    else:
        docs = all_docs

    docs_by_slug: dict[str, dict[str, list[Path]]] = {}
    for doc in all_docs:
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
