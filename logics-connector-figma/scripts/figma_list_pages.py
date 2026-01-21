#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


DEFAULT_API_URL = "https://api.figma.com/v1"


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _token() -> str:
    token = os.environ.get("FIGMA_TOKEN_PAT", "").strip()
    if not token:
        raise SystemExit("Missing FIGMA_TOKEN_PAT (Figma Personal Access Token).")
    return token


def _get(url: str) -> dict[str, object]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-Figma-Token", _token())
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="List top-level pages (CANVAS) of a Figma file.")
    parser.add_argument("--file-key", default=os.environ.get("FIGMA_FILE_KEY"), help="Figma fileKey.")
    args = parser.parse_args(argv)

    _find_repo_root(Path.cwd())
    if not args.file_key:
        raise SystemExit("Missing --file-key (or set FIGMA_FILE_KEY).")

    data = _get(f"{DEFAULT_API_URL}/files/{args.file_key}")
    document = data.get("document") or {}
    children = document.get("children") or []

    pages = []
    for child in children:
        if not isinstance(child, dict):
            continue
        if child.get("type") != "CANVAS":
            continue
        pages.append((child.get("id") or "", child.get("name") or ""))

    print(f"FILE: {args.file_key}")
    print(f"PAGES: {len(pages)}")
    for page_id, name in pages:
        print(f"- {name} ({page_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

