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

@dataclass(frozen=True)
class PlannedDoc:
    ref: str
    path: Path


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


def _reserve_doc(directory: Path, prefix: str, title: str, dry_run: bool) -> PlannedDoc:
    slug = _slugify(title)
    # Treat missing workflow stage directories as an intentional self-healing case
    # for partially bootstrapped repos where the kit and flow manager are present.
    directory.mkdir(parents=True, exist_ok=True)

    for _ in range(50):
        doc_id = _next_id(directory, prefix)
        ref = f"{prefix}_{doc_id:03d}_{slug}"
        path = directory / f"{ref}.md"
        if dry_run:
            return PlannedDoc(ref=ref, path=path)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write("")
            return PlannedDoc(ref=ref, path=path)
        except FileExistsError:
            continue

    raise SystemExit(f"Could not reserve a unique `{prefix}` document id in {directory}")


def _template_path(script_path: Path, template_name: str) -> Path:
    return script_path.parent.parent / "assets" / "templates" / template_name


def _render_template(template_text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", repl, template_text)


def _plan_doc(repo_root: Path, directory: str, prefix: str, title: str, dry_run: bool = False) -> PlannedDoc:
    target_dir = repo_root / directory
    return _reserve_doc(target_dir, prefix, title, dry_run=dry_run)


def _indicator_map(lines: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    pattern = re.compile(r"^\s*>\s*([^:]+)\s*:\s*(.+)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            out[match.group(1).strip()] = match.group(2).strip()
    return out


def _section_lines(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start_idx = None
    target = heading.strip().lower()
    for idx, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip().lower() == target:
            start_idx = idx + 1
            break
    if start_idx is None:
        return []
    out: list[str] = []
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if line.startswith("# "):
            break
        out.append(line)
    return out


def _clean_section_lines(lines: Iterable[str]) -> list[str]:
    cleaned = [line.rstrip() for line in lines if line.strip()]
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return cleaned


def _list_items_from_section(text: str, heading: str) -> list[str]:
    items: list[str] = []
    for line in _section_lines(text, heading):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _acceptance_items(text: str) -> list[str]:
    return _list_items_from_section(text, "Acceptance criteria")


def _reference_items(text: str) -> list[str]:
    return _list_items_from_section(text, "References")


def _normalize_reference_item(item: str) -> str:
    value = item.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def _has_frontend_signals(*parts: str) -> bool:
    haystack = "\n".join(part for part in parts if part).strip()
    if not haystack:
        return False
    return FRONTEND_SIGNAL_PATTERN.search(haystack) is not None


def _extract_ac_ids(text: str) -> list[str]:
    ids: set[str] = set()
    pattern = re.compile(r"\b(AC\d+[a-z]?)\b", re.IGNORECASE)
    for match in pattern.finditer(text):
        ids.add(match.group(1).upper())
    return sorted(ids)


def _parse_acceptance_entries(items: list[str]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    explicit_pattern = re.compile(r"^(AC\d+[a-z]?)\s*:\s*(.+)$", re.IGNORECASE)
    generated_index = 1

    for raw_item in items:
        item = raw_item.strip()
        if not item:
            continue
        match = explicit_pattern.match(item)
        if match:
            ac_id = match.group(1).upper()
            summary = match.group(2).strip()
        else:
            while True:
                ac_id = f"AC{generated_index}"
                generated_index += 1
                if ac_id not in seen_ids:
                    break
            summary = item
        seen_ids.add(ac_id)
        entries.append((ac_id, summary))
    return entries


def _render_bullet_block(items: Iterable[str], fallback: str) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in cleaned)


def _render_plan_block(steps: list[str]) -> str:
    rendered = [f"- [ ] {idx}. {step}" for idx, step in enumerate(steps, start=1)]
    rendered.append("- [ ] CHECKPOINT: leave the current wave commit-ready and update the linked Logics docs before continuing.")
    rendered.append("- [ ] FINAL: Update related Logics docs")
    return "\n".join(rendered)


def _render_validation_block(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        cleaned = ["Run the relevant automated tests for the changed surface.", "Run the relevant lint or quality checks."]
    return "\n".join(f"- {item}" for item in cleaned)


def _render_references_section(items: Iterable[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        item = _normalize_reference_item(raw_item)
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    if not cleaned:
        return ""
    rendered = "\n".join(f"- `{item}`" for item in cleaned)
    return f"# References\n{rendered}"


def _collect_reference_items(title: str, source_text: str = "") -> list[str]:
    references = [_normalize_reference_item(item) for item in _reference_items(source_text)]
    if _has_frontend_signals(title, source_text) and UI_STEERING_REF not in references:
        references.append(UI_STEERING_REF)

    cleaned: list[str] = []
    seen: set[str] = set()
    for reference in references:
        if not reference or reference in seen:
            continue
        seen.add(reference)
        cleaned.append(reference)
    return cleaned


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _plain_text(value: str) -> str:
    text = _ascii_text(value)
    text = re.sub(r"`+", "", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[/{}[\]()+*#]", " ", text)
    text = re.sub(r"[^A-Za-z0-9:._ -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text


def _safe_mermaid_label(value: str, fallback: str) -> str:
    text = _plain_text(value)
    if not text:
        text = fallback
    words = text.split()
    if len(words) > MERMAID_LABEL_MAX_WORDS:
        text = " ".join(words[:MERMAID_LABEL_MAX_WORDS])
    if len(text) > MERMAID_LABEL_MAX_CHARS:
        text = text[:MERMAID_LABEL_MAX_CHARS].rstrip(" .:-")
    return text or fallback


def _rendered_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^- \[[ xX]\]\s*", "", stripped)
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        items.append(stripped)
    return items


def _pick_mermaid_summary(candidates: Iterable[str], fallback: str) -> str:
    for candidate in candidates:
        label = _safe_mermaid_label(candidate, "")
        if label:
            return label
    return fallback


def _mermaid_signature_part(value: str) -> str:
    text = _plain_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:40]


def _compose_mermaid_signature(kind_name: str, *parts: str) -> str:
    signature_parts = [_mermaid_signature_part(kind_name)]
    for part in parts:
        rendered = _mermaid_signature_part(part)
        if rendered:
            signature_parts.append(rendered)
    return "|".join(signature_parts)


def _render_mermaid_block(kind_name: str, signature: str, lines: list[str]) -> str:
    body = "\n".join(
        [
            "```mermaid",
            f"%% logics-kind: {kind_name}",
            f"%% logics-signature: {signature}",
            *lines,
            "```",
        ]
    )
    return body


def _render_request_mermaid(title: str, values: dict[str, str]) -> str:
    need_items = _rendered_list_items(values.get("NEEDS_PLACEHOLDER", ""))
    context_items = _rendered_list_items(values.get("CONTEXT_PLACEHOLDER", ""))
    acceptance_items = _rendered_list_items(values.get("ACCEPTANCE_PLACEHOLDER", ""))
    title_label = _safe_mermaid_label(title, "Request need")
    need_label = _pick_mermaid_summary([*need_items, *context_items, title], "Need scope")
    outcome_label = _pick_mermaid_summary([*acceptance_items, *context_items], "Acceptance target")
    feedback_label = _safe_mermaid_label(MERMAID_FALLBACKS["request_backlog"], MERMAID_FALLBACKS["request_backlog"])
    signature = _compose_mermaid_signature("request", title, need_label, outcome_label)
    return _render_mermaid_block(
        "request",
        signature,
        [
            "flowchart TD",
            f"    Trigger[{title_label}] --> Need[{need_label}]",
            f"    Need --> Outcome[{outcome_label}]",
            f"    Outcome --> Backlog[{feedback_label}]",
        ],
    )


def _render_backlog_mermaid(title: str, values: dict[str, str]) -> str:
    request_refs = sorted(_extract_refs(values.get("REQUEST_LINK_PLACEHOLDER", ""), REF_PREFIXES["request"]))
    task_refs = sorted(_extract_refs(values.get("TASK_LINK_PLACEHOLDER", ""), REF_PREFIXES["task"]))
    problem_items = _rendered_list_items(values.get("PROBLEM_PLACEHOLDER", ""))
    acceptance_items = _rendered_list_items(values.get("ACCEPTANCE_BLOCK", ""))
    source_label = _pick_mermaid_summary([*request_refs, title], "Request source")
    problem_label = _pick_mermaid_summary([*problem_items, title], "Problem scope")
    scope_label = _safe_mermaid_label(title, "Scoped delivery")
    acceptance_label = _pick_mermaid_summary(acceptance_items, "Acceptance check")
    task_label = _pick_mermaid_summary(task_refs, MERMAID_FALLBACKS["backlog_task"])
    signature = _compose_mermaid_signature("backlog", title, source_label, problem_label, acceptance_label)
    return _render_mermaid_block(
        "backlog",
        signature,
        [
            "flowchart LR",
            f"    Request[{source_label}] --> Problem[{problem_label}]",
            f"    Problem --> Scope[{scope_label}]",
            f"    Scope --> Acceptance[{acceptance_label}]",
            f"    Acceptance --> Tasks[{task_label}]",
        ],
    )


def _render_task_mermaid(title: str, values: dict[str, str]) -> str:
    backlog_refs = sorted(_extract_refs(values.get("BACKLOG_LINK_PLACEHOLDER", ""), REF_PREFIXES["backlog"]))
    plan_items = [
        item
        for item in _rendered_list_items(values.get("PLAN_BLOCK", ""))
        if not item.lower().startswith("final:")
    ]
    validation_items = _rendered_list_items(values.get("VALIDATION_BLOCK", ""))
    source_label = _pick_mermaid_summary([*backlog_refs, title], "Backlog source")
    step_one = _pick_mermaid_summary(plan_items[:1], "Confirm scope")
    step_two = _pick_mermaid_summary(plan_items[1:2], "Implement scope")
    step_three = _pick_mermaid_summary(plan_items[2:3], "Validate result")
    validation_label = _pick_mermaid_summary(validation_items, "Validation")
    report_label = _safe_mermaid_label(MERMAID_FALLBACKS["task_report"], MERMAID_FALLBACKS["task_report"])
    signature = _compose_mermaid_signature("task", title, source_label, step_one, validation_label)
    return _render_mermaid_block(
        "task",
        signature,
        [
            "flowchart LR",
            f"    Backlog[{source_label}] --> Step1[{step_one}]",
            f"    Step1 --> Step2[{step_two}]",
            f"    Step2 --> Step3[{step_three}]",
            f"    Step3 --> Validation[{validation_label}]",
            f"    Validation --> Report[{report_label}]",
        ],
    )


def _render_workflow_mermaid(kind_name: str, title: str, values: dict[str, str]) -> str:
    if kind_name == "request":
        return _render_request_mermaid(title, values)
    if kind_name == "backlog":
        return _render_backlog_mermaid(title, values)
    if kind_name == "task":
        return _render_task_mermaid(title, values)
    raise ValueError(f"Unsupported Mermaid workflow kind: {kind_name}")


def _extract_title(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
            return line.removeprefix("## ").strip()
    return ""


def expected_workflow_mermaid_signature(kind_name: str, lines: list[str]) -> str:
    text = "\n".join(lines)
    title = _extract_title(lines)
    if kind_name == "request":
        need_items = _rendered_list_items("\n".join(_section_lines(text, "Needs")))
        context_items = _rendered_list_items("\n".join(_section_lines(text, "Context")))
        acceptance_items = _rendered_list_items("\n".join(_section_lines(text, "Acceptance criteria")))
        need_label = _pick_mermaid_summary([*need_items, *context_items, title], "Need scope")
        outcome_label = _pick_mermaid_summary([*acceptance_items, *context_items], "Acceptance target")
        return _compose_mermaid_signature("request", title, need_label, outcome_label)

    if kind_name == "backlog":
        request_refs = sorted(_extract_refs(text, REF_PREFIXES["request"]))
        problem_items = _rendered_list_items("\n".join(_section_lines(text, "Problem")))
        acceptance_items = _rendered_list_items("\n".join(_section_lines(text, "Acceptance criteria")))
        source_label = _pick_mermaid_summary([*request_refs, title], "Request source")
        problem_label = _pick_mermaid_summary([*problem_items, title], "Problem scope")
        acceptance_label = _pick_mermaid_summary(acceptance_items, "Acceptance check")
        return _compose_mermaid_signature("backlog", title, source_label, problem_label, acceptance_label)

    if kind_name == "task":
        backlog_refs = sorted(_extract_refs(text, REF_PREFIXES["backlog"]))
        plan_items = [
            item
            for item in _rendered_list_items("\n".join(_section_lines(text, "Plan")))
            if not item.lower().startswith("final:")
        ]
        validation_items = _rendered_list_items("\n".join(_section_lines(text, "Validation")))
        source_label = _pick_mermaid_summary([*backlog_refs, title], "Backlog source")
        step_one = _pick_mermaid_summary(plan_items[:1], "Confirm scope")
        validation_label = _pick_mermaid_summary(validation_items, "Validation")
        return _compose_mermaid_signature("task", title, source_label, step_one, validation_label)

    return ""


def refresh_workflow_mermaid_signature_text(text: str, kind_name: str) -> tuple[str, bool]:
    match = MERMAID_BLOCK_PATTERN.search(text)
    if match is None:
        return text, False

    block = match.group(1)
    lines = text.splitlines()
    expected_signature = expected_workflow_mermaid_signature(kind_name, lines)
    if not expected_signature:
        return text, False

    signature_match = MERMAID_SIGNATURE_PATTERN.search(block)
    if signature_match is not None and signature_match.group(1).strip() == expected_signature:
        return text, False

    if signature_match is not None:
        refreshed_block = MERMAID_SIGNATURE_PATTERN.sub(
            f"%% logics-signature: {expected_signature}",
            block,
            count=1,
        )
    else:
        block_lines = block.splitlines()
        insert_at = 1 if block_lines and block_lines[0].lstrip().startswith("%% logics-kind:") else 0
        block_lines.insert(insert_at, f"%% logics-signature: {expected_signature}")
        refreshed_block = "\n".join(block_lines)

    refreshed_text = text[: match.start(1)] + refreshed_block + text[match.end(1) :]
    return refreshed_text, True


def refresh_workflow_mermaid_signature_file(path: Path, kind_name: str, dry_run: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    refreshed, changed = refresh_workflow_mermaid_signature_text(original, kind_name)
    if not changed:
        return False
    _write(path, refreshed.rstrip() + "\n", dry_run)
    return True


def _render_ac_traceability_block(ac_entries: Iterable[tuple[str, str]], fallback: str) -> str:
    rendered = [
        f"- {ac_id} -> Scope: {summary}. Proof: TODO."
        for ac_id, summary in ac_entries
    ]
    if not rendered:
        rendered = [f"- AC1 -> {fallback}. Proof: TODO."]
    return "\n".join(rendered)


def _copy_indicator_defaults(values: dict[str, str], source_text: str) -> None:
    indicators = _indicator_map(source_text.splitlines())
    if indicators.get("From version"):
        values["FROM_VERSION"] = indicators["From version"]
    if indicators.get("Understanding"):
        values["UNDERSTANDING"] = indicators["Understanding"]
    if indicators.get("Confidence"):
        values["CONFIDENCE"] = indicators["Confidence"]
    if indicators.get("Complexity"):
        values["COMPLEXITY"] = indicators["Complexity"]
    if indicators.get("Theme"):
        values["THEME"] = indicators["Theme"]


def _seed_backlog_from_request(values: dict[str, str], source_text: str, request_ref: str | None, source_rel: Path) -> None:
    needs = _list_items_from_section(source_text, "Needs")
    context_lines = _clean_section_lines(_section_lines(source_text, "Context"))
    acceptance_items = _acceptance_items(source_text)
    ac_entries = _parse_acceptance_entries(acceptance_items)

    problem_items = list(needs)
    if context_lines:
        problem_items.extend(context_lines[:2])

    values["PROBLEM_PLACEHOLDER"] = _render_bullet_block(problem_items, "Describe the problem and user impact")
    values["ACCEPTANCE_BLOCK"] = _render_bullet_block(
        acceptance_items,
        "AC1: Define an objective acceptance check",
    )
    values["AC_TRACEABILITY_PLACEHOLDER"] = _render_ac_traceability_block(
        ac_entries,
        "Backlog scope and delivery path are defined",
    )

    notes = []
    if request_ref is not None:
        notes.append(f"- Derived from request `{request_ref}`.")
    notes.append(f"- Source file: `{source_rel}`.")
    if context_lines:
        notes.append(f"- Request context seeded into this backlog item from `{source_rel}`.")
    values["NOTES_PLACEHOLDER"] = "\n".join(notes)


def _seed_task_from_backlog(
    values: dict[str, str],
    source_text: str,
    source_ref: str | None,
    source_rel: Path,
    request_refs: list[str],
) -> None:
    problem_lines = _clean_section_lines(_section_lines(source_text, "Problem"))
    acceptance_items = _acceptance_items(source_text)
    backlog_ac_entries = _parse_acceptance_entries(acceptance_items)

    context_lines = [
        f"- Derived from backlog item `{source_ref or source_rel}`.",
        f"- Source file: `{source_rel}`.",
    ]
    if request_refs:
        context_lines.append("- Related request(s): " + ", ".join(f"`{ref}`" for ref in request_refs) + ".")
    if problem_lines:
        context_lines.extend(problem_lines[:3])

    values["CONTEXT_PLACEHOLDER"] = "\n".join(context_lines)
    values["PLAN_BLOCK"] = _render_plan_block(
        [
            "Confirm scope, dependencies, and linked acceptance criteria.",
            "Implement the next coherent delivery wave from the backlog item.",
            "Checkpoint the wave in a commit-ready state, validate it, and update the linked Logics docs.",
        ]
    )
    values["AC_TRACEABILITY_PLACEHOLDER"] = _render_ac_traceability_block(
        backlog_ac_entries,
        "Implemented in the steps above",
    )
    values["VALIDATION_BLOCK"] = _render_validation_block(
        [
            "Run the relevant automated tests for the changed surface.",
            "Run the relevant lint or quality checks.",
            "Confirm the completed wave leaves the repository in a commit-ready state.",
        ]
    )


def _split_titles(raw_titles: list[str]) -> list[str]:
    titles = [title.strip() for title in raw_titles if title and title.strip()]
    if not titles:
        raise SystemExit("Provide at least one non-empty --title value.")
    return titles


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


def _mark_section_checkboxes_done(path: Path, heading: str, dry_run: bool) -> None:
    lines = _read_lines(path)
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip().lower() == f"# {heading}".lower():
            start_idx = idx + 1
            break
    if start_idx is None:
        return

    modified = False
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if line.startswith("# "):
            break
        if line.lstrip().startswith("- [ ]"):
            prefix, suffix = line.split("- [ ]", 1)
            lines[idx] = f"{prefix}- [x]{suffix}"
            modified = True
    if modified:
        _write(path, "\n".join(lines).rstrip() + "\n", dry_run)


def _section_body_bounds(lines: list[str], heading: str) -> tuple[int | None, int | None]:
    start_idx = None
    target = f"# {heading}".lower()
    for idx, line in enumerate(lines):
        if line.strip().lower() == target:
            start_idx = idx + 1
            break
    if start_idx is None:
        return None, None
    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if lines[idx].startswith("# "):
            end_idx = idx
            break
    return start_idx, end_idx


def _append_section_bullets(path: Path, heading: str, bullets: list[str], dry_run: bool) -> None:
    if not bullets:
        return
    lines = _read_lines(path)
    start_idx, end_idx = _section_body_bounds(lines, heading)
    if start_idx is None or end_idx is None:
        return

    existing = {line.strip() for line in lines[start_idx:end_idx] if line.strip()}
    new_lines = [bullet for bullet in bullets if bullet.strip() and bullet.strip() not in existing]
    if not new_lines:
        return

    insert_at = end_idx
    while insert_at > start_idx and not lines[insert_at - 1].strip():
        insert_at -= 1
    updated_lines = lines[:insert_at] + new_lines + lines[insert_at:]
    _write(path, "\n".join(updated_lines).rstrip() + "\n", dry_run)


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


def _extract_refs(text: str, prefix: str) -> set[str]:
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return {match.group(0) for match in pattern.finditer(text)}


def _strip_mermaid_blocks(text: str) -> str:
    return re.sub(r"```mermaid\s*\n.*?\n```", "", text, flags=re.DOTALL)


def _doc_ref_from_path(path: Path, kind: DocKind) -> str | None:
    stem = path.stem
    if stem.startswith(f"{kind.prefix}_"):
        return stem
    return None


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
        "VALIDATION_1": "Run the relevant automated tests for the changed surface.",
        "VALIDATION_2": "Run the relevant lint or quality checks.",
        "VALIDATION_BLOCK": _render_validation_block(
            [
                "Run the relevant automated tests for the changed surface.",
                "Run the relevant lint or quality checks.",
                "Confirm the completed wave leaves the repository in a commit-ready state.",
            ]
        ),
        "REPORT_PLACEHOLDER": "",
        "REFERENCES_SECTION": "",
        "MERMAID_BLOCK": "",
    }

    if not include_progress:
        values["PROGRESS"] = ""

    return values


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
    values = _build_template_values(args, planned.ref, title, include_progress=True)
    source_text = source_path.read_text(encoding="utf-8")
    source_ref = _doc_ref_from_path(source_path, DOC_KINDS["request"])
    source_rel = source_path.relative_to(repo_root)
    _copy_indicator_defaults(values, source_text)
    _seed_backlog_from_request(values, source_text, source_ref, source_rel)
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

    values["MERMAID_BLOCK"] = _render_workflow_mermaid("backlog", title, values)
    content = _render_template(template_text, values).rstrip() + "\n"
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
    values = _build_template_values(args, planned.ref, title, include_progress=True)
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

    _seed_task_from_backlog(values, source_text, source_ref, source_rel, request_refs)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(title, source_text))
    values["BACKLOG_LINK_PLACEHOLDER"] = f"`{source_ref}`" if source_ref is not None else f"`{source_rel}`"
    _apply_decision_assessment(values, assessment)
    if request_refs:
        values["REQUEST_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in request_refs)
    if product_refs:
        values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
    if architecture_refs:
        values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _render_workflow_mermaid("task", title, values)
    content = _render_template(template_text, values).rstrip() + "\n"
    _write(planned.path, content, args.dry_run)
    if source_ref is not None:
        existing_task_refs = sorted(_extract_refs(source_text, REF_PREFIXES["task"]) | {planned.ref})
        _update_backlog_task_links(source_path, existing_task_refs, args.dry_run)
    _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return planned



__all__ = [name for name in globals() if not name.startswith("__")]
