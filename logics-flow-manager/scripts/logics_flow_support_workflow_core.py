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

MERMAID_GENERATOR_SCRIPTS = Path(__file__).resolve().parents[2] / "logics-mermaid-generator" / "scripts"
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


def _extract_ai_context_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _section_lines(text, "AI Context"):
        match = AI_CONTEXT_FIELD_PATTERN.match(line.strip())
        if match is None:
            continue
        label = match.group(1).strip().lower()
        fields[label] = match.group(2).strip()
    return fields


def _plain_text_items(lines: Iterable[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^\s*-\s*(\[[ xX]\]\s*)?", "", stripped)
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        if stripped.startswith("```"):
            continue
        items.append(stripped.strip("` "))
    return items


def _truncate_summary(value: str, *, max_words: int = 18, max_chars: int = 160) -> str:
    cleaned = " ".join(value.replace("`", "").split())
    if not cleaned:
        return cleaned
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(".,;:") + "..."
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3].rstrip(" ,.;:") + "..."
    return cleaned


def _keyword_tokens(*parts: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", " ".join(parts).lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in AI_KEYWORD_STOPWORDS or token in seen:
            continue
        if token.isdigit():
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def _default_ai_use_when(doc_kind: str, title: str) -> str:
    if doc_kind == "request":
        return f"Use when framing scope, context, and acceptance checks for {title}."
    if doc_kind == "backlog":
        return f"Use when implementing or reviewing the delivery slice for {title}."
    return f"Use when executing the current implementation wave for {title}."


def _default_ai_skip_when(doc_kind: str) -> str:
    if doc_kind == "request":
        return "Skip when the work targets another feature, repository, or workflow stage."
    if doc_kind == "backlog":
        return "Skip when the change is unrelated to this delivery slice or its linked request."
    return "Skip when the work belongs to another backlog item or a different execution wave."


def _apply_ai_context_values(
    values: dict[str, str],
    *,
    doc_kind: str,
    title: str,
    source_text: str = "",
    primary_items: Iterable[str] = (),
    secondary_items: Iterable[str] = (),
) -> None:
    existing = _extract_ai_context_fields(source_text)
    primary = _plain_text_items(primary_items)
    secondary = _plain_text_items(secondary_items)
    summary = existing.get("summary")
    if not summary:
        summary = next((item for item in [*primary, *secondary] if item), "")
    if not summary:
        summary = f"{title} scope, constraints, and expected outcome need a compact handoff."
    keywords = existing.get("keywords")
    if not keywords:
        keyword_items = _keyword_tokens(title, " ".join(primary), " ".join(secondary))
        keywords = ", ".join(keyword_items) if keyword_items else "logics, workflow"
    values["AI_SUMMARY_PLACEHOLDER"] = _truncate_summary(summary)
    values["AI_KEYWORDS_PLACEHOLDER"] = keywords
    values["AI_USE_WHEN_PLACEHOLDER"] = existing.get("use when") or _default_ai_use_when(doc_kind, title)
    values["AI_SKIP_WHEN_PLACEHOLDER"] = existing.get("skip when") or _default_ai_skip_when(doc_kind)


def _normalize_reference_item(item: str) -> str:
    value = item.strip()
    if value.startswith("`") and value.endswith("`"):
        value = value[1:-1].strip()
    match = MARKDOWN_LINK_PATTERN.match(value)
    if match is not None:
        value = match.group(1).strip()
    return _repo_relative_path_hint(value)


def _repo_relative_path_hint(value: str) -> str:
    candidate = value.strip().strip("<>")
    if not candidate:
        return candidate
    if candidate.startswith("file://"):
        candidate = candidate.removeprefix("file://")
    normalized = candidate.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        return value.strip()
    for starter in REPO_PATH_STARTERS:
        if normalized == starter or normalized.startswith(starter):
            return normalized
        marker = f"/{starter}"
        index = normalized.find(marker)
        if index != -1:
            return normalized[index + 1 :]
    return normalized


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
    rendered.append("- [ ] CHECKPOINT: if the shared AI runtime is active and healthy, run `python logics/skills/logics.py flow assist commit-all` for the current step, item, or wave commit checkpoint.")
    rendered.append("- [ ] GATE: do not close a wave or step until the relevant automated tests and quality checks have been run successfully.")
    rendered.append("- [ ] FINAL: Update related Logics docs")
    return "\n".join(rendered)


def _render_validation_block(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        cleaned = [
            "Run the relevant automated tests for the changed surface before closing the current wave or step.",
            "Run the relevant lint or quality checks before closing the current wave or step.",
        ]
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
    if not title:
        return ""
    values = _workflow_mermaid_values_from_doc(text, kind_name)
    rendered = _render_workflow_mermaid(kind_name, title, values)
    match = MERMAID_SIGNATURE_PATTERN.search(rendered)
    return match.group(1) if match is not None else ""


def _section_block(text: str, heading: str, fallback: str = "") -> str:
    cleaned = _clean_section_lines(_section_lines(text, heading))
    if cleaned:
        return "\n".join(cleaned)
    return fallback


def _ref_placeholder(text: str, prefix: str, fallback: str = "(none yet)") -> str:
    refs = sorted(_extract_refs(text, prefix))
    if refs:
        return ", ".join(f"`{ref}`" for ref in refs)
    return fallback


def _workflow_mermaid_values_from_doc(text: str, kind_name: str) -> dict[str, str]:
    ref_text = _strip_mermaid_blocks(text)
    if kind_name == "request":
        return {
            "NEEDS_PLACEHOLDER": _section_block(text, "Needs", "- Describe the need"),
            "CONTEXT_PLACEHOLDER": _section_block(text, "Context", "- Add the relevant context"),
            "ACCEPTANCE_PLACEHOLDER": _section_block(text, "Acceptance criteria", "- AC1: Define a measurable outcome"),
        }

    if kind_name == "backlog":
        return {
            "PROBLEM_PLACEHOLDER": _section_block(text, "Problem", "- Describe the problem and user impact"),
            "ACCEPTANCE_BLOCK": _section_block(text, "Acceptance criteria", "- AC1: Define an objective acceptance check"),
            "REQUEST_LINK_PLACEHOLDER": _ref_placeholder(ref_text, REF_PREFIXES["request"]),
            "TASK_LINK_PLACEHOLDER": _ref_placeholder(ref_text, REF_PREFIXES["task"]),
        }

    if kind_name == "task":
        return {
            "PLAN_BLOCK": _section_block(
                text,
                "Plan",
                "- [ ] 1. Confirm scope\n- [ ] 2. Implement scope\n- [ ] 3. Validate result",
            ),
            "VALIDATION_BLOCK": _section_block(
                text,
                "Validation",
                "- Run the relevant automated tests before closing the current wave or step.",
            ),
            "BACKLOG_LINK_PLACEHOLDER": _ref_placeholder(ref_text, REF_PREFIXES["backlog"]),
        }

    raise ValueError(f"Unsupported Mermaid workflow kind: {kind_name}")


def _generate_workflow_mermaid(
    repo_root: Path,
    kind_name: str,
    title: str,
    values: dict[str, str],
    *,
    dry_run: bool,
) -> str:
    payload = generate_mermaid(
        repo_root=repo_root,
        kind_name=kind_name,
        title=title,
        values=values,
        dry_run=dry_run,
    )
    return str(payload["mermaid"]).strip()


def refresh_workflow_mermaid_signature_text(
    text: str,
    kind_name: str,
    *,
    repo_root: Path | None = None,
    dry_run: bool = False,
) -> tuple[str, bool]:
    match = MERMAID_BLOCK_PATTERN.search(text)
    if match is None:
        return text, False

    lines = text.splitlines()
    title = _extract_title(lines)
    if not title:
        return text, False

    resolved_repo_root = repo_root.resolve() if repo_root is not None else Path.cwd().resolve()
    values = _workflow_mermaid_values_from_doc(text, kind_name)
    refreshed_block = _generate_workflow_mermaid(
        resolved_repo_root,
        kind_name,
        title,
        values,
        dry_run=dry_run,
    )
    if match.group(0).strip() == refreshed_block:
        return text, False

    refreshed_text = text[: match.start()] + refreshed_block + text[match.end() :]
    return refreshed_text, True


def refresh_workflow_mermaid_signature_file(
    path: Path,
    kind_name: str,
    dry_run: bool,
    *,
    repo_root: Path | None = None,
) -> bool:
    original = path.read_text(encoding="utf-8")
    resolved_repo_root = repo_root.resolve() if repo_root is not None else _find_repo_root(path.parent)
    refreshed, changed = refresh_workflow_mermaid_signature_text(
        original,
        kind_name,
        repo_root=resolved_repo_root,
        dry_run=dry_run,
    )
    if not changed:
        return False
    _write(path, refreshed.rstrip() + "\n", dry_run)
    return True


def _render_ac_traceability_block(ac_entries: Iterable[tuple[str, str]], fallback: str) -> str:
    rendered = [
        f"- {ac_id} -> Scope: {summary}. Proof: capture validation evidence in this doc."
        for ac_id, summary in ac_entries
    ]
    if not rendered:
        rendered = [f"- AC1 -> {fallback}. Proof: capture validation evidence in this doc."]
    return "\n".join(rendered)


def _copy_indicator_defaults(values: dict[str, str], source_text: str) -> None:
    indicators = _indicator_map(source_text.splitlines())
    if indicators.get("From version"):
        values["FROM_VERSION"] = indicators["From version"]
    if indicators.get("Schema version"):
        values["SCHEMA_VERSION"] = indicators["Schema version"]
    if indicators.get("Understanding"):
        values["UNDERSTANDING"] = indicators["Understanding"]
    if indicators.get("Confidence"):
        values["CONFIDENCE"] = indicators["Confidence"]
    if indicators.get("Complexity"):
        values["COMPLEXITY"] = indicators["Complexity"]
    if indicators.get("Theme"):
        values["THEME"] = indicators["Theme"]


def _seed_backlog_from_request(
    values: dict[str, str],
    title: str,
    source_text: str,
    request_ref: str | None,
    source_rel: Path,
) -> None:
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
    notes.append("- Keep this backlog item as one bounded delivery slice; create sibling backlog items for the remaining request coverage instead of widening this doc.")
    if context_lines:
        notes.append(f"- Request context seeded into this backlog item from `{source_rel}`.")
    values["NOTES_PLACEHOLDER"] = "\n".join(notes)
    _apply_ai_context_values(
        values,
        doc_kind="backlog",
        title=title,
        source_text=source_text,
        primary_items=[*needs, *acceptance_items],
        secondary_items=context_lines,
    )


def _seed_task_from_backlog(
    values: dict[str, str],
    title: str,
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
            "Run the relevant automated tests for the changed surface before closing the current wave or step.",
            "Run the relevant lint or quality checks before closing the current wave or step.",
            "Confirm the completed wave leaves the repository in a commit-ready state.",
        ]
    )
    _apply_ai_context_values(
        values,
        doc_kind="task",
        title=title,
        source_text=source_text,
        primary_items=[*problem_lines, *acceptance_items],
        secondary_items=context_lines,
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


__all__ = [name for name in globals() if not name.startswith("__")]
