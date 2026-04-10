#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

FLOW_MANAGER_SCRIPTS = Path(__file__).resolve().parents[2] / "logics-flow-manager" / "scripts"
if str(FLOW_MANAGER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FLOW_MANAGER_SCRIPTS))

from logics_flow_support import expected_workflow_mermaid_signature


@dataclass(frozen=True)
class Kind:
    directory: str
    prefix: str
    requires_progress: bool
    required_indicators: tuple[str, ...]
    allowed_statuses: tuple[str, ...]


KINDS = {
    "request": Kind(
        "logics/request",
        "req",
        False,
        ("From version", "Understanding", "Confidence"),
        ("Draft", "Ready", "In progress", "Blocked", "Done", "Obsolete", "Archived"),
    ),
    "backlog": Kind(
        "logics/backlog",
        "item",
        True,
        ("From version", "Understanding", "Confidence", "Progress"),
        ("Draft", "Ready", "In progress", "Blocked", "Done", "Obsolete", "Archived"),
    ),
    "task": Kind(
        "logics/tasks",
        "task",
        True,
        ("From version", "Understanding", "Confidence", "Progress"),
        ("Draft", "Ready", "In progress", "Blocked", "Done", "Obsolete", "Archived"),
    ),
    "product": Kind(
        "logics/product",
        "prod",
        False,
        ("Date", "Status", "Related request", "Related backlog", "Related task", "Related architecture", "Reminder"),
        ("Draft", "Proposed", "Active", "Validated", "Rejected", "Superseded", "Archived"),
    ),
    "architecture": Kind(
        "logics/architecture",
        "adr",
        False,
        ("Date", "Status", "Drivers", "Related request", "Related backlog", "Related task", "Reminder"),
        ("Draft", "Proposed", "Accepted", "Rejected", "Superseded", "Archived"),
    ),
}

