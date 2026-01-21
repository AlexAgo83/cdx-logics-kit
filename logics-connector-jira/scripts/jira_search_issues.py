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


def _jira_base_url() -> str:
    base = os.environ.get("JIRA_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise SystemExit("Missing JIRA_BASE_URL (e.g. https://<domain>.atlassian.net).")
    return base


def _auth_header() -> str:
    email = os.environ.get("JIRA_EMAIL", "").strip()
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not email or not token:
        raise SystemExit("Missing JIRA_EMAIL or JIRA_API_TOKEN.")
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
    parser = argparse.ArgumentParser(description="Search Jira issues via JQL (REST API v3).")
    parser.add_argument("--jql", default=os.environ.get("JIRA_DEFAULT_JQL"), help="JQL query.")
    parser.add_argument("--limit", type=int, default=20, help="Max issues to return.")
    args = parser.parse_args(argv)

    _find_repo_root(Path.cwd())
    if not args.jql:
        raise SystemExit("Missing --jql (or set JIRA_DEFAULT_JQL).")
    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    base = _jira_base_url()
    start_at = 0
    issues_out: list[dict[str, object]] = []
    fields = "summary,status"

    while len(issues_out) < args.limit:
        max_results = min(100, args.limit - len(issues_out))
        query = urllib.parse.urlencode(
            {
                "jql": args.jql,
                "startAt": str(start_at),
                "maxResults": str(max_results),
                "fields": fields,
            }
        )
        data = _get_json(f"{base}/rest/api/3/search?{query}")
        issues = data.get("issues") or []
        if not isinstance(issues, list) or not issues:
            break
        issues_out.extend([i for i in issues if isinstance(i, dict)])
        start_at += len(issues)
        if len(issues) < max_results:
            break

    print(f"JQL: {args.jql}")
    print(f"RESULTS: {len(issues_out)}")
    for issue in issues_out:
        key = issue.get("key") or ""
        fields_obj = issue.get("fields") or {}
        summary = fields_obj.get("summary") if isinstance(fields_obj, dict) else ""
        status = ""
        if isinstance(fields_obj, dict):
            status_obj = fields_obj.get("status") or {}
            status = status_obj.get("name") if isinstance(status_obj, dict) else ""
        browse = f"{base}/browse/{key}" if key else ""
        print(f"- {key} [{status}] {summary} {browse}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

