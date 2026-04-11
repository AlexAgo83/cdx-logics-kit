#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from logics_flow_decision_support import (
    DecisionAssessment,
    _apply_decision_assessment,
    _assess_decision_framing,
    _print_decision_summary,
    _render_architecture_decision,
    _render_product_brief,
    _signals_display,
)
from logics_flow_registry import CURRENT_WORKFLOW_SCHEMA_VERSION

MERMAID_GENERATOR_SCRIPTS = Path(__file__).resolve().parents[3] / "logics-mermaid-generator" / "scripts"
if str(MERMAID_GENERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MERMAID_GENERATOR_SCRIPTS))

from generate_mermaid import (  # noqa: E402
    generate_mermaid,
    _render_backlog_mermaid,
    _render_request_mermaid,
    _render_task_mermaid,
    _render_workflow_mermaid,
)


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

REF_PREFIXES = {
    "request": "req",
    "backlog": "item",
    "task": "task",
    "product": "prod",
    "architecture": "adr",
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
UI_STEERING_REF = "logics/skills/logics-ui-steering/SKILL.md"
FRONTEND_SIGNAL_PATTERN = re.compile(
    r"\b(front[\s-]?end|ui|interface|webview|react|vue|svelte|html|css|component|screen|layout)\b",
    re.IGNORECASE,
)
MERMAID_LABEL_MAX_WORDS = 6
MERMAID_LABEL_MAX_CHARS = 42
MERMAID_FALLBACKS = {
    "request_backlog": "Backlog slice",
    "backlog_task": "Execution task",
    "task_report": "Done report",
}
MERMAID_BLOCK_PATTERN = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
MERMAID_SIGNATURE_PATTERN = re.compile(r"^\s*%%\s*logics-signature:\s*(.+?)\s*$", re.MULTILINE)
AI_CONTEXT_FIELD_PATTERN = re.compile(r"^\s*-\s*([^:]+)\s*:\s*(.+?)\s*$")
AI_KEYWORD_STOPWORDS = {
    "about",
    "after",
    "before",
    "being",
    "between",
    "define",
    "deliver",
    "delivery",
    "focus",
    "from",
    "have",
    "into",
    "needs",
    "review",
    "scope",
    "should",
    "task",
    "that",
    "this",
    "through",
    "when",
    "with",
}
MARKDOWN_LINK_PATTERN = re.compile(r"^\[[^\]]+\]\(([^)]+)\)$")
REPO_PATH_STARTERS = (
    "logics/",
    "src/",
    "media/",
    "tests/",
    "scripts/",
    "debug/",
    "changelogs/",
    ".github/",
    ".vscode/",
    ".claude/",
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "package.json",
    "VERSION",
    ".gitattributes",
    ".vscodeignore",
)

@dataclass(frozen=True)
class PlannedDoc:
    ref: str
    path: Path



from logics_flow_support_workflow_core import *  # noqa: F401,F403

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


def _update_backlog_task_links(
    backlog_path: Path,
    task_refs: list[str],
    dry_run: bool,
) -> None:
    if not task_refs:
        return

    lines = backlog_path.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    replaced = False

    for line in lines:
        if line.startswith("- Primary task(s):"):
            refs = ", ".join(f"`{ref}`" for ref in task_refs)
            updated_lines.append(f"- Primary task(s): {refs}")
            replaced = True
        else:
            updated_lines.append(line)

    if not replaced:
        updated_lines.extend(["", "# Links", f"- Primary task(s): {', '.join(f'`{ref}`' for ref in task_refs)}"])

    updated = "\n".join(updated_lines).rstrip() + "\n"
    _write(backlog_path, updated, dry_run)


def _update_request_companion_links(
    request_path: Path,
    heading: str,
    ref: str,
    dry_run: bool,
) -> None:
    lines = request_path.read_text(encoding="utf-8").splitlines()
    target_line = f"- {heading}: `{ref}`"

    section_start = None
    for idx, line in enumerate(lines):
        if line.strip() == "# Companion docs":
            section_start = idx
            break

    if section_start is None:
        updated_lines = lines + ["", "# Companion docs", target_line]
    else:
        section_end = len(lines)
        for idx in range(section_start + 1, len(lines)):
            if lines[idx].startswith("# "):
                section_end = idx
                break

        existing = lines[section_start + 1 : section_end]
        updated_section = []
        found_heading = False
        found_ref = False
        for line in existing:
            if not line.strip():
                continue
            if line.startswith(f"- {heading}:"):
                found_heading = True
                refs = set(_extract_refs(line, REF_PREFIXES["product"])) | set(_extract_refs(line, REF_PREFIXES["architecture"]))
                refs.add(ref)
                ordered = ", ".join(f"`{value}`" for value in sorted(refs))
                updated_section.append(f"- {heading}: {ordered}")
                found_ref = True
            else:
                updated_section.append(line)
        if not found_heading:
            updated_section.append(target_line)
        elif found_ref:
            pass

        updated_lines = lines[: section_start + 1] + updated_section + lines[section_end:]

    updated = "\n".join(updated_lines).rstrip() + "\n"
    _write(request_path, updated, dry_run)


def _build_template_values(
    args: argparse.Namespace,
    doc_ref: str,
    title: str,
    include_progress: bool,
    doc_kind: str,
) -> dict[str, str]:
    values: dict[str, str] = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "SCHEMA_VERSION": CURRENT_WORKFLOW_SCHEMA_VERSION,
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
        "ACCEPTANCE_BLOCK": "- AC1: Define an objective acceptance check",
        "AC_TRACEABILITY_PLACEHOLDER": "- AC1 -> TODO: map this acceptance criterion to scope. Proof: TODO.",
        "PROBLEM_PLACEHOLDER": "Describe the problem and user impact",
        "NOTES_PLACEHOLDER": "",
        "REQUEST_LINK_PLACEHOLDER": "`req_XXX_example`",
        "PRODUCT_LINK_PLACEHOLDER": "(none yet)",
        "ARCHITECTURE_LINK_PLACEHOLDER": "(none yet)",
        "PRODUCT_FRAMING_STATUS": "Not needed",
        "PRODUCT_FRAMING_SIGNALS": "(none detected)",
        "PRODUCT_FRAMING_ACTION": "No product brief follow-up is expected based on current signals.",
        "ARCHITECTURE_FRAMING_STATUS": "Not needed",
        "ARCHITECTURE_FRAMING_SIGNALS": "(none detected)",
        "ARCHITECTURE_FRAMING_ACTION": "No architecture decision follow-up is expected based on current signals.",
        "BACKLOG_LINK_PLACEHOLDER": "`item_XXX_example`",
        "TASK_LINK_PLACEHOLDER": "`task_XXX_example`",
        "STEP_1": "First implementation step",
        "STEP_2": "Second implementation step",
        "STEP_3": "Third implementation step",
        "PLAN_BLOCK": _render_plan_block(
            [
                "Confirm scope, dependencies, and linked acceptance criteria.",
                "Implement the next coherent delivery wave.",
                "Checkpoint the wave in a commit-ready state, validate it, and update the linked Logics docs.",
            ]
        ),
        "VALIDATION_1": "Run the relevant automated tests for the changed surface before closing the current wave or step.",
        "VALIDATION_2": "Run the relevant lint or quality checks before closing the current wave or step.",
        "VALIDATION_BLOCK": _render_validation_block(
            [
                "Run the relevant automated tests for the changed surface before closing the current wave or step.",
                "Run the relevant lint or quality checks before closing the current wave or step.",
                "Confirm the completed wave leaves the repository in a commit-ready state.",
            ]
        ),
        "REPORT_PLACEHOLDER": "",
        "AI_SUMMARY_PLACEHOLDER": "",
        "AI_KEYWORDS_PLACEHOLDER": "",
        "AI_USE_WHEN_PLACEHOLDER": "",
        "AI_SKIP_WHEN_PLACEHOLDER": "",
        "REFERENCES_SECTION": "",
        "MERMAID_BLOCK": "",
    }
    _apply_ai_context_values(values, doc_kind=doc_kind, title=title, primary_items=[title])

    if not include_progress:
        values["PROGRESS"] = ""

    return values


