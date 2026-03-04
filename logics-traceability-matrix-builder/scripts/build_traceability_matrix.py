#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

STOPWORDS = {
    "with",
    "from",
    "this",
    "that",
    "when",
    "then",
    "should",
    "must",
    "have",
    "into",
    "after",
    "before",
    "under",
    "over",
    "will",
    "user",
    "users",
    "data",
    "task",
    "item",
    "spec",
    "logics",
}


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory).")


def _extract_acceptance_criteria(lines: list[str]) -> list[str]:
    start: int | None = None
    heading_level = 0
    for i, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        heading_text = match.group(2).strip().lower()
        if "acceptance criteria" in heading_text:
            start = i + 1
            heading_level = len(match.group(1))
            break

    if start is None:
        return []

    section: list[str] = []
    for raw in lines[start:]:
        match = HEADING_RE.match(raw.strip())
        if match and len(match.group(1)) <= heading_level:
            break
        section.append(raw)

    criteria: list[str] = []
    for raw in section:
        stripped = raw.strip()
        bullet = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)
        if bullet:
            criteria.append(re.sub(r"\s+", " ", bullet.group(2)).strip())
            continue
        if criteria and stripped and not stripped.startswith("#"):
            criteria[-1] = f"{criteria[-1]} {stripped}"

    return [c for c in criteria if c]


def _infer_test_type(text: str) -> str:
    value = text.lower()
    e2e_keywords = (
        "screen",
        "ui",
        "modal",
        "click",
        "keyboard",
        "workspace",
        "navigation",
        "onboarding",
        "layout",
    )
    unit_keywords = (
        "parser",
        "validator",
        "normalize",
        "format",
        "utility",
        "helper",
        "pure function",
        "mapping",
    )
    integration_keywords = (
        "import",
        "export",
        "save",
        "persist",
        "store",
        "migration",
        "csv",
        "api",
        "undo",
        "redo",
    )
    if any(k in value for k in e2e_keywords):
        return "E2E"
    if any(k in value for k in unit_keywords):
        return "Unit"
    if any(k in value for k in integration_keywords):
        return "Integration"
    return "Integration"


def _keyword_tokens(text: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())
    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        unique.append(token)
        if len(unique) >= limit:
            break
    return unique


def _collect_test_files(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for rel in ("tests", "src"):
        base = repo_root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            p = path.as_posix().lower()
            name = path.name.lower()
            if ".test." in name or ".spec." in name or "__tests__" in p or "/e2e/" in p:
                candidates.append(path)
    return candidates


def _match_candidate_tests(test_files: list[Path], tokens: list[str], limit: int = 3) -> list[str]:
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for path in test_files:
        value = path.as_posix().lower()
        score = sum(1 for token in tokens if token in value)
        if score <= 0:
            continue
        scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], item[1]))
    result: list[str] = []
    for _, rel in scored:
        if rel in result:
            continue
        result.append(rel)
        if len(result) >= limit:
            break
    return result


def _validation_commands(repo_root: Path) -> list[str]:
    package_json = repo_root / "package.json"
    if not package_json.is_file():
        return []
    try:
        scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
    except json.JSONDecodeError:
        return []
    if not isinstance(scripts, dict):
        return []

    command_order: list[list[str]] = [
        ["lint"],
        ["tests", "test"],
        ["typecheck"],
        ["build"],
        ["test:e2e", "e2e", "playwright"],
    ]
    commands: list[str] = []
    for aliases in command_order:
        selected = next((alias for alias in aliases if alias in scripts), None)
        if selected:
            commands.append(f"npm run {selected}")
    return commands


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _render_traceability_section(rows: list[dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append("## Traceability matrix")
    lines.append("")
    if not rows:
        lines.append("_No acceptance criteria were found in this document._")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("| AC ID | Acceptance Criterion | Test Type | Candidate Tests | Validation Commands |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(row["ac_id"]),
                    _escape_cell(row["criterion"]),
                    _escape_cell(row["test_type"]),
                    _escape_cell(row["candidate_tests"]),
                    _escape_cell(row["validation_commands"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _upsert_traceability_section(path: Path, section: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    new_block = section.rstrip().splitlines()

    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## traceability matrix":
            start = i
            break

    if start is None:
        updated = lines + [""] + new_block
    else:
        end = start + 1
        while end < len(lines):
            if lines[end].startswith("## "):
                break
            end += 1
        updated = lines[:start] + new_block + ([""] if end < len(lines) else []) + lines[end:]

    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build a traceability matrix from Logics acceptance criteria.")
    parser.add_argument("doc", help="Backlog/task/spec markdown file.")
    parser.add_argument("--out", help="Write generated matrix markdown to a separate file.")
    parser.add_argument(
        "--update-doc",
        action="store_true",
        help="Upsert a `## Traceability matrix` section in the source document.",
    )
    args = parser.parse_args(argv)

    doc_path = Path(args.doc)
    if not doc_path.is_file():
        raise SystemExit(f"File not found: {doc_path}")

    repo_root = _find_repo_root(Path.cwd())
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    criteria = _extract_acceptance_criteria(lines)
    test_files = _collect_test_files(repo_root)
    commands = _validation_commands(repo_root)
    commands_text = ", ".join(commands) if commands else "n/a"

    rows: list[dict[str, str]] = []
    for index, criterion in enumerate(criteria, start=1):
        tokens = _keyword_tokens(criterion)
        candidates = _match_candidate_tests(test_files, tokens)
        rows.append(
            {
                "ac_id": f"AC-{index:02d}",
                "criterion": criterion,
                "test_type": _infer_test_type(criterion),
                "candidate_tests": ", ".join(candidates) if candidates else "n/a",
                "validation_commands": commands_text,
            }
        )

    section = _render_traceability_section(rows)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(section, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(repo_root) if out_path.is_relative_to(repo_root) else out_path}")

    if args.update_doc:
        _upsert_traceability_section(doc_path, section)
        print(f"Updated {doc_path}")

    if not args.out and not args.update_doc:
        sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