WORKFLOW_KINDS = {"request", "backlog", "task"}
ACTIVE_WORKFLOW_STATUSES = {"ready", "in progress", "done"}
CRITICAL_INDICATOR_PLACEHOLDERS = {
    "From version": {"X.X.X"},
    "Understanding": {"??%"},
    "Confidence": {"??%"},
    "Progress": {"??%"},
}
TEMPLATE_PLACEHOLDER_SNIPPETS = (
    "Describe the need",
    "Add context and constraints",
    "Describe the problem and user impact",
    "Define an objective acceptance check",
    "First implementation step",
    "Second implementation step",
    "Third implementation step",
)
BLOCKING_TRACEABILITY_PLACEHOLDER_SNIPPETS = (
    "Proof: TODO",
    "TODO: map this acceptance criterion",
)
GENERIC_MERMAID_SNIPPETS = (
    "Primary input or trigger",
    "Expected outcome",
    "User visible result",
    "Feedback or follow up",
    "Request source",
    "Problem to solve",
    "Scoped delivery",
    "Implementation task s",
    "Backlog source",
    "Implementation step 1",
    "Implementation step 2",
    "Implementation step 3",
    "Report and Done",
)
MERMAID_SIGNATURE_PATTERN = re.compile(r"^\s*%%\s*logics-signature:\s*(.+?)\s*$", re.MULTILINE)
MERMAID_BLOCK_PATTERN = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
MERMAID_LABEL_MAX_WORDS = 6
MERMAID_LABEL_MAX_CHARS = 42


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _extract_first_heading(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("## "):
            return line
    return None


def _indicator_value(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^\s*>\s*{re.escape(key)}\s*:\s*(.+)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def _has_indicator(lines: list[str], key: str) -> bool:
    return _indicator_value(lines, key) is not None


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


def _extract_title(lines: list[str]) -> str:
    heading = _extract_first_heading(lines)
    if heading is None:
        return ""
    match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", heading)
    if match:
        return match.group(1).strip()
    return heading.removeprefix("## ").strip()


def _section_lines(lines: list[str], heading: str) -> list[str]:
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


def _extract_refs(text: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
    return sorted({match.group(0) for match in pattern.finditer(text)})


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


def _expected_mermaid_signature(kind_name: str, lines: list[str]) -> str:
    return expected_workflow_mermaid_signature(kind_name, lines)


def _mermaid_warnings(kind_name: str, lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    match = MERMAID_BLOCK_PATTERN.search(text)
    if match is None:
        return ["missing Mermaid overview block"]

    block = match.group(1)
    warnings: list[str] = []
    generic_hits = [snippet for snippet in GENERIC_MERMAID_SNIPPETS if snippet in block]
    if generic_hits:
        warnings.append(
            "contains generic Mermaid scaffold content: " + ", ".join(sorted(set(generic_hits)))
        )

    signature_match = MERMAID_SIGNATURE_PATTERN.search(block)
    expected_signature = _expected_mermaid_signature(kind_name, lines)
    if signature_match is None:
        warnings.append("missing Mermaid context signature comment")
    elif expected_signature and signature_match.group(1).strip() != expected_signature:
        warnings.append(
            "Mermaid context signature is stale: "
            + f"expected `{expected_signature}`"
        )

    return warnings


def _run_git(repo_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _git_modified_paths(repo_root: Path) -> set[Path]:
    paths: set[Path] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMRT"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRT"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        output = _run_git(repo_root, args)
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            paths.add(Path(line))
    if not paths:
        output = _run_git(repo_root, ["diff-tree", "--no-commit-id", "--name-only", "-r", "--diff-filter=ACMRT", "HEAD"])
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            paths.add(Path(line))
    return paths


def _git_untracked_paths(repo_root: Path) -> set[Path]:
    paths: set[Path] = set()
    output = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        paths.add(Path(line))
    return paths


def _doc_diff(repo_root: Path, rel_path: Path) -> str:
    diff = _run_git(repo_root, ["diff", "--unified=0", "--", str(rel_path)])
    diff += _run_git(repo_root, ["diff", "--cached", "--unified=0", "--", str(rel_path)])
    if diff:
        return diff
    last_commit_paths = _git_modified_paths(repo_root)
    if rel_path in last_commit_paths:
        return _run_git(repo_root, ["show", "--format=", "--unified=0", "HEAD", "--", str(rel_path)])
    return ""


def _diff_has_indicator_changes(repo_root: Path, rel_path: Path, indicators: set[str]) -> bool:
    if not indicators:
        return True
    diff = _doc_diff(repo_root, rel_path)
    if not diff:
        return False
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        for key in indicators:
            if f"> {key}:" in line:
                return True
    return False


def _diff_is_status_only_normalization(repo_root: Path, rel_path: Path) -> bool:
    diff = _doc_diff(repo_root, rel_path)
    if not diff:
        return False

    saw_change = False
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith(("+++ ", "--- ")):
            continue

        changed = line[1:].strip()
        if not changed:
            continue

        saw_change = True
        if changed.startswith("> Status:"):
            continue
        return False

    return saw_change


def _diff_is_mermaid_signature_only(repo_root: Path, rel_path: Path) -> bool:
    diff = _doc_diff(repo_root, rel_path)
    if not diff:
        return False

    saw_change = False
    for line in diff.splitlines():
        if not line.startswith(("+", "-")):
            continue
        if line.startswith(("+++ ", "--- ")):
            continue

        changed = line[1:].strip()
        if not changed:
            continue

        saw_change = True
        if changed.startswith("%% logics-signature:"):
            continue
        return False

    return saw_change


def _workflow_status_is_active(lines: list[str]) -> bool:
    status_value = _indicator_value(lines, "Status")
    if status_value is None:
        return False
    return " ".join(status_value.split()).lower() in ACTIVE_WORKFLOW_STATUSES


def _blocking_placeholder_hits(lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    hits: list[str] = []
    for snippet in TEMPLATE_PLACEHOLDER_SNIPPETS:
        if snippet in text:
            hits.append(snippet)
    for snippet in BLOCKING_TRACEABILITY_PLACEHOLDER_SNIPPETS:
        if snippet in text:
            hits.append(snippet)
    return sorted(set(hits))


def _lint_file(path: Path, kind_name: str, kind: Kind, require_status: bool, check_changed_doc_rules: bool) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    name = path.name
    if not re.match(rf"^{re.escape(kind.prefix)}_\d{{3}}_[a-z0-9_]+\.md$", name):
        issues.append(f"bad filename: {name}")

    stem = path.stem
    lines = _read_lines(path)
    heading = _extract_first_heading(lines)
    if heading is None:
        issues.append("missing first heading (expected '## ...')")
    else:
        expected_prefix = f"## {stem} - "
        if not heading.startswith(expected_prefix):
            issues.append(f"bad heading: expected '{expected_prefix}<Title>'")

    for key in kind.required_indicators:
        if not _has_indicator(lines, key):
            issues.append(f"missing indicator: {key}")

    status_value = _indicator_value(lines, "Status")
    if status_value is None:
        if require_status:
            issues.append("missing indicator: Status")
    elif " ".join(status_value.split()).lower() not in {status.lower() for status in kind.allowed_statuses}:
        issues.append(
            "invalid Status value: "
            + status_value
            + " (allowed: "
            + " | ".join(kind.allowed_statuses)
            + ")"
        )

    if check_changed_doc_rules and kind_name in WORKFLOW_KINDS:
        for key, disallowed_values in CRITICAL_INDICATOR_PLACEHOLDERS.items():
            if key not in kind.required_indicators:
                continue
            current = _indicator_value(lines, key)
            if current in disallowed_values:
                issues.append(f"placeholder indicator: {key} = {current}")

        text = "\n".join(lines)
        placeholder_hits = [snippet for snippet in TEMPLATE_PLACEHOLDER_SNIPPETS if snippet in text]
        blocking_hits = _blocking_placeholder_hits(lines)
        if _workflow_status_is_active(lines) and blocking_hits:
            issues.append(
                "blocking placeholder content in active workflow doc: " + ", ".join(blocking_hits)
            )
        elif placeholder_hits:
            warnings.append(
                "contains template placeholder content: " + ", ".join(sorted(set(placeholder_hits)))
            )
        warnings.extend(_mermaid_warnings(kind_name, lines))

    return issues, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_lint.py",
        description="Lint Logics docs (filenames, headings, indicators).",
    )
    parser.add_argument(
        "--require-status",
        action="store_true",
        help="Require `Status` indicator in all supported Logics docs.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    all_issues: list[tuple[Path, list[str]]] = []
    all_warnings: list[tuple[Path, list[str]]] = []
    modified_paths = _git_modified_paths(repo_root)
    untracked_paths = _git_untracked_paths(repo_root)

    for kind_name, kind in KINDS.items():
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            rel_path = path.relative_to(repo_root)
            issues, warnings = _lint_file(
                path,
                kind_name,
                kind,
                require_status=args.require_status,
                check_changed_doc_rules=rel_path in modified_paths,
            )
            if rel_path in modified_paths and rel_path not in untracked_paths:
                required = set(kind.required_indicators)
                if (
                    not _diff_has_indicator_changes(repo_root, rel_path, required)
                    and not _diff_is_status_only_normalization(repo_root, rel_path)
                    and not _diff_is_mermaid_signature_only(repo_root, rel_path)
                ):
                    issues.append(
                        "modified without updating indicators: "
                        + ", ".join(sorted(required))
                    )
            if issues:
                all_issues.append((rel_path, issues))
            if warnings:
                all_warnings.append((rel_path, warnings))

    payload = {
        "ok": not all_issues,
        "issue_count": sum(len(issues) for _path, issues in all_issues),
        "warning_count": sum(len(warnings) for _path, warnings in all_warnings),
        "issues": [
            {"path": path.as_posix(), "message": issue}
            for path, issues in all_issues
            for issue in issues
        ],
        "warnings": [
            {"path": path.as_posix(), "message": warning}
            for path, warnings in all_warnings
            for warning in warnings
        ],
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not all_issues else 1

    if not all_issues and not all_warnings:
        print("Logics lint: OK")
        return 0

    if not all_issues:
        print("Logics lint: OK (warnings)")
        for path, warnings in all_warnings:
            for warning in warnings:
                print(f"- {path}: WARNING: {warning}")
        return 0

    print("Logics lint: FAILED")
    for path, issues in all_issues:
        for issue in issues:
            print(f"- {path}: {issue}")
    for path, warnings in all_warnings:
        for warning in warnings:
            print(f"- {path}: WARNING: {warning}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
