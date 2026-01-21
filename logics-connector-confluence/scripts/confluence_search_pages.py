#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Search Confluence pages via CQL.")
    parser.add_argument("--cql", required=True, help="Confluence CQL query (URL encoded automatically).")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    _find_repo_root(Path.cwd())
    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    query = urllib.parse.urlencode({"cql": args.cql, "limit": str(args.limit)})
    url = f"{_confluence_domain()}/rest/api/content/search?{query}"
    data = _get_json(url)
    results = data.get("results") or []
    if not isinstance(results, list):
        raise SystemExit("Unexpected Confluence response: results is not a list.")

    print(f"CQL: {args.cql}")
    print(f"RESULTS: {len(results)}")
    for r in results:
        if not isinstance(r, dict):
            continue
        page_id = r.get("id") or ""
        title = r.get("title") or ""
        links = r.get("_links") or {}
        webui = links.get("webui") if isinstance(links, dict) else None
        page_url = f"{_confluence_domain()}{webui}" if webui else ""
        print(f"- {page_id} {title} {page_url}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