def build_workflow_doc_values(
    kind_name: str,
    *,
    doc_ref: str,
    title: str,
    from_version: str = "0.0.0",
    status: str | None = None,
    understanding: str = "90%",
    confidence: str = "85%",
    progress: str = "0%",
    complexity: str = "Medium",
    theme: str = "General",
) -> dict[str, str]:
    kind = DOC_KINDS[kind_name]
    args = argparse.Namespace(
        from_version=from_version,
        understanding=understanding,
        confidence=confidence,
        status=status or STATUS_BY_KIND_DEFAULT[kind_name],
        progress=progress if kind.include_progress else "",
        complexity=complexity,
        theme=theme,
        auto_create_product_brief=False,
        auto_create_adr=False,
        dry_run=False,
    )
    return _build_template_values(args, doc_ref, title, kind.include_progress, kind_name)


def plan_workflow_doc(repo_root: Path, kind_name: str, title: str, dry_run: bool = False) -> PlannedDoc:
    kind = DOC_KINDS[kind_name]
    return _plan_doc(repo_root, kind.directory, kind.prefix, title, dry_run=dry_run)


def find_repo_root(start: Path) -> Path:
    return _find_repo_root(start)


def render_workflow_template(kind_name: str, values: dict[str, str]) -> str:
    kind = DOC_KINDS[kind_name]
    template_text = _template_path(Path(__file__), kind.template_name).read_text(encoding="utf-8")
    return _render_template(template_text, values).rstrip() + "\n"


