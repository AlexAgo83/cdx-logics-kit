#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROGRESS_RE = re.compile(r"^>\s*Progress:\s*([0-9]{1,3}|[?]{2})%")
RISKY_KEYWORDS = ("migration", "import", "export", "delete", "persist", "rollback", "version")


@dataclass(frozen=True)
class GateResult:
    failures: list[str]
    warnings: list[str]
    checked_completed_tasks: int
    checked_completed_backlog_items: int


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory).")


def _extract_progress(lines: list[str]) -> int | None:
    for line in lines:
        match = PROGRESS_RE.match(line.strip())
        if not match:
            continue
        raw = match.group(1)
        if raw == "??":
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value
    return None


def _has_heading(lines: list[str], heading: str) -> bool:
    target = heading.strip().lower()
    return any(line.strip().lower() == target for line in lines)


def _is_risky_task(text: str) -> bool:
    value = text.lower()
    return any(keyword in value for keyword in RISKY_KEYWORDS)


def _check_gate(repo_root: Path, require_release_notes: bool) -> GateResult:
    failures: list[str] = []
    warnings: list[str] = []

    tasks_dir = repo_root / "logics" / "tasks"
    backlog_dir = repo_root / "logics" / "backlog"
    completed_tasks = 0
    completed_backlog = 0

    if tasks_dir.is_dir():
        for path in sorted(tasks_dir.glob("task_*.md")):
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            progress = _extract_progress(lines)
            if progress is None:
                warnings.append(f"{path.as_posix()}: missing or unknown Progress indicator.")
                continue
            if progress < 100:
                continue
            completed_tasks += 1

            if not _has_heading(lines, "# Validation"):
                failures.append(f"{path.as_posix()}: completed task missing `# Validation`.")
            if not _has_heading(lines, "# Report"):
                failures.append(f"{path.as_posix()}: completed task missing `# Report`.")
            if _is_risky_task(text) and not (
                _has_heading(lines, "# Risks & rollback") or "rollback" in text.lower()
            ):
                failures.append(f"{path.as_posix()}: risky completed task missing rollback coverage.")

    if backlog_dir.is_dir():
        for path in sorted(backlog_dir.glob("item_*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            progress = _extract_progress(lines)
            if progress is None or progress < 100:
                continue
            completed_backlog += 1
            has_ac_heading = any("acceptance criteria" in line.strip().lower() for line in lines if line.startswith("#"))
            if not has_ac_heading:
                failures.append(f"{path.as_posix()}: completed backlog item missing acceptance criteria heading.")

    changelog = repo_root / "logics" / "CHANGELOG.md"
    if not changelog.is_file():
        failures.append("logics/CHANGELOG.md is missing.")

    if require_release_notes:
        release_notes = repo_root / "logics" / "RELEASE_NOTES.md"
        if not release_notes.is_file():
            failures.append("logics/RELEASE_NOTES.md is missing (--require-release-notes enabled).")

    return GateResult(
        failures=failures,
        warnings=warnings,
        checked_completed_tasks=completed_tasks,
        checked_completed_backlog_items=completed_backlog,
    )


def _render_report(result: GateResult) -> str:
    lines: list[str] = []
    lines.append("# Release Gate Report")
    lines.append("")
    outcome = "PASS" if not result.failures else "FAIL"
    lines.append(f"## Outcome: {outcome}")
    lines.append("")
    lines.append(f"- Completed tasks checked: {result.checked_completed_tasks}")
    lines.append(f"- Completed backlog items checked: {result.checked_completed_backlog_items}")
    lines.append(f"- Failures: {len(result.failures)}")
    lines.append(f"- Warnings: {len(result.warnings)}")
    lines.append("")

    if result.failures:
        lines.append("## Failures")
        lines.append("")
        for failure in result.failures:
            lines.append(f"- {failure}")
        lines.append("")

    if result.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    if not result.failures and not result.warnings:
        lines.append("_No gate issues detected._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run release-readiness gates over Logics docs.")
    parser.add_argument("--out", help="Write the report to this file.")
    parser.add_argument(
        "--require-release-notes",
        action="store_true",
        help="Fail if logics/RELEASE_NOTES.md is missing.",
    )
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    result = _check_gate(repo_root, require_release_notes=args.require_release_notes)
    report = _render_report(result)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(repo_root) if out_path.is_relative_to(repo_root) else out_path}")
    else:
        sys.stdout.write(report)

    return 1 if result.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
