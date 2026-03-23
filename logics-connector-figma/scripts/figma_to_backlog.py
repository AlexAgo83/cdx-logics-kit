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

FLOW_MANAGER_SCRIPTS = Path(__file__).resolve().parents[2] / "logics-flow-manager" / "scripts"
if str(FLOW_MANAGER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FLOW_MANAGER_SCRIPTS))

from logics_flow_support import (  # noqa: E402
    _render_workflow_mermaid,
    build_workflow_doc_values,
    find_repo_root,
    plan_workflow_doc,
    render_workflow_template,
    write_workflow_doc,
)

DEFAULT_API_URL = "https://api.figma.com/v1"


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

    repo_root = find_repo_root(Path.cwd())
    if not args.file_key:
        raise SystemExit("Missing --file-key (or set FIGMA_FILE_KEY).")

    node_name = _fetch_node_name(args.file_key, args.node_id)
    title = args.title or node_name or f"Figma node {args.node_id}"
    figma_url = _figma_url(args.file_key, args.node_id)

    planned = plan_workflow_doc(repo_root, "backlog", title, dry_run=args.dry_run)

    exported_path: Path | None = None
    if args.export:
        image_dir = Path(args.image_out_dir)
        exported_path = image_dir / f"{planned.ref}_{args.node_id.replace(':', '_')}.png"
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

    values = build_workflow_doc_values(
        "backlog",
        doc_ref=planned.ref,
        title=title,
        from_version=args.from_version,
        status="Ready",
        understanding=args.understanding,
        confidence=args.confidence,
        progress=args.progress,
        complexity="Medium",
        theme="UI",
    )
    values["PROBLEM_PLACEHOLDER"] = "\n".join(problem_lines)
    values["ACCEPTANCE_PLACEHOLDER"] = "Define acceptance criteria"
    values["ACCEPTANCE_BLOCK"] = "- AC1: Define acceptance criteria from the imported Figma design."
    values["AC_TRACEABILITY_PLACEHOLDER"] = "- AC1 -> Scope: Review imported design intent and define proof. Proof: TODO."
    values["PRODUCT_FRAMING_STATUS"] = "Required"
    values["PRODUCT_FRAMING_SIGNALS"] = "imported design artifact"
    values["PRODUCT_FRAMING_ACTION"] = "Create or link a product brief that captures the design intent before implementation."
    values["ARCHITECTURE_FRAMING_STATUS"] = "Consider"
    values["ARCHITECTURE_FRAMING_SIGNALS"] = "implementation impact review required"
    values["ARCHITECTURE_FRAMING_ACTION"] = "Review whether a linked ADR is needed before implementation details diverge from the design."
    values["REFERENCES_SECTION"] = f"# References\n- `{figma_url}`"
    values["NOTES_PLACEHOLDER"] = "\n".join(notes_lines)
    values["MERMAID_BLOCK"] = _render_workflow_mermaid("backlog", title, values)
    content = render_workflow_template("backlog", values)
    write_workflow_doc(planned.path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
