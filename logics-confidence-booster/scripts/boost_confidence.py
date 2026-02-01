#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Tuple


def detect_doc_type(path: Path) -> str:
    name = path.name
    if name.startswith("req_"):
        return "request"
    if name.startswith("item_"):
        return "backlog"
    if name.startswith("task_"):
        return "task"
    return "unknown"


def prompt_questions(questions: List[Tuple[str, str]], apply_defaults: bool) -> List[Tuple[str, str]]:
    answers: List[Tuple[str, str]] = []
    for idx, (question, suggestion) in enumerate(questions, start=1):
        if apply_defaults:
            answers.append((question, suggestion))
            continue
        prompt = f"Q{idx}: {question}\nSuggested: {suggestion}\nAnswer (enter to accept): "
        response = input(prompt).strip()
        answers.append((question, response or suggestion))
    return answers


def set_indicator(lines: List[str], key: str, value: str) -> None:
    target = f"> {key}:"
    for idx, line in enumerate(lines):
        if line.startswith(target):
            lines[idx] = f"> {key}: {value}"
            return
    insert_at = 1
    for idx, line in enumerate(lines):
        if line.startswith("> "):
            insert_at = idx + 1
    lines.insert(insert_at, f"> {key}: {value}")


def get_indicator(lines: List[str], key: str) -> str | None:
    target = f"> {key}:"
    for line in lines:
        if line.startswith(target):
            return line.split(":", 1)[1].strip()
    return None


def parse_percent(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\\d+)", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def compute_indicators(answered: int, total: int) -> tuple[int, int]:
    ratio = (answered / total) if total else 0.0
    understanding = int(round(70 + ratio * 24))
    confidence = int(round(65 + ratio * 27))
    return understanding, confidence


def upsert_section(lines: List[str], title: str, entries: List[str]) -> None:
    header = f"# {title}"
    header_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == header:
            header_idx = idx
            break
    if header_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.append("")
        lines.extend(entries)
        return

    insert_at = len(lines)
    for idx in range(header_idx + 1, len(lines)):
        if lines[idx].startswith("# "):
            insert_at = idx
            break
    if insert_at == header_idx + 1:
        lines.insert(insert_at, "")
        insert_at += 1
    for line in entries:
        lines.insert(insert_at, line)
        insert_at += 1


def build_questions(doc_type: str) -> List[Tuple[str, str]]:
    base = [
        (
            "Define the primary outcome and scope boundaries (in/out).",
            "In: core deliverables. Out: adjacent features or polish.",
        ),
        (
            "Define time window and granularity for any trends/rollups.",
            "Rolling 7-day window, daily buckets, local midnight.",
        ),
        (
            "Define metric sources and what counts (include offline or background gains?).",
            "Use deltas, include offline/background gains if applicable.",
        ),
        (
            "Define active vs inactive time rules (if relevant).",
            "Active = process/action running. Inactive = no active process.",
        ),
        (
            "Define mobile vs desktop layout expectations.",
            "Mobile-first with condensed order; desktop uses a broader dashboard layout.",
        ),
        (
            "Define persistence and retention.",
            "Persist in saved state; retain only the last 7 days of data.",
        ),
        (
            "Define edge cases and empty states.",
            "No data -> zeros + empty state; new users -> seeded buckets.",
        ),
    ]

    if doc_type == "backlog":
        return base + [
            (
                "Define acceptance criteria with measurable checks.",
                "Acceptance: outputs match spec; UI matches mockups; data persists across reloads.",
            ),
            (
                "Note dependencies and risks.",
                "Dependencies: data sources available; Risks: data drift, migration complexity.",
            ),
        ]

    if doc_type == "task":
        return base + [
            (
                "Define implementation checkpoints.",
                "Plan: data model -> aggregation -> UI -> QA.",
            ),
            (
                "Define validation commands.",
                "Run lint/tests/build relevant to the change.",
            ),
        ]

    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Boost Understanding/Confidence for Logics docs.")
    parser.add_argument("path", help="Path to a logics request/backlog/task markdown file.")
    parser.add_argument("--type", choices=["request", "backlog", "task"], help="Override doc type.")
    parser.add_argument("--apply-defaults", action="store_true", help="Use suggested defaults without prompts.")
    parser.add_argument("--understanding", help="Understanding indicator value (e.g. 85%).")
    parser.add_argument("--confidence", help="Confidence indicator value (e.g. 80%).")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing.")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    doc_type = args.type or detect_doc_type(path)
    questions = build_questions(doc_type)
    answers = prompt_questions(questions, args.apply_defaults)

    lines = path.read_text(encoding="utf-8").splitlines()
    current_understanding = get_indicator(lines, "Understanding") or "??%"
    current_confidence = get_indicator(lines, "Confidence") or "??%"

    understanding = args.understanding
    confidence = args.confidence

    if not args.apply_defaults:
        if understanding is None:
            response = input(
                f"Set Understanding (current {current_understanding})? "
                "Enter to auto-compute, or provide a %: "
            ).strip()
            if response:
                understanding = response
        if confidence is None:
            response = input(
                f"Set Confidence (current {current_confidence})? "
                "Enter to auto-compute, or provide a %: "
            ).strip()
            if response:
                confidence = response

    answered = sum(1 for _, answer in answers if answer.strip())
    auto_understanding, auto_confidence = compute_indicators(answered, len(questions))
    current_understanding_value = parse_percent(current_understanding)
    current_confidence_value = parse_percent(current_confidence)

    if understanding is None:
        target = auto_understanding
        if current_understanding_value is not None:
            target = max(current_understanding_value, auto_understanding)
        understanding = f"{target}%"

    if confidence is None:
        target = auto_confidence
        if current_confidence_value is not None:
            target = max(current_confidence_value, auto_confidence)
        confidence = f"{target}%"

    set_indicator(lines, "Understanding", understanding)
    set_indicator(lines, "Confidence", confidence)

    entries = [f"- {q} :: {a}" for q, a in answers]
    upsert_section(lines, "Clarifications", entries)

    output = "\n".join(lines).rstrip() + "\n"
    if args.dry_run:
        print(output)
        return 0

    path.write_text(output, encoding="utf-8")
    print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