def write_workflow_doc(path: Path, content: str, dry_run: bool) -> None:
    _write(path, content, dry_run)


def _ai_context_inputs_for_kind(kind_name: str, text: str) -> tuple[list[str], list[str]]:
    if kind_name == "request":
        return (_list_items_from_section(text, "Needs") + _acceptance_items(text), _clean_section_lines(_section_lines(text, "Context")))
    if kind_name == "backlog":
        return (_list_items_from_section(text, "Problem") + _acceptance_items(text), _clean_section_lines(_section_lines(text, "Notes")))
    if kind_name == "task":
        return (_clean_section_lines(_section_lines(text, "Context")) + _clean_section_lines(_section_lines(text, "Validation")), _clean_section_lines(_section_lines(text, "Plan")))
    return ([], [])


def _render_ai_context_section(values: dict[str, str]) -> list[str]:
    return [
        "# AI Context",
        f"- Summary: {values['AI_SUMMARY_PLACEHOLDER']}",
        f"- Keywords: {values['AI_KEYWORDS_PLACEHOLDER']}",
        f"- Use when: {values['AI_USE_WHEN_PLACEHOLDER']}",
        f"- Skip when: {values['AI_SKIP_WHEN_PLACEHOLDER']}",
    ]


def _section_bounds(lines: list[str], heading: str) -> tuple[int | None, int | None]:
    start_idx = None
    target = heading.strip().lower()
    for idx, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip().lower() == target:
            start_idx = idx
            break
    if start_idx is None:
        return None, None
    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].startswith("# "):
            end_idx = idx
            break
    return start_idx, end_idx


def _preferred_ai_context_anchor(kind_name: str) -> list[str]:
    if kind_name == "request":
        return ["References", "Backlog"]
    if kind_name == "backlog":
        return ["References", "Priority", "Notes"]
    if kind_name == "task":
        return ["References", "Validation", "Definition of Done (DoD)"]
    return []


