#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _render_api import (
    extract_service_plan,
    extract_service_runtime,
    get_service,
    list_deploys,
)

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
        theme="Infrastructure",
    )
    values["PROBLEM_PLACEHOLDER"] = problem.strip()
    values["ACCEPTANCE_PLACEHOLDER"] = "Define acceptance criteria (see Render context and deploy history)."
    values["ACCEPTANCE_BLOCK"] = "- AC1: Define acceptance criteria from the imported Render context and deploy history."
    values["AC_TRACEABILITY_PLACEHOLDER"] = "- AC1 -> Scope: Review imported Render context and define proof. Proof: TODO."
    values["PRODUCT_FRAMING_STATUS"] = "Not needed"
    values["PRODUCT_FRAMING_SIGNALS"] = "(none detected)"
    values["PRODUCT_FRAMING_ACTION"] = "No product brief follow-up is expected from this imported Render context."
    values["ARCHITECTURE_FRAMING_STATUS"] = "Required"
    values["ARCHITECTURE_FRAMING_SIGNALS"] = "runtime and deployment context imported from Render"
    values["ARCHITECTURE_FRAMING_ACTION"] = "Create or link an ADR before irreversible infrastructure changes start."
    values["NOTES_PLACEHOLDER"] = notes.rstrip()
    values["MERMAID_BLOCK"] = _render_workflow_mermaid("backlog", title, values)
    return render_workflow_template("backlog", values)


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

    title = f"Render follow-up: {service_name}"
    planned = plan_workflow_doc(repo_root, "backlog", title, dry_run=args.dry_run)

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
        title=title,
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
