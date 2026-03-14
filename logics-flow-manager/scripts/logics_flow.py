#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


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

PRODUCT_SIGNAL_RULES = {
    "conversion journey": ("checkout", "signup", "sign up", "onboarding", "activation", "funnel", "conversion"),
    "pricing and packaging": ("pricing", "plan", "subscription", "trial", "paywall"),
    "user segmentation": ("persona", "segment", "target user", "role based"),
    "navigation and discoverability": ("navigation", "search", "filter", "discover", "browse", "menu"),
    "engagement loop": ("notification", "retention", "sharing", "invite", "feed"),
    "experience scope": ("dashboard", "settings", "profile", "empty state", "first run"),
}

ARCHITECTURE_SIGNAL_RULES = {
    "data model and persistence": ("schema", "database", "storage", "migration", "persistence", "data model"),
    "contracts and integration": ("api", "contract", "webhook", "integration", "provider", "sdk"),
    "runtime and boundaries": ("monolith", "modular", "module", "microservice", "boundary"),
    "state and sync": ("cache", "state management", "offline", "sync", "queue", "event", "stream"),
    "security and identity": ("auth", "authentication", "authorization", "permission", "security", "secret"),
    "delivery and operations": ("deployment", "infra", "observability", "monitoring", "performance", "scaling"),
}


@dataclass(frozen=True)
class DecisionAssessment:
    product_level: str
    product_signals: tuple[str, ...]
    architecture_level: str
    architecture_signals: tuple[str, ...]


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


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    pattern = r"\b" + re.escape(normalized_phrase).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _detect_signal_labels(text: str, rules: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    normalized = _normalize_text(text)
    labels: list[str] = []
    for label, phrases in rules.items():
        if any(_contains_phrase(normalized, phrase) for phrase in phrases):
            labels.append(label)
    return tuple(labels)


def _decision_level(title_signals: tuple[str, ...], all_signals: tuple[str, ...]) -> str:
    if title_signals or len(all_signals) >= 2:
        return "Required"
    if all_signals:
        return "Consider"
    return "Not needed"


def _assess_decision_framing(title: str, text: str) -> DecisionAssessment:
    combined = f"{title}\n{text}".strip()
    product_title_signals = _detect_signal_labels(title, PRODUCT_SIGNAL_RULES)
    product_signals = _detect_signal_labels(combined, PRODUCT_SIGNAL_RULES)
    architecture_title_signals = _detect_signal_labels(title, ARCHITECTURE_SIGNAL_RULES)
    architecture_signals = _detect_signal_labels(combined, ARCHITECTURE_SIGNAL_RULES)
    return DecisionAssessment(
        product_level=_decision_level(product_title_signals, product_signals),
        product_signals=product_signals,
        architecture_level=_decision_level(architecture_title_signals, architecture_signals),
        architecture_signals=architecture_signals,
    )


def _signals_display(signals: tuple[str, ...]) -> str:
    if not signals:
        return "(none detected)"
    return ", ".join(signals)


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


def _extract_ac_ids(text: str) -> list[str]:
    ids: set[str] = set()
    pattern = re.compile(r"\b(AC\d+[a-z]?)\b", re.IGNORECASE)
    for match in pattern.finditer(text):
        ids.add(match.group(1).upper())
    return sorted(ids)


def _render_bullet_block(items: Iterable[str], fallback: str) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in cleaned)


def _render_plan_block(steps: list[str]) -> str:
    rendered = [f"- [ ] {idx}. {step}" for idx, step in enumerate(steps, start=1)]
    rendered.append("- [ ] FINAL: Update related Logics docs")
    return "\n".join(rendered)


def _render_validation_block(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        cleaned = ["Run the relevant automated tests for the changed surface.", "Run the relevant lint or quality checks."]
    return "\n".join(f"- {item}" for item in cleaned)


def _render_ac_traceability_block(ac_ids: Iterable[str], fallback: str) -> str:
    rendered = [f"- {ac_id} -> TODO: map this acceptance criterion to scope. Proof: TODO." for ac_id in ac_ids]
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
    ac_ids = _extract_ac_ids("\n".join(acceptance_items))

    problem_items = list(needs)
    if context_lines:
        problem_items.extend(context_lines[:2])

    values["PROBLEM_PLACEHOLDER"] = _render_bullet_block(problem_items, "Describe the problem and user impact")
    values["ACCEPTANCE_BLOCK"] = _render_bullet_block(
        acceptance_items,
        "AC1: Define an objective acceptance check",
    )
    values["AC_TRACEABILITY_PLACEHOLDER"] = _render_ac_traceability_block(
        ac_ids,
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
    backlog_ac_ids = _extract_ac_ids(source_text)

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
            "Implement the scoped changes from the backlog item.",
            "Validate the result and update the linked Logics docs.",
        ]
    )
    values["AC_TRACEABILITY_PLACEHOLDER"] = _render_ac_traceability_block(
        backlog_ac_ids,
        "Implemented in the steps above",
    )
    values["VALIDATION_BLOCK"] = _render_validation_block(
        [
            "Run the relevant automated tests for the changed surface.",
            "Run the relevant lint or quality checks.",
        ]
    )


