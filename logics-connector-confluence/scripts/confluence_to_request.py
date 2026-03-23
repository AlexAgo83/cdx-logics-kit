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

MAX_HTML_CHARS = 20000


def _confluence_domain() -> str:
    domain = os.environ.get("CONFLUENCE_DOMAIN", "").strip().rstrip("/")
    if not domain:
        domain = os.environ.get("CONFLUENCE_DOMAINE", "").strip().rstrip("/")
    if not domain:
        raise SystemExit(
            "Missing CONFLUENCE_DOMAIN (or legacy CONFLUENCE_DOMAINE), "
            "e.g. https://<domain>.atlassian.net/wiki."
        )
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



def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Confluence page into logics/request as a new req_### doc.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID.")
    parser.add_argument("--title", help="Override request title (defaults to Confluence page title).")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())

    page_id = str(args.page_id).strip()
    if not page_id.isdigit():
        raise SystemExit("--page-id must be numeric.")

    url = f"{_confluence_domain()}/rest/api/content/{page_id}?expand=body.storage,version,_links"
    data = _get_json(url)

    page_title = (data.get("title") or "").strip()
    title = (args.title or page_title or f"Confluence page {page_id}").strip()
    links = data.get("_links") or {}
    webui = links.get("webui") if isinstance(links, dict) else None
    page_url = f"{_confluence_domain()}{webui}" if webui else ""

    storage = (((data.get("body") or {}).get("storage")) or {}) if isinstance(data.get("body"), dict) else {}
    html = storage.get("value") if isinstance(storage, dict) else None
    html = html if isinstance(html, str) else ""
    html = html.strip()
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n<!-- truncated -->\n"

    planned = plan_workflow_doc(repo_root, "request", title, dry_run=args.dry_run)

    context_parts = [
        f"Imported from Confluence page `{page_id}`.",
    ]
    if page_url:
        context_parts.append(f"- Confluence: {page_url}")
    context_parts.append("- Companion docs review: assess whether a product brief or ADR is needed before promotion.")
    context_parts.append("")
    if html:
        context_parts.append("```html")
        context_parts.append(html)
        context_parts.append("```")
    context = "\n".join(context_parts)

    values = build_workflow_doc_values(
        "request",
        doc_ref=planned.ref,
        title=title,
        from_version=args.from_version,
        status="Draft",
        understanding=args.understanding,
        confidence=args.confidence,
        complexity="Medium",
        theme="General",
    )
    values["NEEDS_PLACEHOLDER"] = f"Frame the imported Confluence source and turn it into an actionable request for {title}."
    values["CONTEXT_PLACEHOLDER"] = context
    values["ACCEPTANCE_PLACEHOLDER"] = "AC1: Define an objective acceptance check from the imported Confluence source."
    values["REFERENCES_SECTION"] = f"# References\n- `{page_url}`" if page_url else ""
    values["MERMAID_BLOCK"] = _render_workflow_mermaid("request", title, values)
    content = render_workflow_template("request", values)
    write_workflow_doc(planned.path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
