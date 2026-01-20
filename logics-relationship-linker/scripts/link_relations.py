#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


DOC_REF_RE = re.compile(r"\b(req|item|task|spec)_(\d{3})_[a-z0-9_]+\b")


@dataclass(frozen=True)
class Doc:
    ref: str
    path: Path
    title: str
    outgoing: set[str]


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _iter_logics_docs(repo_root: Path) -> list[Path]:
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


def _parse_doc(path: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    ref = path.stem
    title = _parse_title(lines, fallback=ref)
    outgoing = {m.group(0) for m in DOC_REF_RE.finditer(text) if m.group(0) != ref}
    return Doc(ref=ref, path=path, title=title, outgoing=outgoing)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a relationship report between Logics docs.")
    parser.add_argument("--out", default="logics/RELATIONSHIPS.md")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    docs = [_parse_doc(p) for p in _iter_logics_docs(repo_root)]
    by_ref = {d.ref: d for d in docs}

    incoming: dict[str, set[str]] = {d.ref: set() for d in docs}
    for d in docs:
        for ref in d.outgoing:
            if ref in incoming:
                incoming[ref].add(d.ref)

    lines: list[str] = ["# Logics Relationships", ""]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Docs scanned: {len(docs)}")
    lines.append("")

    lines.append("## By document")
    lines.append("")
    for d in sorted(docs, key=lambda x: x.ref):
        rel = d.path.relative_to(repo_root).as_posix()
        lines.append(f"### [{d.ref}]({rel}) - {d.title}")
        lines.append("")
        out_list = sorted(r for r in d.outgoing if r in by_ref)
        in_list = sorted(incoming.get(d.ref, set()))
        lines.append(f"- Outgoing: {', '.join(out_list) if out_list else '_none_'}")
        lines.append(f"- Incoming: {', '.join(in_list) if in_list else '_none_'}")
        lines.append("")

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

