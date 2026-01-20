#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Doc:
    path: Path
    ref: str
    title: str
    text: str


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


def _parse_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("## "):
            match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
            return line.removeprefix("## ").strip()
    return fallback


def _normalize_title(title: str) -> str:
    return " ".join(WORD_RE.findall(title.lower()))


def _score(a: Doc, b: Doc) -> float:
    ta = _normalize_title(a.title)
    tb = _normalize_title(b.title)
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Find potential duplicate Logics docs by title similarity.")
    parser.add_argument("--min-score", type=float, default=0.6)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    docs: list[Doc] = []
    for path in _iter_docs(repo_root):
        text = path.read_text(encoding="utf-8")
        ref = path.stem
        title = _parse_title(text, fallback=ref)
        docs.append(Doc(path=path, ref=ref, title=title, text=text))

    pairs: list[tuple[float, Doc, Doc]] = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            s = _score(docs[i], docs[j])
            if s >= args.min_score:
                pairs.append((s, docs[i], docs[j]))

    pairs.sort(key=lambda x: x[0], reverse=True)
    if not pairs:
        print("No duplicate candidates found.")
        return 0

    print(f"Duplicate candidates (min-score={args.min_score}):")
    for s, a, b in pairs[: args.top]:
        ar = a.path.relative_to(repo_root).as_posix()
        br = b.path.relative_to(repo_root).as_posix()
        print(f"- score={s:.2f} :: {a.ref} ({ar}) <-> {b.ref} ({br})")
        print(f"  - {a.title}")
        print(f"  - {b.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