def _split_titles(raw_titles: list[str]) -> list[str]:
    titles = [title.strip() for title in raw_titles if title and title.strip()]
    if not titles:
        raise SystemExit("Provide at least one non-empty --title value.")
    return titles


def _render_product_brief(
    title: str,
    product_ref: str,
    request_ref: str | None,
    backlog_ref: str | None,
    task_ref: str | None,
    architecture_refs: list[str],
) -> str:
    template_path = Path(__file__).resolve().parents[2] / "logics-product-brief-writer" / "assets" / "templates" / "product_brief.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": product_ref,
        "TITLE": title,
        "DATE": date.today().isoformat(),
        "STATUS": "Proposed",
        "REQUEST_REF": f"`{request_ref}`" if request_ref else "(none yet)",
        "BACKLOG_REF": f"`{backlog_ref}`" if backlog_ref else "(none yet)",
        "TASK_REF": f"`{task_ref}`" if task_ref else "(none yet)",
        "ARCHITECTURE_REF": ", ".join(f"`{ref}`" for ref in architecture_refs) if architecture_refs else "(none yet)",
        "OVERVIEW": "Summarize the product direction, the targeted user value, and the main expected outcomes.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Problem[User problem] --> Direction[Chosen product direction]\n"
            "    Direction --> Value[User value]\n"
            "    Direction --> Scope[Scoped experience]\n"
            "    Direction --> Outcome[Expected product outcomes]"
        ),
        "PROBLEM": "Describe the user or business problem this brief resolves.",
        "USER_1": "Primary user or segment",
        "GOAL_1": "Primary product goal",
        "NON_GOAL_1": "Explicit non-goal or excluded expectation",
        "IN_SCOPE_1": "Main capability or experience slice included",
        "OUT_OF_SCOPE_1": "Main capability explicitly excluded for now",
        "DECISION_1": "Key product trade-off or framing decision",
        "SUCCESS_SIGNAL_1": "Observable success signal or product metric",
        "QUESTION_1": "Main open product question to resolve",
    }
    return _render_template(template_text, values).rstrip() + "\n"


def _render_architecture_decision(
    title: str,
    architecture_ref: str,
    request_ref: str | None,
    backlog_ref: str | None,
    task_ref: str | None,
) -> str:
    template_path = (
        Path(__file__).resolve().parents[2]
        / "logics-architecture-decision-writer"
        / "assets"
        / "templates"
        / "adr.md"
    )
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": architecture_ref,
        "TITLE": title,
        "DATE": date.today().isoformat(),
        "STATUS": "Proposed",
        "DRIVERS": "List the main architectural drivers.",
        "REQUEST_REF": f"`{request_ref}`" if request_ref else "(none yet)",
        "BACKLOG_REF": f"`{backlog_ref}`" if backlog_ref else "(none yet)",
        "TASK_REF": f"`{task_ref}`" if task_ref else "(none yet)",
        "OVERVIEW": "Summarize the chosen direction, what changes, and the main impacted areas.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Current[Current architecture] --> Decision[Chosen direction]\n"
            "    Decision --> App[Application layer]\n"
            "    Decision --> Data[Data and contracts]\n"
            "    Decision --> Ops[Deployment and observability]\n"
            "    Decision --> Team[Delivery and maintenance]"
        ),
        "CONTEXT": "Describe the problem, constraints, and drivers.",
        "DECISION": "State the chosen option and rationale.",
        "ALT_1": "Alternative option",
        "CONSEQUENCE_1": "Operational/product consequence",
        "MIGRATION_1": "Describe the rollout or migration step.",
        "FOLLOW_UP_1": "List the backlog or task work enabled by this decision.",
    }
    return _render_template(template_text, values).rstrip() + "\n"


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
        "ARCHITECTURE_FRAMING_STATUS": "Not needed",
        "ARCHITECTURE_FRAMING_SIGNALS": "(none detected)",
        "BACKLOG_LINK_PLACEHOLDER": "`item_XXX_example`",
        "TASK_LINK_PLACEHOLDER": "`task_XXX_example`",
        "STEP_1": "First implementation step",
        "STEP_2": "Second implementation step",
        "STEP_3": "Third implementation step",
        "PLAN_BLOCK": _render_plan_block(
            ["First implementation step", "Second implementation step", "Third implementation step"]
        ),
        "VALIDATION_1": "npm run tests",
        "VALIDATION_2": "npm run lint",
        "VALIDATION_BLOCK": _render_validation_block(["npm run tests", "npm run lint"]),
        "REPORT_PLACEHOLDER": "",
    }

    if not include_progress:
        values["PROGRESS"] = ""

    return values


