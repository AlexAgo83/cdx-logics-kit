#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _parse_task(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = path.stem
    progress = ""
    plan: list[str] = []
    validation: list[str] = []
    in_plan = False
    in_validation = False

    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                title = match.group(1).strip()
            continue
        if line.startswith("> Progress:"):
            progress = line.split(":", 1)[1].strip()
        if line.strip() == "# Plan":
            in_plan = True
            in_validation = False
            continue
        if line.strip() == "# Validation":
            in_validation = True
            in_plan = False
            continue
        if line.startswith("# "):
            in_plan = False
            in_validation = False
        if in_plan and line.lstrip().startswith("- ["):
            plan.append(line.strip())
        if in_validation and line.lstrip().startswith("- "):
            validation.append(line.strip().removeprefix("- ").strip())

    return {"title": title, "progress": progress, "plan": plan, "validation": validation, "raw": text}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a PR description from a Logics task doc.")
    parser.add_argument("task_path")
    parser.add_argument("--out", default="PR.md")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    task_path = Path(args.task_path).resolve()
    if not task_path.is_file():
        raise SystemExit(f"Task not found: {task_path}")

    data = _parse_task(task_path)
    rel = task_path.relative_to(repo_root).as_posix()

    lines: list[str] = []
    lines.append(f"# {data['title']}")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(f"- Task: `{rel}`")
    if data["progress"]:
        lines.append(f"- Progress: {data['progress']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("- ")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("- In:")
    lines.append("- Out:")
    lines.append("")
    if data["plan"]:
        lines.append("## Plan checklist")
        lines.append("")
        lines.extend([f"- {p}" for p in data["plan"]])
        lines.append("")
    lines.append("## Validation")
    lines.append("")
    if data["validation"]:
        for cmd in data["validation"]:
            lines.append(f"- `{cmd}`")
    else:
        lines.append("- ")
    lines.append("")
    lines.append("## Risks / rollback")
    lines.append("")
    lines.append("- ")
    lines.append("")

    out_path = (repo_root / args.out).resolve()
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

