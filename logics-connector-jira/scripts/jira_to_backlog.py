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

    repo_root = _find_repo_root(Path.cwd())
    backlog_dir = repo_root / "logics" / "backlog"
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
    doc_id = _next_id(backlog_dir, "item")
    slug = _slugify(title)
    filename = f"item_{doc_id:03d}_{slug}.md"
    doc_ref = f"item_{doc_id:03d}_{slug}"
    output_path = backlog_dir / filename
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite: {output_path}")

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

    template = _template_path(Path(__file__), "backlog.md").read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": args.from_version,
        "UNDERSTANDING": args.understanding,
        "CONFIDENCE": args.confidence,
        "PROGRESS": args.progress,
        "PROBLEM_PLACEHOLDER": "\n".join(problem_lines),
        "ACCEPTANCE_PLACEHOLDER": "Define acceptance criteria (see Jira description)",
        "NOTES_PLACEHOLDER": notes.rstrip(),
    }
    content = _render_template(template, values).rstrip() + "\n"
    _write(output_path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

