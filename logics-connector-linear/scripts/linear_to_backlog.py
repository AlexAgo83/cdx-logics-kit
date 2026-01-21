#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


DEFAULT_API_URL = "https://api.linear.app/graphql"


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
    repo_root: Path,
    title: str,
    doc_ref: str,
    from_version: str,
    understanding: str,
    confidence: str,
    progress: str,
    problem: str,
    notes: str,
) -> str:
    template = _template_path(Path(__file__), "backlog.md").read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": from_version,
        "UNDERSTANDING": understanding,
        "CONFIDENCE": confidence,
        "PROGRESS": progress,
        "PROBLEM_PLACEHOLDER": problem.strip(),
        "ACCEPTANCE_PLACEHOLDER": "Define acceptance criteria (see Linear description)",
        "NOTES_PLACEHOLDER": notes.rstrip(),
    }
    return _render_template(template, values).rstrip() + "\n"


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

    repo_root = _find_repo_root(Path.cwd())
    backlog_dir = repo_root / "logics" / "backlog"
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

    doc_id = _next_id(backlog_dir, "item")
    slug = _slugify(title or identifier)
    filename = f"item_{doc_id:03d}_{slug}.md"
    doc_ref = f"item_{doc_id:03d}_{slug}"
    output_path = backlog_dir / filename
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite: {output_path}")

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
        repo_root=repo_root,
        title=title or str(identifier),
        doc_ref=doc_ref,
        from_version=args.from_version,
        understanding=args.understanding,
        confidence=args.confidence,
        progress=args.progress,
        problem=problem,
        notes=notes,
    )

    _write(output_path, content, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
