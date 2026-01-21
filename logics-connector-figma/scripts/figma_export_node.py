#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
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


def _get_json(url: str) -> dict[str, object]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-Figma-Token", _token())
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _download(url: str, out_path: Path) -> None:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export a Figma node as an image (PNG/SVG/PDF).")
    parser.add_argument("--file-key", default=os.environ.get("FIGMA_FILE_KEY"), help="Figma fileKey.")
    parser.add_argument("--node-id", required=True, help="Figma nodeId (e.g. 1744:4185).")
    parser.add_argument("--format", default="png", choices=["png", "svg", "pdf"], help="Export format.")
    parser.add_argument("--scale", type=float, default=2.0, help="Scale (PNG only).")
    parser.add_argument("--out", required=True, help="Output filepath.")
    args = parser.parse_args(argv)

    _find_repo_root(Path.cwd())
    if not args.file_key:
        raise SystemExit("Missing --file-key (or set FIGMA_FILE_KEY).")

    params: dict[str, str] = {"ids": args.node_id, "format": args.format}
    if args.format == "png":
        params["scale"] = str(args.scale)
    query = urllib.parse.urlencode(params)
    data = _get_json(f"{DEFAULT_API_URL}/images/{args.file_key}?{query}")

    images = data.get("images") or {}
    if not isinstance(images, dict):
        raise SystemExit("Unexpected Figma response: missing images dict.")
    url = images.get(args.node_id)
    if not url:
        raise SystemExit(f"No export URL returned for node {args.node_id}.")

    out_path = Path(args.out)
    _download(url, out_path)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

