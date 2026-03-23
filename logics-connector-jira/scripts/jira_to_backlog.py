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



def _extract_issue_key(value: str) -> str:
    value = value.strip()
    if not value:
        raise SystemExit("--issue cannot be empty")
    if "atlassian.net" in value:
        match = re.search(r"/browse/([A-Z][A-Z0-9]+-\\d+)", value)
        if match:
            return match.group(1)
    match = re.search(r"([A-Z][A-Z0-9]+-\\d+)", value)
    if match:
        return match.group(1)
    raise SystemExit(f"Could not parse Jira issue key from: {value}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Jira issue into logics/backlog as a new item_### doc.")
    parser.add_argument("--issue", required=True, help="Jira issue key (e.g. CIR-123) or browse URL.")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--progress", default="0%")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())
    base = _jira_base_url()

    key = _extract_issue_key(args.issue)
    fields = "summary,status,labels,assignee,project,issuetype,description"
    issue_url = f"{base}/rest/api/3/issue/{urllib.parse.quote(key)}?fields={urllib.parse.quote(fields)}&expand=renderedFields"
    data = _get_json(issue_url)

    fields_obj = data.get("fields") or {}
    rendered = data.get("renderedFields") or {}
    summary = fields_obj.get("summary") if isinstance(fields_obj, dict) else ""
    status = ""
    project = ""
    assignee = ""
    issuetype = ""
    labels: list[str] = []
    if isinstance(fields_obj, dict):
        status_obj = fields_obj.get("status") or {}
        status = status_obj.get("name") if isinstance(status_obj, dict) else ""
        project_obj = fields_obj.get("project") or {}
        project = project_obj.get("name") if isinstance(project_obj, dict) else ""
        assignee_obj = fields_obj.get("assignee") or {}
        assignee = assignee_obj.get("displayName") if isinstance(assignee_obj, dict) else ""
        type_obj = fields_obj.get("issuetype") or {}
        issuetype = type_obj.get("name") if isinstance(type_obj, dict) else ""
        labels = [str(x) for x in (fields_obj.get("labels") or []) if isinstance(x, str)]

    rendered_description = ""
    if isinstance(rendered, dict):
        rendered_description = rendered.get("description") if isinstance(rendered.get("description"), str) else ""
    if rendered_description and len(rendered_description) > MAX_HTML_CHARS:
        rendered_description = rendered_description[:MAX_HTML_CHARS] + "\n<!-- truncated -->\n"

    title = summary or key
    planned = plan_workflow_doc(repo_root, "backlog", title, dry_run=args.dry_run)

    browse_url = f"{base}/browse/{key}"
    problem_lines = [
        f"Imported from Jira `{key}` [{status}].",
        "",
        f"- Jira: {browse_url}",
    ]
    if project:
        problem_lines.append(f"- Project: {project}")
    if issuetype:
        problem_lines.append(f"- Type: {issuetype}")
    if assignee:
        problem_lines.append(f"- Assignee: {assignee}")
    if labels:
        problem_lines.append(f"- Labels: {', '.join(labels)}")

    notes_parts: list[str] = []
    if rendered_description:
        notes_parts.append("## Jira description (rendered)")
        notes_parts.append("```html")
        notes_parts.append(rendered_description)
        notes_parts.append("```")
    notes_parts.append("## Links")
    notes_parts.append(f"- Jira: {browse_url}")
    notes = "\n".join(notes_parts)

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
        theme="General",
    )
    values["PROBLEM_PLACEHOLDER"] = "\n".join(problem_lines)
    values["ACCEPTANCE_PLACEHOLDER"] = "Define acceptance criteria (see Jira description)"
    values["ACCEPTANCE_BLOCK"] = "- AC1: Define acceptance criteria (see Jira description)."
    values["AC_TRACEABILITY_PLACEHOLDER"] = "- AC1 -> Scope: Review imported Jira scope and define proof. Proof: TODO."
    values["PRODUCT_FRAMING_STATUS"] = "Consider"
    values["PRODUCT_FRAMING_SIGNALS"] = "imported issue scope review required"
    values["PRODUCT_FRAMING_ACTION"] = "Review whether the imported Jira scope needs a linked product brief before delivery."
    values["ARCHITECTURE_FRAMING_STATUS"] = "Consider"
    values["ARCHITECTURE_FRAMING_SIGNALS"] = "imported issue technical impact review required"
    values["ARCHITECTURE_FRAMING_ACTION"] = "Review whether the imported Jira issue needs a linked ADR before implementation."
    values["REFERENCES_SECTION"] = f"# References\n- `{browse_url}`"
    values["NOTES_PLACEHOLDER"] = notes.rstrip()
    values["MERMAID_BLOCK"] = _render_workflow_mermaid("backlog", title, values)
    content = render_workflow_template("backlog", values)
    write_workflow_doc(planned.path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