def refresh_ai_context_text(text: str, kind_name: str) -> tuple[str, bool]:
    lines = text.splitlines()
    title = _extract_title(lines) or "Untitled"
    values = build_workflow_doc_values(kind_name, doc_ref="placeholder", title=title)
    primary_items, secondary_items = _ai_context_inputs_for_kind(kind_name, text)
    _apply_ai_context_values(
        values,
        doc_kind=kind_name,
        title=title,
        source_text=text,
        primary_items=primary_items,
        secondary_items=secondary_items,
    )
    new_section = _render_ai_context_section(values)

    start_idx, end_idx = _section_bounds(lines, "AI Context")
    if start_idx is not None and end_idx is not None:
        updated_lines = lines[:start_idx] + new_section + lines[end_idx:]
    else:
        insert_at = len(lines)
        for anchor in _preferred_ai_context_anchor(kind_name):
            anchor_start, _anchor_end = _section_bounds(lines, anchor)
            if anchor_start is not None:
                insert_at = anchor_start
                break
        updated_lines = lines[:insert_at]
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.extend(new_section)
        if insert_at < len(lines):
            updated_lines.append("")
        updated_lines.extend(lines[insert_at:])

    refreshed = "\n".join(updated_lines).rstrip() + "\n"
    return refreshed, refreshed != text


def refresh_ai_context_file(path: Path, kind_name: str, dry_run: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    refreshed, changed = refresh_ai_context_text(original, kind_name)
    if not changed:
        return False
    _write(path, refreshed, dry_run)
    return True


def _auto_create_companion_docs(
    repo_root: Path,
    title: str,
    request_ref: str | None,
    backlog_ref: str | None,
    task_ref: str | None,
    assessment: DecisionAssessment,
    product_refs: list[str],
    architecture_refs: list[str],
    args: argparse.Namespace,
) -> tuple[list[str], list[str]]:
    created_product_refs = list(product_refs)
    created_architecture_refs = list(architecture_refs)

    if args.auto_create_adr and assessment.architecture_level == "Required" and not created_architecture_refs:
        planned = _plan_doc(repo_root, "logics/architecture", REF_PREFIXES["architecture"], title, dry_run=args.dry_run)
        content = _render_architecture_decision(title, planned.ref, request_ref, backlog_ref, task_ref)
        _write(planned.path, content, args.dry_run)
        created_architecture_refs.append(planned.ref)

    if args.auto_create_product_brief and assessment.product_level == "Required" and not created_product_refs:
        planned = _plan_doc(repo_root, "logics/product", REF_PREFIXES["product"], title, dry_run=args.dry_run)
        content = _render_product_brief(
            title,
            planned.ref,
            request_ref,
            backlog_ref,
            task_ref,
            created_architecture_refs,
        )
        _write(planned.path, content, args.dry_run)
        created_product_refs.append(planned.ref)

    return created_product_refs, created_architecture_refs


def _create_backlog_from_request(
    repo_root: Path,
    source_path: Path,
    title: str,
    args: argparse.Namespace,
) -> PlannedDoc:
    planned = _reserve_doc(repo_root / DOC_KINDS["backlog"].directory, DOC_KINDS["backlog"].prefix, title, args.dry_run)
    template_text = _template_path(Path(__file__), DOC_KINDS["backlog"].template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, title, include_progress=True, doc_kind="backlog")
    source_text = source_path.read_text(encoding="utf-8")
    source_ref = _doc_ref_from_path(source_path, DOC_KINDS["request"])
    source_rel = source_path.relative_to(repo_root)
    _copy_indicator_defaults(values, source_text)
    _seed_backlog_from_request(values, title, source_text, source_ref, source_rel)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(title, source_text))

    ref_text = _strip_mermaid_blocks(source_text)
    product_refs = sorted(_extract_refs(ref_text, REF_PREFIXES["product"]))
    architecture_refs = sorted(_extract_refs(ref_text, REF_PREFIXES["architecture"]))
    assessment = _assess_decision_framing(title, source_text)
    product_refs, architecture_refs = _auto_create_companion_docs(
        repo_root,
        title,
        request_ref=source_ref,
        backlog_ref=planned.ref,
        task_ref=None,
        assessment=assessment,
        product_refs=product_refs,
        architecture_refs=architecture_refs,
        args=args,
    )

    if source_ref is not None:
        values["REQUEST_LINK_PLACEHOLDER"] = f"`{source_ref}`"
    else:
        values["REQUEST_LINK_PLACEHOLDER"] = f"`{source_rel}`"
    _apply_decision_assessment(values, assessment)
    if product_refs:
        values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
    if architecture_refs:
        values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _generate_workflow_mermaid(repo_root, "backlog", title, values, dry_run=args.dry_run)
    content = _render_template(template_text, values).rstrip() + "\n"
    content, _changed = refresh_ai_context_text(content, "backlog")
    content, _changed = refresh_workflow_mermaid_signature_text(content, "backlog", repo_root=repo_root, dry_run=args.dry_run)
    _write(planned.path, content, args.dry_run)
    _update_request_backlog_links(source_path, planned.ref, args.dry_run)
    for ref in product_refs:
        _update_request_companion_links(source_path, "Product brief(s)", ref, args.dry_run)
    for ref in architecture_refs:
        _update_request_companion_links(source_path, "Architecture decision(s)", ref, args.dry_run)
    _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return planned


