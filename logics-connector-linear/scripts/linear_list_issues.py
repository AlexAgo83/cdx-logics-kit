#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_API_URL = "https://api.linear.app/graphql"


@dataclass(frozen=True)
class LinearIssue:
    identifier: str
    title: str
    url: str
    state: str


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def _api_url() -> str:
    return os.environ.get("LINEAR_API_URL", DEFAULT_API_URL)


def _api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing LINEAR_API_KEY (Linear Personal API key).")
    return key


def _gql(query: str, variables: dict[str, object] | None = None) -> dict[str, object]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(_api_url(), data=payload, method="POST")
    req.add_header("Authorization", _api_key())
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if data.get("errors"):
        raise SystemExit(data["errors"][0].get("message", str(data["errors"][0])))
    return data["data"]


QUERY = """
query($teamId: String!, $after: String, $first: Int!) {
  team(id: $teamId) {
    name
    issues(first: $first, after: $after) {
      nodes {
        identifier
        title
        url
        state { name }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def list_issues(team_id: str, limit: int) -> tuple[str, list[LinearIssue]]:
    repo_root = _find_repo_root(Path.cwd())
    del repo_root  # only used for validation (run from project repo)

    issues: list[LinearIssue] = []
    after: str | None = None
    team_name: str | None = None

    while len(issues) < limit:
        first = min(100, limit - len(issues))
        data = _gql(QUERY, {"teamId": team_id, "after": after, "first": first})
        team = data.get("team") or {}
        if not team:
            raise SystemExit("Team not found (invalid teamId or insufficient permissions).")
        team_name = team.get("name") or team_name

        conn = team.get("issues") or {}
        nodes = conn.get("nodes") or []
        for node in nodes:
            state = (node.get("state") or {}).get("name") or ""
            issues.append(
                LinearIssue(
                    identifier=node.get("identifier") or "",
                    title=node.get("title") or "",
                    url=node.get("url") or "",
                    state=state,
                )
            )

        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")

    return (team_name or "Unknown team"), issues


def _write_out(path: str | None, text: str) -> None:
    if not path or path == "-":
        print(text, end="")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(f"Wrote {path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="List Linear issues for a team (GraphQL).")
    parser.add_argument("--team-id", default=os.environ.get("LINEAR_API_TEAM_ID"), help="Linear teamId (UUID).")
    parser.add_argument("--limit", type=int, default=50, help="Max number of issues to list.")
    parser.add_argument("--out", help="Write output to a file (use '-' or omit for stdout).")
    args = parser.parse_args(argv)

    if not args.team_id:
        raise SystemExit("Missing --team-id (or set LINEAR_API_TEAM_ID).")
    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    team_name, issues = list_issues(args.team_id, args.limit)
    lines = [f"# Linear issues – {team_name}", f"Total: {len(issues)}", ""]
    for issue in issues:
        lines.append(f"- {issue.identifier} [{issue.state}] {issue.title} — {issue.url}")
    _write_out(args.out, "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

