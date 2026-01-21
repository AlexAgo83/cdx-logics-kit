#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DOC_REF_RE = re.compile(r"^(req|item|task|spec)_(\d{3})_[a-z0-9_]+$")


@dataclass(frozen=True)
class DocInfo:
    path: Path
    ref: str
    kind: str
    title: str
    indicators: dict[str, str]
    outgoing_refs: set[str]
    contains_placeholders: bool


PLACEHOLDER_SNIPPETS: tuple[str, ...] = (
    "Describe the need",
    "Add context and constraints",
    "Describe the problem and user impact",
    "Define an objective acceptance check",
    "Define acceptance criteria",
    "First implementation step",
    "Second implementation step",
    "Third implementation step",
)


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _iter_docs(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for rel in ("logics/request", "logics/backlog", "logics/tasks", "logics/specs"):
        directory = repo_root / rel
        if not directory.is_dir():
            continue
        paths.extend(sorted(directory.glob("*.md")))
    return paths


def _parse_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
            return line.removeprefix("## ").strip()
    return fallback


def _parse_indicators(lines: list[str]) -> dict[str, str]:
    indicators: dict[str, str] = {}
    for line in lines:
        if not line.startswith("> "):
            if indicators:
                break
            continue
        if ":" not in line:
            continue
        key, value = line.removeprefix("> ").split(":", 1)
        indicators[key.strip()] = value.strip()
    return indicators


def _outgoing_refs(text: str, self_ref: str) -> set[str]:
    found = {m.group(0) for m in re.finditer(r"\b(req|item|task|spec)_(\d{3})_[a-z0-9_]+\b", text)}
    return {ref for ref in found if ref != self_ref}


def _contains_placeholders(text: str) -> bool:
    return any(snippet in text for snippet in PLACEHOLDER_SNIPPETS)


def _parse_doc(path: Path) -> DocInfo:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    ref = path.stem
    match = DOC_REF_RE.match(ref)
    kind = match.group(1) if match else "unknown"
    title = _parse_title(lines, fallback=ref)
    indicators = _parse_indicators(lines)
    outgoing = _outgoing_refs(text, self_ref=ref)
    placeholders = _contains_placeholders(text)
    return DocInfo(
        path=path,
        ref=ref,
        kind=kind,
        title=title,
        indicators=indicators,
        outgoing_refs=outgoing,
        contains_placeholders=placeholders,
    )


def _progress_bucket(value: str | None) -> str:
    if not value:
        return "(missing)"
    v = value.strip()
    if v == "??%":
        return "??%"
    try:
        pct = int(v.removesuffix("%"))
    except ValueError:
        return "(invalid)"
    if pct <= 0:
        return "0%"
    if pct < 50:
        return "1–49%"
    if pct < 100:
        return "50–99%"
    return "100%"


def _rel(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _render_report(repo_root: Path, docs: list[DocInfo]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_kind: dict[str, list[DocInfo]] = {"req": [], "item": [], "task": [], "spec": [], "unknown": []}
    for d in docs:
        by_kind.setdefault(d.kind, []).append(d)

    def count(kind: str) -> int:
        return len(by_kind.get(kind, []))

    placeholder_docs = [d for d in docs if d.contains_placeholders]
    unknown_docs = [d for d in docs if d.kind == "unknown"]
    stale_indicator_docs = [d for d in docs if any(v == "??%" for v in d.indicators.values())]

    tasks = by_kind.get("task", [])
    task_progress = {"(missing)": 0, "??%": 0, "0%": 0, "1–49%": 0, "50–99%": 0, "100%": 0, "(invalid)": 0}
    for t in tasks:
        task_progress[_progress_bucket(t.indicators.get("Progress"))] += 1

    backlog = by_kind.get("item", [])
    backlog_progress = {"(missing)": 0, "??%": 0, "0%": 0, "1–49%": 0, "50–99%": 0, "100%": 0, "(invalid)": 0}
    for b in backlog:
        backlog_progress[_progress_bucket(b.indicators.get("Progress"))] += 1

    lines: list[str] = []
    lines.append("# Logics Global Review")
    lines.append("")
    lines.append(f"_Generated: {now}_")
    lines.append("")
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- Requests: {count('req')}")
    lines.append(f"- Backlog items: {count('item')}")
    lines.append(f"- Tasks: {count('task')}")
    lines.append(f"- Specs: {count('spec')}")
    if unknown_docs:
        lines.append(f"- Unknown doc refs: {len(unknown_docs)} (non-standard filename)")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not docs:
        lines.append("_No Logics docs found._")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    lines.append(f"- Template placeholders remaining: {len(placeholder_docs)}")
    lines.append(f"- Indicators with unknown values (`??%`): {len(stale_indicator_docs)}")
    lines.append("")

    if placeholder_docs:
        lines.append("### Docs with template placeholders")
        lines.append("")
        for d in placeholder_docs:
            lines.append(f"- [{d.ref}]({_rel(repo_root, d.path)}) - {d.title}")
        lines.append("")

    if stale_indicator_docs:
        lines.append("### Docs with stale indicators")
        lines.append("")
        for d in stale_indicator_docs:
            rel = _rel(repo_root, d.path)
            keys = ", ".join(k for k, v in d.indicators.items() if v == "??%")
            lines.append(f"- [{d.ref}]({rel}) - {d.title} (unknown: {keys})")
        lines.append("")

    if tasks:
        lines.append("### Task progress distribution")
        lines.append("")
        lines.append("| Bucket | Count |")
        lines.append("|---|---:|")
        for bucket in ("(missing)", "??%", "0%", "1–49%", "50–99%", "100%", "(invalid)"):
            lines.append(f"| {bucket} | {task_progress[bucket]} |")
        lines.append("")

    if backlog:
        lines.append("### Backlog progress distribution")
        lines.append("")
        lines.append("| Bucket | Count |")
        lines.append("|---|---:|")
        for bucket in ("(missing)", "??%", "0%", "1–49%", "50–99%", "100%", "(invalid)"):
            lines.append(f"| {bucket} | {backlog_progress[bucket]} |")
        lines.append("")

    lines.append("## Recommendations (prioritized)")
    lines.append("")
    lines.append("1. Replace template placeholders in active docs and remove `??%` indicators once the scope is understood.")
    lines.append("2. Ensure each backlog item has measurable acceptance criteria and a clear priority (Impact/Urgency).")
    lines.append("3. Ensure each task has a step-by-step plan and at least 1–2 concrete validation commands.")
    lines.append("4. Keep relationships explicit: link request → backlog → task (and spec when useful).")
    lines.append("5. Generate supporting views when the doc set grows: `logics/INDEX.md` + `logics/RELATIONSHIPS.md`.")
    lines.append("")

    lines.append("## Suggested commands")
    lines.append("")
    lines.append("- `python3 logics/skills/logics-doc-linter/scripts/logics_lint.py`")
    lines.append("- `python3 logics/skills/logics-indexer/scripts/generate_index.py --out logics/INDEX.md`")
    lines.append("- `python3 logics/skills/logics-relationship-linker/scripts/link_relations.py --out logics/RELATIONSHIPS.md`")
    lines.append("- `python3 logics/skills/logics-duplicate-detector/scripts/find_duplicates.py --min-score 0.55`")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a global review report for Logics docs.")
    parser.add_argument("--out", help="Write the Markdown report to this path (relative to repo root).")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    docs = [_parse_doc(p) for p in _iter_docs(repo_root)]
    report = _render_report(repo_root, docs)

    if not args.out:
        sys.stdout.write(report)
        return 0

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

