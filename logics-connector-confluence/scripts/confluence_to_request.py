#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


MAX_HTML_CHARS = 20000


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _confluence_domain() -> str:
    domain = os.environ.get("CONFLUENCE_DOMAINE", "").strip().rstrip("/")
    if not domain:
        raise SystemExit("Missing CONFLUENCE_DOMAINE (e.g. https://<domain>.atlassian.net/wiki).")
    return domain


def _auth_header() -> str:
    email = os.environ.get("CONFLUENCE_EMAIL", "").strip()
    token = os.environ.get("CONFLUENCE_API_TOKEN", "").strip()
    if not email or not token:
        raise SystemExit("Missing CONFLUENCE_EMAIL or CONFLUENCE_API_TOKEN.")
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _get_json(url: str) -> dict[str, object]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", _auth_header())
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Confluence page into logics/request as a new req_### doc.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID.")
    parser.add_argument("--title", help="Override request title (defaults to Confluence page title).")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    request_dir = repo_root / "logics" / "request"

    page_id = str(args.page_id).strip()
    if not page_id.isdigit():
        raise SystemExit("--page-id must be numeric.")

    url = f"{_confluence_domain()}/rest/api/content/{page_id}?expand=body.storage,version,_links"
    data = _get_json(url)

    page_title = (data.get("title") or "").strip()
    title = (args.title or page_title or f"Confluence page {page_id}").strip()
    slug = _slugify(title)

    links = data.get("_links") or {}
    webui = links.get("webui") if isinstance(links, dict) else None
    page_url = f"{_confluence_domain()}{webui}" if webui else ""

    storage = (((data.get("body") or {}).get("storage")) or {}) if isinstance(data.get("body"), dict) else {}
    html = storage.get("value") if isinstance(storage, dict) else None
    html = html if isinstance(html, str) else ""
    html = html.strip()
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n<!-- truncated -->\n"

    doc_id = _next_id(request_dir, "req")
    filename = f"req_{doc_id:03d}_{slug}.md"
    doc_ref = f"req_{doc_id:03d}_{slug}"
    output_path = request_dir / filename
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite: {output_path}")

    context_parts = [
        f"Imported from Confluence page `{page_id}`.",
    ]
    if page_url:
        context_parts.append(f"- Confluence: {page_url}")
    context_parts.append("")
    if html:
        context_parts.append("```html")
        context_parts.append(html)
        context_parts.append("```")
    context = "\n".join(context_parts)

    template = _template_path(Path(__file__), "request.md").read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "NEEDS_PLACEHOLDER": "Describe the need",
        "CONTEXT_PLACEHOLDER": context,
    }
    content = _render_template(template, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

