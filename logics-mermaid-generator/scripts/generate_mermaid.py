#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata

MERMAID_LABEL_MAX_WORDS = 6
MERMAID_LABEL_MAX_CHARS = 42
MERMAID_FALLBACKS = {
    "request_backlog": "Backlog slice",
    "backlog_task": "Execution task",
    "task_report": "Done report",
}
REF_PREFIXES = {
    "request": "req",
    "backlog": "item",
    "task": "task",
}


def _plain_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>]+", " ", text)
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


def _pick_mermaid_summary(candidates: list[str], fallback: str) -> str:
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
    return "\n".join(
        [
            "```mermaid",
            f"%% logics-kind: {kind_name}",
            f"%% logics-signature: {signature}",
            *lines,
            "```",
        ]
    )


def _extract_refs(text: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return sorted({match.group(0) for match in pattern.finditer(text)})


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
    request_refs = _extract_refs(values.get("REQUEST_LINK_PLACEHOLDER", ""), REF_PREFIXES["request"])
    task_refs = _extract_refs(values.get("TASK_LINK_PLACEHOLDER", ""), REF_PREFIXES["task"])
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
    backlog_refs = _extract_refs(values.get("BACKLOG_LINK_PLACEHOLDER", ""), REF_PREFIXES["backlog"])
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic Mermaid blocks for Logics workflow docs.")
    parser.add_argument("--kind", choices=("request", "backlog", "task"), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--values-json", default="{}", help="JSON object with template placeholder values.")
    args = parser.parse_args()

    try:
        values = json.loads(args.values_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid --values-json payload: {exc}") from exc
    if not isinstance(values, dict):
        raise SystemExit("--values-json must decode to an object.")
    normalized = {str(key): str(value) for key, value in values.items()}
    print(_render_workflow_mermaid(args.kind, args.title, normalized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
