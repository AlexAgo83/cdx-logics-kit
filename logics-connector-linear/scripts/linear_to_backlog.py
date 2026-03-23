#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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

DEFAULT_API_URL = "https://api.linear.app/graphql"


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



ISSUE_SEARCH = """
query($term: String!, $teamId: String) {
  searchIssues(term: $term, teamId: $teamId, first: 10) {
    nodes {
      identifier
      title
      url
      description
      state { name }
      project { name }
      assignee { name }
      labels { nodes { name } }
    }
  }
}
"""


def _extract_identifier(value: str) -> str:
    value = value.strip()
    if not value:
        raise SystemExit("--issue cannot be empty")
    if "linear.app" in value:
        # https://linear.app/<org>/issue/CIR-42/<slug>
        match = re.search(r"/issue/([A-Z]+-\d+)(?:/|$)", value)
        if match:
            return match.group(1)
    return value


def fetch_issue(issue_ref: str) -> dict[str, object]:
    identifier = _extract_identifier(issue_ref)
    team_id = os.environ.get("LINEAR_API_TEAM_ID") or None
    data = _gql(ISSUE_SEARCH, {"term": identifier, "teamId": team_id})
    nodes = ((data.get("searchIssues") or {}).get("nodes")) or []
    if not nodes:
        raise SystemExit(f"Issue not found: {identifier}")
    if re.match(r"^[A-Z]+-\\d+$", identifier):
        for node in nodes:
            if (node.get("identifier") or "").upper() == identifier.upper():
                return node
    return nodes[0]


def build_backlog_content(
    *,
    title: str,
    doc_ref: str,
    from_version: str,
    understanding: str,
    confidence: str,
    progress: str,
    problem: str,
    notes: str,
) -> str:
    values = build_workflow_doc_values(
        "backlog",
        doc_ref=doc_ref,
        title=title,
        from_version=from_version,
        status="Ready",
        understanding=understanding,
        confidence=confidence,
        progress=progress,
        complexity="Medium",
        theme="General",
    )
    values["PROBLEM_PLACEHOLDER"] = problem.strip()
    values["ACCEPTANCE_PLACEHOLDER"] = "Define acceptance criteria (see Linear description)"
    values["ACCEPTANCE_BLOCK"] = "- AC1: Define acceptance criteria (see Linear description)."
    values["AC_TRACEABILITY_PLACEHOLDER"] = "- AC1 -> Scope: Review imported Linear scope and define proof. Proof: TODO."
    values["PRODUCT_FRAMING_STATUS"] = "Consider"
    values["PRODUCT_FRAMING_SIGNALS"] = "imported issue scope review required"
    values["PRODUCT_FRAMING_ACTION"] = "Review whether the imported Linear scope needs a linked product brief before delivery."
    values["ARCHITECTURE_FRAMING_STATUS"] = "Consider"
    values["ARCHITECTURE_FRAMING_SIGNALS"] = "imported issue technical impact review required"
    values["ARCHITECTURE_FRAMING_ACTION"] = "Review whether the imported Linear issue needs a linked ADR before implementation."
    values["NOTES_PLACEHOLDER"] = notes.rstrip()
    values["MERMAID_BLOCK"] = _render_workflow_mermaid("backlog", title, values)
    return render_workflow_template("backlog", values)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Linear issue into logics/backlog as a new item_### doc.")
    parser.add_argument("--issue", required=True, help="Linear issue identifier (e.g. CIR-42) or issue URL.")
    parser.add_argument("--team-id", default=os.environ.get("LINEAR_API_TEAM_ID"), help="Optional teamId to scope search.")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--progress", default="0%")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())
    if args.team_id:
        os.environ["LINEAR_API_TEAM_ID"] = args.team_id
    issue = fetch_issue(args.issue)

    identifier = issue.get("identifier") or ""
    title = issue.get("title") or ""
    url = issue.get("url") or ""
    state = ((issue.get("state") or {}).get("name")) or ""
    project = ((issue.get("project") or {}).get("name")) or ""
    assignee = ((issue.get("assignee") or {}).get("name")) or ""
    labels = [n.get("name") for n in ((issue.get("labels") or {}).get("nodes") or []) if n.get("name")]
    description = (issue.get("description") or "").rstrip()

    planned = plan_workflow_doc(repo_root, "backlog", title or str(identifier), dry_run=args.dry_run)

    meta_lines = [
        f"Imported from Linear `{identifier}` [{state}].",
        "",
        f"- Linear: {url}",
    ]
    if project:
        meta_lines.append(f"- Project: {project}")
    if assignee:
        meta_lines.append(f"- Assignee: {assignee}")
    if labels:
        meta_lines.append(f"- Labels: {', '.join(labels)}")
    problem = "\n".join(meta_lines)

    notes_parts: list[str] = []
    if description:
        notes_parts.append("## Linear description")
        notes_parts.append(description)
    notes = "\n\n".join(notes_parts)

    content = build_backlog_content(
        title=title or str(identifier),
        doc_ref=planned.ref,
        from_version=args.from_version,
        understanding=args.understanding,
        confidence=args.confidence,
        progress=args.progress,
        problem=problem,
        notes=notes,
    )

    write_workflow_doc(planned.path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
