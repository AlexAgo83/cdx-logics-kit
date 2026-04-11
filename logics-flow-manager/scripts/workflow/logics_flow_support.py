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
    return script_path.parent.parent.parent / "assets" / "templates" / template_name


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



from logics_flow_support_workflow import *  # noqa: F401,F403
