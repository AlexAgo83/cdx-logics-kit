#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
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


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "untitled"


def _next_id(directory: Path, prefix: str) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)_.*\.md$")
    max_id = -1
    for file_path in directory.glob(f"{prefix}_*.md"):
        match = pattern.match(file_path.name)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
    return max_id + 1


def _template_path(script_path: Path, template_name: str) -> Path:
    kit_root = script_path.resolve().parents[2]  # .../logics/skills
    return kit_root / "logics-flow-manager" / "assets" / "templates" / template_name


def _render_template(template_text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", repl, template_text)


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        preview = content if len(content) <= 2000 else content[:2000] + "\n...\n"
        print(f"[dry-run] would write: {path}")
        print(preview)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path}")


def _figma_url(file_key: str, node_id: str) -> str:
    return f"https://www.figma.com/file/{file_key}?node-id={urllib.parse.quote(node_id, safe='')}"


def _fetch_node_name(file_key: str, node_id: str) -> str | None:
    params = urllib.parse.urlencode({"ids": node_id})
    data = _get_json(f"{DEFAULT_API_URL}/files/{file_key}/nodes?{params}")
    nodes = data.get("nodes") or {}
    if not isinstance(nodes, dict):
        return None
    node = nodes.get(node_id) or {}
    document = (node.get("document") or {}) if isinstance(node, dict) else {}
    name = document.get("name") if isinstance(document, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _export_node(file_key: str, node_id: str, out_path: Path, scale: float) -> None:
    params: dict[str, str] = {"ids": node_id, "format": "png", "scale": str(scale)}
    query = urllib.parse.urlencode(params)
    data = _get_json(f"{DEFAULT_API_URL}/images/{file_key}?{query}")
    images = data.get("images") or {}
    if not isinstance(images, dict):
        raise SystemExit("Unexpected Figma response: missing images dict.")
    url = images.get(node_id)
    if not url:
        raise SystemExit(f"No export URL returned for node {node_id}.")
    _download(url, out_path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Figma node reference into logics/backlog as a new item_### doc.")
    parser.add_argument("--file-key", default=os.environ.get("FIGMA_FILE_KEY"), help="Figma fileKey.")
    parser.add_argument("--node-id", required=True, help="Figma nodeId (e.g. 1744:4185).")
    parser.add_argument("--title", help="Override backlog item title (defaults to node name).")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--progress", default="0%")
    parser.add_argument("--export", action="store_true", help="Export node image (PNG) to disk.")
    parser.add_argument("--image-out-dir", default="output/figma", help="Directory for exported PNGs (if --export).")
    parser.add_argument("--scale", type=float, default=2.0, help="PNG export scale (if --export).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    if not args.file_key:
        raise SystemExit("Missing --file-key (or set FIGMA_FILE_KEY).")

    node_name = _fetch_node_name(args.file_key, args.node_id)
    title = args.title or node_name or f"Figma node {args.node_id}"
    figma_url = _figma_url(args.file_key, args.node_id)

    backlog_dir = repo_root / "logics" / "backlog"
    doc_id = _next_id(backlog_dir, "item")
    slug = _slugify(title)
    filename = f"item_{doc_id:03d}_{slug}.md"
    doc_ref = f"item_{doc_id:03d}_{slug}"
    output_path = backlog_dir / filename
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite: {output_path}")

    exported_path: Path | None = None
    if args.export:
        image_dir = Path(args.image_out_dir)
        exported_path = image_dir / f"{doc_ref}_{args.node_id.replace(':','_')}.png"
        if args.dry_run:
            print(f"[dry-run] would export PNG: {exported_path}")
        else:
            _export_node(args.file_key, args.node_id, exported_path, args.scale)

    problem_lines = [
        "Imported from Figma.",
        "",
        f"- Figma: {figma_url}",
    ]
    if exported_path is not None:
        problem_lines.append(f"- Export: `{exported_path}`")

    notes_lines = [
        "## Design context",
        "- Add product intent, expected UI behavior, and edge cases.",
        "",
        "## Links",
        f"- Figma: {figma_url}",
    ]
    if exported_path is not None:
        notes_lines.append(f"- Export: `{exported_path}`")

    template = _template_path(Path(__file__), "backlog.md").read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "PROBLEM_PLACEHOLDER": "\n".join(problem_lines),
        "ACCEPTANCE_PLACEHOLDER": "Define acceptance criteria",
        "NOTES_PLACEHOLDER": "\n".join(notes_lines),
    }

    content = _render_template(template, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