def _apply_decision_assessment(values: dict[str, str], assessment: DecisionAssessment) -> None:
    values["PRODUCT_FRAMING_STATUS"] = assessment.product_level
    values["PRODUCT_FRAMING_SIGNALS"] = _signals_display(assessment.product_signals)
    values["ARCHITECTURE_FRAMING_STATUS"] = assessment.architecture_level
    values["ARCHITECTURE_FRAMING_SIGNALS"] = _signals_display(assessment.architecture_signals)


def _print_decision_summary(
    doc_ref: str,
    assessment: DecisionAssessment,
    product_refs: list[str],
    architecture_refs: list[str],
) -> None:
    product_line = assessment.product_level
    if assessment.product_signals:
        product_line += f" ({_signals_display(assessment.product_signals)})"
    architecture_line = assessment.architecture_level
    if assessment.architecture_signals:
        architecture_line += f" ({_signals_display(assessment.architecture_signals)})"
    lines = [
        f"Decision framing for {doc_ref}:",
        f"- Product: {product_line}",
        f"- Architecture: {architecture_line}",
        f"- Product brief refs: {', '.join(product_refs) if product_refs else '(none yet)'}",
        f"- Architecture decision refs: {', '.join(architecture_refs) if architecture_refs else '(none yet)'}",
    ]
    if assessment.product_level in {"Consider", "Required"} and not product_refs:
        lines.append("- Suggested follow-up: create or link a product brief before delivery gets deeper.")
    if assessment.architecture_level in {"Consider", "Required"} and not architecture_refs:
        lines.append("- Suggested follow-up: create or link an architecture decision before irreversible implementation work.")
    print("\n".join(lines))


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

    product_refs = sorted(_extract_refs(source_text, REF_PREFIXES["product"]))
    architecture_refs = sorted(_extract_refs(source_text, REF_PREFIXES["architecture"]))
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

    request_refs = sorted(_extract_refs(source_text, REF_PREFIXES["request"]))
    product_refs = sorted(_extract_refs(source_text, REF_PREFIXES["product"]))
    architecture_refs = sorted(_extract_refs(source_text, REF_PREFIXES["architecture"]))
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
    values["BACKLOG_LINK_PLACEHOLDER"] = f"`{source_ref}`" if source_ref is not None else f"`{source_rel}`"
    _apply_decision_assessment(values, assessment)
    if request_refs:
        values["REQUEST_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in request_refs)
    if product_refs:
        values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
    if architecture_refs:
        values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    content = _render_template(template_text, values).rstrip() + "\n"
    _write(planned.path, content, args.dry_run)
    if source_ref is not None:
        existing_task_refs = sorted(_extract_refs(source_text, REF_PREFIXES["task"]) | {planned.ref})
        _update_backlog_task_links(source_path, existing_task_refs, args.dry_run)
    _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return planned


def cmd_new(args: argparse.Namespace) -> None:
    doc_kind = DOC_KINDS[args.kind]
    repo_root = _find_repo_root(Path.cwd())
    planned = _reserve_doc(repo_root / doc_kind.directory, doc_kind.prefix, args.slug or args.title, args.dry_run)

    template_text = _template_path(Path(__file__), doc_kind.template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, args.title, doc_kind.include_progress)
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

    text = source_path.read_text(encoding="utf-8")
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

            item_text = item_path.read_text(encoding="utf-8")
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
    task_text = task_path.read_text(encoding="utf-8")
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

        item_text = item_path.read_text(encoding="utf-8")
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
