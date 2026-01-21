#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


WORD_RE = re.compile(r"[a-z0-9]+")
DOC_META_RE = re.compile(r"^(req|item|task|spec)_(\d{3})_([a-z0-9_]+)$")


@dataclass(frozen=True)
class Doc:
    path: Path
    ref: str
    kind: str
    slug: str
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

def _normalize_content(text: str, max_chars: int) -> str:
    snippet = text[:max_chars].lower()
    return " ".join(WORD_RE.findall(snippet))


def _token_set(value: str) -> set[str]:
    return set(value.split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _score(a: Doc, b: Doc) -> float:
    ta = _normalize_title(a.title)
    tb = _normalize_title(b.title)
    if not ta or not tb:
        return 0.0
    title_score = SequenceMatcher(None, ta, tb).ratio()

    ca = _token_set(_normalize_content(a.text, max_chars=5000))
    cb = _token_set(_normalize_content(b.text, max_chars=5000))
    content_score = _jaccard(ca, cb)

    # Weighted, best-effort score.
    return 0.75 * title_score + 0.25 * content_score


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Find potential duplicate Logics docs by title similarity.")
    parser.add_argument("--min-score", type=float, default=0.6)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument(
        "--include-related",
        action="store_true",
        help="Include request/backlog/task/spec docs that share the same slug (often a normal chain).",
    )
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    docs: list[Doc] = []
    for path in _iter_docs(repo_root):
        text = path.read_text(encoding="utf-8")
        ref = path.stem
        match = DOC_META_RE.match(ref)
        kind = match.group(1) if match else "unknown"
        slug = match.group(3) if match else ""
        title = _parse_title(text, fallback=ref)
        docs.append(Doc(path=path, ref=ref, kind=kind, slug=slug, title=title, text=text))

    pairs: list[tuple[float, Doc, Doc]] = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if not args.include_related and docs[i].slug and docs[i].slug == docs[j].slug:
                continue
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
