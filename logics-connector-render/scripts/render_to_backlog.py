#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _render_api import (
    extract_service_plan,
    extract_service_runtime,
    find_repo_root,
    get_service,
    list_deploys,
)


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


def _format_deploy_lines(deploys: list[dict[str, object]]) -> str:
    if not deploys:
        return "- No deploy returned."
    lines: list[str] = []
    for deploy in deploys:
        deploy_id = str(deploy.get("id") or "")
        status = str(deploy.get("status") or "")
        trigger = str(deploy.get("trigger") or "")
        created_at = str(deploy.get("createdAt") or "")
        commit = deploy.get("commit")
        commit_id = ""
        commit_message = ""
        if isinstance(commit, dict):
            commit_id = str(commit.get("id") or "")
            commit_message = str(commit.get("message") or "").replace("\n", " ").strip()
        commit_summary = commit_id if not commit_message else f"{commit_id} {commit_message}"
        lines.append(f"- `{deploy_id}` [{status}] trigger={trigger} created={created_at} commit={commit_summary or '-'}")
    return "\n".join(lines)


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
    template = _template_path(Path(__file__), "backlog.md").read_text(encoding="utf-8")
    values = {
        "DOC_REF": doc_ref,
        "TITLE": title,
        "FROM_VERSION": from_version,
        "UNDERSTANDING": understanding,
        "CONFIDENCE": confidence,
        "PROGRESS": progress,
        "PROBLEM_PLACEHOLDER": problem.strip(),
        "ACCEPTANCE_PLACEHOLDER": "Define acceptance criteria (see Render context and deploy history).",
        "NOTES_PLACEHOLDER": notes.rstrip(),
    }
    return _render_template(template, values).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Import a Render service context into logics/backlog.")
    parser.add_argument("--service-id", required=True, help="Render service ID.")
    parser.add_argument("--deploy-limit", type=int, default=10, help="Recent deploy count to include in notes.")
    parser.add_argument("--from-version", default="X.X.X")
    parser.add_argument("--understanding", default="??%")
    parser.add_argument("--confidence", default="??%")
    parser.add_argument("--progress", default="0%")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path.cwd())
    backlog_dir = repo_root / "logics" / "backlog"

    if args.deploy_limit <= 0:
        raise SystemExit("--deploy-limit must be > 0")

    service = get_service(args.service_id)
    deploys = list_deploys(args.service_id, limit=args.deploy_limit)

    service_name = str(service.get("name") or args.service_id)
    service_type = str(service.get("type") or "")
    dashboard_url = str(service.get("dashboardUrl") or "")
    suspended = str(service.get("suspended") or "")
    runtime = extract_service_runtime(service) or "-"
    plan = extract_service_plan(service) or "-"

    doc_id = _next_id(backlog_dir, "item")
    slug = _slugify(f"{service_name}_render_service_follow_up")
    filename = f"item_{doc_id:03d}_{slug}.md"
    doc_ref = f"item_{doc_id:03d}_{slug}"
    output_path = backlog_dir / filename
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite: {output_path}")

    problem = "\n".join(
        [
            f"Imported from Render service `{args.service_id}`.",
            "",
            f"- Service: {service_name}",
            f"- Type: {service_type}",
            f"- Runtime: {runtime}",
            f"- Current plan: {plan}",
            f"- Suspended: {suspended}",
            f"- Dashboard: {dashboard_url}",
        ]
    )

    notes_parts = [
        "## Render service payload (excerpt)",
        "```json",
        json.dumps(
            {
                "id": service.get("id"),
                "name": service.get("name"),
                "type": service.get("type"),
                "dashboardUrl": service.get("dashboardUrl"),
                "suspended": service.get("suspended"),
                "serviceDetails": service.get("serviceDetails"),
            },
            indent=2,
            ensure_ascii=True,
        ),
        "```",
        "",
        "## Recent deploys",
        _format_deploy_lines(deploys),
    ]
    notes = "\n".join(notes_parts)

    content = build_backlog_content(
        title=f"Render follow-up: {service_name}",
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
