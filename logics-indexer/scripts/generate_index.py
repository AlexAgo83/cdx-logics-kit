#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FLOW_MANAGER_SCRIPTS = Path(__file__).resolve().parents[2] / "logics-flow-manager" / "scripts"
if str(FLOW_MANAGER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FLOW_MANAGER_SCRIPTS))

from logics_flow_config import load_repo_config
from logics_flow_index import load_runtime_index


@dataclass(frozen=True)
class Entry:
    path: Path
    doc_ref: str
    title: str
    progress: str | None


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _parse_doc(path: Path) -> Entry:
    lines = path.read_text(encoding="utf-8").splitlines()
    doc_ref = path.stem
    title = ""
    progress: str | None = None

    for line in lines:
        if line.startswith("## "):
            match = re.match(r"^##\s+(\S+)\s*-\s*(.+?)\s*$", line)
            if match:
                doc_ref = match.group(1).strip()
                title = match.group(2).strip()
            else:
                title = line.removeprefix("## ").strip()
            continue
        if line.startswith("> Progress:"):
            progress = line.split(":", 1)[1].strip()
    if not title:
        title = "(missing title)"
    return Entry(path=path, doc_ref=doc_ref, title=title, progress=progress)


def _collect_from_paths(paths: list[Path]) -> list[Entry]:
    return [_parse_doc(path) for path in sorted(paths)]


def _collect(repo_root: Path, index_payload: dict[str, object], rel_dir: str) -> list[Entry]:
    if rel_dir not in {"logics/request", "logics/backlog", "logics/tasks"}:
        directory = repo_root / rel_dir
        if not directory.is_dir():
            return []
        return _collect_from_paths(sorted(directory.glob("*.md")))
    indexed = index_payload.get("workflow_docs", {})
    paths = [
        repo_root / rel_path
        for rel_path in sorted(indexed.keys())
        if rel_path.startswith(f"{rel_dir}/")
    ]
    return _collect_from_paths(paths)


def _render_section(title: str, entries: list[Entry], show_progress: bool, out_dir: Path) -> str:
    lines: list[str] = [f"## {title}", ""]
    if not entries:
        lines.append("_None_")
        lines.append("")
        return "\n".join(lines)

    header = "| Doc | Title |"
    sep = "|---|---|"
    if show_progress:
        header = "| Doc | Title | Progress |"
        sep = "|---|---|---|"
    lines.extend([header, sep])

    for entry in entries:
        rel = os.path.relpath(entry.path, start=out_dir).replace(os.sep, "/")
        doc_link = f"[{entry.doc_ref}]({rel})"
        if show_progress:
            lines.append(f"| {doc_link} | {entry.title} | {entry.progress or ''} |")
        else:
            lines.append(f"| {doc_link} | {entry.title} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate logics/INDEX.md from Logics docs.")
    parser.add_argument("--out", default="logics/INDEX.md")
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild the runtime index instead of reusing unchanged entries.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    config, _config_path = load_repo_config(repo_root)
    runtime_index = load_runtime_index(repo_root, config=config, force=args.force_reindex)
    architecture = _collect(repo_root, runtime_index, "logics/architecture")
    product = _collect(repo_root, runtime_index, "logics/product")
    requests = _collect(repo_root, runtime_index, "logics/request")
    backlog = _collect(repo_root, runtime_index, "logics/backlog")
    tasks = _collect(repo_root, runtime_index, "logics/tasks")
    out_path = (repo_root / args.out).resolve()
    out_dir = out_path.parent

    content = "\n".join(
        [
            "# Logics Index",
            "",
            _render_section("Architecture decisions", architecture, False, out_dir),
            _render_section("Product briefs", product, False, out_dir),
            _render_section("Requests", requests, False, out_dir),
            _render_section("Backlog", backlog, True, out_dir),
            _render_section("Tasks", tasks, True, out_dir),
        ]
    ).rstrip() + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    payload = {
        "ok": True,
        "output_path": str(printable),
        "counts": {
            "architecture": len(architecture),
            "product": len(product),
            "request": len(requests),
            "backlog": len(backlog),
            "task": len(tasks),
        },
        "index_stats": runtime_index.get("stats", {}),
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