def _create_task_from_backlog(
    repo_root: Path,
    source_path: Path,
    title: str,
    args: argparse.Namespace,
) -> PlannedDoc:
    planned = _reserve_doc(repo_root / DOC_KINDS["task"].directory, DOC_KINDS["task"].prefix, title, args.dry_run)
    template_text = _template_path(Path(__file__), DOC_KINDS["task"].template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, title, include_progress=True, doc_kind="task")
    source_text = source_path.read_text(encoding="utf-8")
    source_ref = _doc_ref_from_path(source_path, DOC_KINDS["backlog"])
    source_rel = source_path.relative_to(repo_root)
    _copy_indicator_defaults(values, source_text)

    ref_text = _strip_mermaid_blocks(source_text)
    request_refs = sorted(_extract_refs(ref_text, REF_PREFIXES["request"]))
    product_refs = sorted(_extract_refs(ref_text, REF_PREFIXES["product"]))
    architecture_refs = sorted(_extract_refs(ref_text, REF_PREFIXES["architecture"]))
    assessment = _assess_decision_framing(title, source_text)
    primary_request_ref = request_refs[0] if request_refs else None
    product_refs, architecture_refs = _auto_create_companion_docs(
        repo_root,
        title,
        request_ref=primary_request_ref,
        backlog_ref=source_ref,
        task_ref=planned.ref,
        assessment=assessment,
        product_refs=product_refs,
        architecture_refs=architecture_refs,
        args=args,
    )

    _seed_task_from_backlog(values, title, source_text, source_ref, source_rel, request_refs)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(title, source_text))
    values["BACKLOG_LINK_PLACEHOLDER"] = f"`{source_ref}`" if source_ref is not None else f"`{source_rel}`"
    _apply_decision_assessment(values, assessment)
    if request_refs:
        values["REQUEST_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in request_refs)
    if product_refs:
        values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
    if architecture_refs:
        values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _generate_workflow_mermaid(repo_root, "task", title, values, dry_run=args.dry_run)
    content = _render_template(template_text, values).rstrip() + "\n"
    content, _changed = refresh_ai_context_text(content, "task")
    content, _changed = refresh_workflow_mermaid_signature_text(content, "task", repo_root=repo_root, dry_run=args.dry_run)
    _write(planned.path, content, args.dry_run)
    if source_ref is not None:
        existing_task_refs = sorted(_extract_refs(source_text, REF_PREFIXES["task"]) | {planned.ref})
        _update_backlog_task_links(source_path, existing_task_refs, args.dry_run)
    _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return planned



__all__ = [name for name in globals() if not name.startswith("__")]

__all__ = [name for name in globals() if not name.startswith("__")]
