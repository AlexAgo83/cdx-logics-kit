#!/usr/bin/env python3
from __future__ import annotations

from logics_flow_doc_commands import *  # noqa: F401,F403

def cmd_finish_task(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{DOC_KINDS['task'].prefix}_"):
        raise SystemExit(f"Expected a `{DOC_KINDS['task'].prefix}_...` task file. Got: {source_path.name}")

    close_args = argparse.Namespace(kind="task", source=args.source, dry_run=args.dry_run)
    cmd_close(close_args)
    _mark_section_checkboxes_done(source_path, "Definition of Done (DoD)", args.dry_run)
    _record_finished_task_follow_up(repo_root, source_path, args.dry_run)

    if args.dry_run:
        print("Dry run: skipped post-close verification.")
        return

    issues = _verify_finished_task_chain(repo_root, source_path)
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        raise SystemExit(f"Finish verification failed:\n{details}")

    print(f"Finish verification: OK for {source_path.relative_to(repo_root)}")
    return {
        "command": "finish",
        "kind": "task",
        "source": _rel(repo_root, source_path),
        "dry_run": args.dry_run,
    }


def _add_common_doc_args(parser: argparse.ArgumentParser, kind: str) -> None:
    parser.add_argument("--from-version")
    parser.add_argument("--understanding", default="90%")
    parser.add_argument("--confidence", default="85%")
    parser.add_argument("--status", default=STATUS_BY_KIND_DEFAULT[kind])
    parser.add_argument("--complexity", default="Medium", choices=ALLOWED_COMPLEXITIES)
    parser.add_argument("--theme", default="General")
    if DOC_KINDS[kind].include_progress:
        parser.add_argument("--progress", default="0%")
    else:
        parser.add_argument("--progress", default="")
    if kind in {"backlog", "task"}:
        parser.add_argument("--auto-create-product-brief", action="store_true")
        parser.add_argument("--auto-create-adr", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_flow.py",
        description="Create/promote/close/finish Logics docs with consistent IDs, templates, and workflow transitions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new Logics doc from a template.")
    new_sub = new_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        kind_parser = new_sub.add_parser(kind, help=f"Create a new {kind} doc.")
        kind_parser.add_argument("--title", required=True)
        kind_parser.add_argument("--slug", help="Override slug derived from the title.")
        _add_common_doc_args(kind_parser, kind)
        kind_parser.set_defaults(func=cmd_new)

    promote_parser = sub.add_parser("promote", help="Promote between Logics stages.")
    promote_sub = promote_parser.add_subparsers(dest="promotion", required=True)

    r2b = promote_sub.add_parser(
        "request-to-backlog",
        help="Create a backlog slice from an already atomic request. Prefer `split request` for broad requests.",
    )
    r2b.add_argument("source")
    _add_common_doc_args(r2b, "backlog")
    r2b.set_defaults(func=cmd_promote_request_to_backlog)

    b2t = promote_sub.add_parser("backlog-to-task", help="Create a task from a backlog item.")
    b2t.add_argument("source")
    _add_common_doc_args(b2t, "task")
    b2t.set_defaults(func=cmd_promote_backlog_to_task)

    split_parser = sub.add_parser("split", help="Split a request/backlog doc into multiple executable children.")
    split_sub = split_parser.add_subparsers(dest="split_kind", required=True)

    split_request = split_sub.add_parser("request", help="Split a request into multiple backlog items.")
    split_request.add_argument("source")
    split_request.add_argument(
        "--title",
        action="append",
        required=True,
        help="Child backlog item title. Repeat the flag for multiple bounded slices so the request coverage does not collapse into one or two oversized items.",
    )
    split_request.add_argument("--allow-extra-slices", action="store_true", help="Override the repo split policy when more child slices are explicitly justified.")
    _add_common_doc_args(split_request, "backlog")
    split_request.set_defaults(func=cmd_split_request)

    split_backlog = split_sub.add_parser("backlog", help="Split a backlog item into multiple tasks.")
    split_backlog.add_argument("source")
    split_backlog.add_argument("--title", action="append", required=True, help="Child task title. Repeat the flag for multiple children, keeping the split to the minimum coherent slice count.")
    split_backlog.add_argument("--allow-extra-slices", action="store_true", help="Override the repo split policy when more child slices are explicitly justified.")
    _add_common_doc_args(split_backlog, "task")
    split_backlog.set_defaults(func=cmd_split_backlog)

    close_parser = sub.add_parser("close", help="Close a request/backlog/task and propagate transitions.")
    close_sub = close_parser.add_subparsers(dest="kind", required=True)
    for kind in DOC_KINDS:
        close_kind = close_sub.add_parser(kind, help=f"Close a {kind} doc.")
        close_kind.add_argument("source")
        close_kind.add_argument("--format", choices=("text", "json"), default="text")
        close_kind.add_argument("--dry-run", action="store_true")
        close_kind.set_defaults(func=cmd_close)

    finish_parser = sub.add_parser(
        "finish",
        help="Finish a completed Logics doc using the recommended workflow guardrails.",
    )
    finish_sub = finish_parser.add_subparsers(dest="finish_kind", required=True)
    finish_task = finish_sub.add_parser(
        "task",
        help="Close a task, propagate task -> backlog -> request transitions, and verify the linked chain.",
    )
    finish_task.add_argument("source")
    finish_task.add_argument("--format", choices=("text", "json"), default="text")
    finish_task.add_argument("--dry-run", action="store_true")
    finish_task.set_defaults(func=cmd_finish_task)

    assist_parser = sub.add_parser(
        "assist",
        help="Run bounded hybrid assist flows that can prefer Ollama locally and degrade cleanly otherwise.",
    )
    assist_sub = assist_parser.add_subparsers(dest="assist_kind", required=True)

    assist_runtime = assist_sub.add_parser(
        "runtime-status",
        help="Report the hybrid assist backend, bridge, and degraded-mode status for this repository.",
    )
    assist_runtime.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    assist_runtime.add_argument("--model-profile")
    assist_runtime.add_argument("--model")
    assist_runtime.add_argument("--ollama-host")
    assist_runtime.add_argument("--timeout", type=float)
    assist_runtime.add_argument("--out", help="Write the JSON status payload to this relative path.")
    assist_runtime.add_argument("--format", choices=("text", "json"), default="text")
    assist_runtime.add_argument("--dry-run", action="store_true")
    assist_runtime.set_defaults(func=cmd_assist_runtime_status)

    assist_context = assist_sub.add_parser(
        "context",
        help="Build a shared hybrid assist context bundle for a named flow.",
    )
    assist_context.add_argument(
        "flow_name",
        choices=tuple(sorted(build_shared_hybrid_contract()["flows"].keys())),
        help="Hybrid assist flow name.",
    )
    assist_context.add_argument("ref", nargs="?", help="Optional workflow ref for flows that operate on a target doc.")
    assist_context.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    assist_context.add_argument("--profile", choices=("tiny", "normal", "deep"))
    assist_context.add_argument("--include-graph", action="store_true", default=None)
    assist_context.add_argument("--include-registry", action="store_true", default=None)
    assist_context.add_argument("--include-doctor", action="store_true", default=None)
    assist_context.add_argument("--out", help="Write the JSON context bundle to this relative path.")
    assist_context.add_argument("--format", choices=("text", "json"), default="text")
    assist_context.add_argument("--dry-run", action="store_true")
    assist_context.set_defaults(func=cmd_assist_context)

    assist_roi = assist_sub.add_parser(
        "roi-report",
        help="Aggregate hybrid assist measurement and audit logs into a stable ROI dispatch report.",
    )
    assist_roi.add_argument("--audit-log")
    assist_roi.add_argument("--measurement-log")
    assist_roi.add_argument("--recent-limit", type=int, default=DEFAULT_HYBRID_ROI_RECENT_LIMIT)
    assist_roi.add_argument("--window-days", type=int, default=DEFAULT_HYBRID_ROI_WINDOW_DAYS)
    assist_roi.add_argument("--out", help="Write the JSON report payload to this relative path.")
    assist_roi.add_argument("--format", choices=("text", "json"), default="text")
    assist_roi.add_argument("--dry-run", action="store_true")
    assist_roi.set_defaults(func=cmd_assist_roi_report)

    assist_run = assist_sub.add_parser(
        "run",
        help="Run a shared hybrid assist flow and return structured output plus backend provenance.",
    )
    assist_run.add_argument(
        "flow_name",
        choices=tuple(sorted(build_shared_hybrid_contract()["flows"].keys())),
        help="Hybrid assist flow name.",
    )
    assist_run.add_argument("ref", nargs="?", help="Optional workflow ref for flows that operate on a target doc.")
    assist_run.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    assist_run.add_argument("--model-profile")
    assist_run.add_argument("--model")
    assist_run.add_argument("--ollama-host")
    assist_run.add_argument("--timeout", type=float)
    assist_run.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    assist_run.add_argument("--profile", choices=("tiny", "normal", "deep"))
    assist_run.add_argument("--include-graph", action="store_true", default=None)
    assist_run.add_argument("--include-registry", action="store_true", default=None)
    assist_run.add_argument("--include-doctor", action="store_true", default=None)
    assist_run.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    assist_run.add_argument("--audit-log")
    assist_run.add_argument("--measurement-log")
    assist_run.add_argument("--intent", help="Short operator intent for request-draft authoring proposals.")
    assist_run.add_argument("--format", choices=("text", "json"), default="text")
    assist_run.add_argument("--dry-run", action="store_true")
    assist_run.set_defaults(func=cmd_assist_run)

    def add_assist_alias(name: str, flow_name: str, help_text: str, *, takes_ref: bool) -> argparse.ArgumentParser:
        alias = assist_sub.add_parser(name, help=help_text)
        if takes_ref:
            alias.add_argument("ref", help="Workflow ref for the assist flow target.")
        alias.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
        alias.add_argument("--model-profile")
        alias.add_argument("--model")
        alias.add_argument("--ollama-host")
        alias.add_argument("--timeout", type=float)
        alias.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
        alias.add_argument("--profile", choices=("tiny", "normal", "deep"))
        alias.add_argument("--include-graph", action="store_true", default=None)
        alias.add_argument("--include-registry", action="store_true", default=None)
        alias.add_argument("--include-doctor", action="store_true", default=None)
        alias.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
        alias.add_argument("--audit-log")
        alias.add_argument("--measurement-log")
        alias.add_argument("--format", choices=("text", "json"), default="text")
        alias.add_argument("--dry-run", action="store_true")
        alias.set_defaults(func=cmd_assist_run, flow_name=flow_name)
        return alias

    add_assist_alias("summarize-pr", "pr-summary", "Generate a bounded PR summary.", takes_ref=False)
    add_assist_alias("summarize-changelog", "changelog-summary", "Generate a bounded changelog summary.", takes_ref=False)
    add_assist_alias("summarize-validation", "validation-summary", "Summarize shared validation results.", takes_ref=False)
    add_assist_alias("next-step", "next-step", "Suggest the next bounded workflow action for a target doc.", takes_ref=True)
    request_draft_alias = add_assist_alias("request-draft", "request-draft", "Draft bounded request Needs and Context blocks.", takes_ref=False)
    request_draft_alias.add_argument("--intent", required=True, help="Short operator intent to draft the request from.")
    add_assist_alias("spec-first-pass", "spec-first-pass", "Draft a first-pass spec outline from a backlog item.", takes_ref=True)
    add_assist_alias("backlog-groom", "backlog-groom", "Draft a bounded backlog proposal from a request doc.", takes_ref=True)
    add_assist_alias("triage", "triage", "Triage a target request or backlog doc.", takes_ref=True)
    add_assist_alias("handoff", "handoff-packet", "Generate a compact handoff packet for a target workflow doc.", takes_ref=True)
    add_assist_alias("suggest-split", "suggest-split", "Suggest a bounded split for a broad request or backlog item.", takes_ref=True)
    add_assist_alias("diff-risk", "diff-risk", "Classify the current diff risk.", takes_ref=False)
    add_assist_alias("commit-plan", "commit-plan", "Suggest the minimal coherent commit plan for the current diff.", takes_ref=False)
    add_assist_alias("closure-summary", "closure-summary", "Summarize a delivered request, backlog item, or task.", takes_ref=True)
    add_assist_alias("validation-checklist", "validation-checklist", "Generate a validation checklist for the current diff.", takes_ref=False)
    add_assist_alias("doc-consistency", "doc-consistency", "Review workflow docs for consistency issues without mutating them.", takes_ref=False)
    add_assist_alias("changed-surface-summary", "changed-surface-summary", "Summarize the current changed surface deterministically.", takes_ref=False)
    add_assist_alias("release-changelog-status", "release-changelog-status", "Resolve the current curated release changelog contract deterministically.", takes_ref=False)
    add_assist_alias("test-impact-summary", "test-impact-summary", "Summarize deterministic validation impact for the current diff.", takes_ref=False)
    add_assist_alias("hybrid-insights-explainer", "hybrid-insights-explainer", "Explain the current Hybrid Insights report with bounded operator guidance.", takes_ref=False)
    add_assist_alias("windows-compat-risk", "windows-compat-risk", "Review the current change surface for Windows compatibility risk.", takes_ref=False)
    add_assist_alias("review-checklist", "review-checklist", "Generate a bounded review checklist for the current change surface.", takes_ref=False)
    add_assist_alias("doc-link-suggestion", "doc-link-suggestion", "Suggest missing workflow or companion-doc links for a target doc.", takes_ref=True)

    commit_all = assist_sub.add_parser(
        "commit-all",
        help="Suggest or execute a minimal coherent commit plan using the shared hybrid assist runtime.",
    )
    commit_all.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    commit_all.add_argument("--model-profile")
    commit_all.add_argument("--model")
    commit_all.add_argument("--ollama-host")
    commit_all.add_argument("--timeout", type=float)
    commit_all.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    commit_all.add_argument("--profile", choices=("tiny", "normal", "deep"))
    commit_all.add_argument("--include-graph", action="store_true", default=None)
    commit_all.add_argument("--include-registry", action="store_true", default=None)
    commit_all.add_argument("--include-doctor", action="store_true", default=None)
    commit_all.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    commit_all.add_argument("--audit-log")
    commit_all.add_argument("--measurement-log")
    commit_all.add_argument("--format", choices=("text", "json"), default="text")
    commit_all.add_argument("--dry-run", action="store_true")
    commit_all.set_defaults(func=cmd_assist_commit_all)

    prepare_release = assist_sub.add_parser(
        "prepare-release",
        help="Generate changelog via AI if missing, update README badge, commit prep changes, and report readiness.",
    )
    prepare_release.add_argument("--backend", choices=REQUESTED_BACKEND_CHOICES)
    prepare_release.add_argument("--model-profile")
    prepare_release.add_argument("--model")
    prepare_release.add_argument("--ollama-host")
    prepare_release.add_argument("--timeout", type=float)
    prepare_release.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    prepare_release.add_argument("--profile", choices=("tiny", "normal", "deep"))
    prepare_release.add_argument("--include-graph", action="store_true", default=None)
    prepare_release.add_argument("--include-registry", action="store_true", default=None)
    prepare_release.add_argument("--include-doctor", action="store_true", default=None)
    prepare_release.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    prepare_release.add_argument("--audit-log")
    prepare_release.add_argument("--measurement-log")
    prepare_release.add_argument("--format", choices=("text", "json"), default="text")
    prepare_release.add_argument("--dry-run", action="store_true")
    prepare_release.set_defaults(func=cmd_assist_prepare_release)

    publish_release = assist_sub.add_parser(
        "publish-release",
        help="Create the release tag, push main and the tag, and publish the GitHub release.",
    )
    publish_release.add_argument("--model-profile")
    publish_release.add_argument("--model")
    publish_release.add_argument("--ollama-host")
    publish_release.add_argument("--timeout", type=float)
    publish_release.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"))
    publish_release.add_argument("--profile", choices=("tiny", "normal", "deep"))
    publish_release.add_argument("--execution-mode", choices=("suggestion-only", "execute"), default="suggestion-only")
    publish_release.add_argument("--push", action="store_true", default=False, help="Create tag, push main+tag, and publish the GitHub release.")
    publish_release.add_argument("--draft", action="store_true", default=False, help="Create a draft GitHub release instead of publishing immediately.")
    publish_release.add_argument("--version", default=None, help="Override the version to release.")
    publish_release.add_argument("--audit-log")
    publish_release.add_argument("--measurement-log")
    publish_release.add_argument("--format", choices=("text", "json"), default="text")
    publish_release.add_argument("--dry-run", action="store_true")
    publish_release.set_defaults(func=cmd_assist_publish_release)

    sync_parser = sub.add_parser("sync", help="Sync workflow metadata and closure transitions.")
    sync_sub = sync_parser.add_subparsers(dest="sync_kind", required=True)
    close_eligible = sync_sub.add_parser(
        "close-eligible-requests",
        help="Auto-close requests when all linked backlog items are done.",
    )
    close_eligible.add_argument("--format", choices=("text", "json"), default="text")
    close_eligible.add_argument("--dry-run", action="store_true")
    close_eligible.set_defaults(func=cmd_sync_close_eligible_requests)

    refresh_mermaid = sync_sub.add_parser(
        "refresh-mermaid-signatures",
        help="Refresh stale workflow Mermaid signatures without rewriting the full diagram body.",
    )
    refresh_mermaid.add_argument("--format", choices=("text", "json"), default="text")
    refresh_mermaid.add_argument("--dry-run", action="store_true")
    refresh_mermaid.set_defaults(func=cmd_sync_refresh_mermaid_signatures)

    refresh_ai = sync_sub.add_parser(
        "refresh-ai-context",
        help="Backfill or refresh compact AI Context sections for managed workflow docs.",
    )
    refresh_ai.add_argument("sources", nargs="*", help="Optional workflow refs or paths to limit the refresh.")
    refresh_ai.add_argument("--preview", action="store_true", help="Preview the mutation plan without writing files.")
    refresh_ai.add_argument("--mutation-mode", choices=("direct", "transactional"), help="Override the repo mutation mode for this bulk update.")
    refresh_ai.add_argument("--format", choices=("text", "json"), default="text")
    refresh_ai.add_argument("--dry-run", action="store_true")
    refresh_ai.set_defaults(func=cmd_sync_refresh_ai_context)

    context_pack = sync_sub.add_parser(
        "context-pack",
        help="Build a kit-native compact context-pack artifact from workflow docs.",
    )
    context_pack.add_argument("ref", help="Seed workflow ref for the context pack.")
    context_pack.add_argument("--mode", choices=("summary-only", "diff-first", "full"), default="summary-only")
    context_pack.add_argument("--profile", choices=("tiny", "normal", "deep"), default="normal")
    context_pack.add_argument("--out", help="Write the JSON artifact to this relative path.")
    context_pack.add_argument("--format", choices=("text", "json"), default="text")
    context_pack.add_argument("--dry-run", action="store_true")
    context_pack.set_defaults(func=cmd_sync_context_pack)

    schema_status = sync_sub.add_parser(
        "schema-status",
        help="Report schema-version coverage for workflow docs.",
    )
    schema_status.add_argument("sources", nargs="*", help="Optional workflow refs or paths to scope the scan.")
    schema_status.add_argument("--format", choices=("text", "json"), default="text")
    schema_status.set_defaults(func=cmd_sync_schema_status)

    migrate_schema = sync_sub.add_parser(
        "migrate-schema",
        help="Normalize workflow docs to the current schema version.",
    )
    migrate_schema.add_argument("sources", nargs="*", help="Optional workflow refs or paths to limit the migration.")
    migrate_schema.add_argument("--refresh-ai-context", action="store_true", help="Refresh AI Context while migrating schema.")
    migrate_schema.add_argument("--preview", action="store_true", help="Preview the mutation plan without writing files.")
    migrate_schema.add_argument("--mutation-mode", choices=("direct", "transactional"), help="Override the repo mutation mode for this bulk update.")
    migrate_schema.add_argument("--format", choices=("text", "json"), default="text")
    migrate_schema.add_argument("--dry-run", action="store_true")
    migrate_schema.set_defaults(func=cmd_sync_migrate_schema)

    export_graph = sync_sub.add_parser(
        "export-graph",
        help="Export workflow relationships as a machine-readable graph.",
    )
    export_graph.add_argument("--out", help="Write the JSON graph to this relative path.")
    export_graph.add_argument("--format", choices=("text", "json"), default="text")
    export_graph.add_argument("--dry-run", action="store_true")
    export_graph.set_defaults(func=cmd_sync_export_graph)

    validate_skills = sync_sub.add_parser(
        "validate-skills",
        help="Validate skill packages against the kit contract.",
    )
    validate_skills.add_argument("--format", choices=("text", "json"), default="text")
    validate_skills.set_defaults(func=cmd_sync_validate_skills)

    export_registry = sync_sub.add_parser(
        "export-registry",
        help="Export conventions, governance profiles, capability metadata, and release metadata.",
    )
    export_registry.add_argument("--out", help="Write the JSON registry to this relative path.")
    export_registry.add_argument("--format", choices=("text", "json"), default="text")
    export_registry.add_argument("--dry-run", action="store_true")
    export_registry.set_defaults(func=cmd_sync_export_registry)

    doctor = sync_sub.add_parser(
        "doctor",
        help="Diagnose common Logics kit setup, schema, and skill-package issues.",
    )
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    doctor.set_defaults(func=cmd_sync_doctor)

    benchmark = sync_sub.add_parser(
        "benchmark-skills",
        help="Run a lightweight benchmark over skill-package discovery and validation.",
    )
    benchmark.add_argument("--format", choices=("text", "json"), default="text")
    benchmark.set_defaults(func=cmd_sync_benchmark_skills)

    build_index = sync_sub.add_parser(
        "build-index",
        help="Build or refresh the incremental runtime index used by repeated workflow and skill operations.",
    )
    build_index.add_argument("--force", action="store_true", help="Ignore unchanged cache entries and rebuild the runtime index.")
    build_index.add_argument("--format", choices=("text", "json"), default="text")
    build_index.add_argument("--dry-run", action="store_true")
    build_index.set_defaults(func=cmd_sync_build_index)

    show_config = sync_sub.add_parser(
        "show-config",
        help="Show the effective repo-native Logics configuration merged with kit defaults.",
    )
    show_config.add_argument("--format", choices=("text", "json"), default="text")
    show_config.set_defaults(func=cmd_sync_show_config)

    dispatch_context = sync_sub.add_parser(
        "dispatch-context",
        help="Build the compact local-dispatch context bundle used by the deterministic dispatcher.",
    )
    dispatch_context.add_argument("ref", help="Seed workflow ref for the dispatcher context.")
    dispatch_context.add_argument("--mode", choices=("summary-only", "diff-first", "full"), default=DEFAULT_DISPATCH_CONTEXT_MODE)
    dispatch_context.add_argument("--profile", choices=("tiny", "normal", "deep"), default=DEFAULT_DISPATCH_PROFILE)
    dispatch_context.add_argument("--include-graph", action="store_true", help="Include a local graph slice around the seed ref.")
    dispatch_context.add_argument("--include-registry", action="store_true", help="Include a compact registry summary.")
    dispatch_context.add_argument("--include-doctor", action="store_true", help="Include a doctor summary in the context bundle.")
    dispatch_context.add_argument("--out", help="Write the JSON context bundle to this relative path.")
    dispatch_context.add_argument("--format", choices=("text", "json"), default="text")
    dispatch_context.add_argument("--dry-run", action="store_true")
    dispatch_context.set_defaults(func=cmd_sync_dispatch_context)

    dispatch = sync_sub.add_parser(
        "dispatch",
        help="Validate and optionally execute a local dispatcher decision through whitelisted Logics commands.",
    )
    dispatch.add_argument("ref", help="Seed workflow ref for dispatcher context assembly.")
    decision_source = dispatch.add_mutually_exclusive_group(required=True)
    decision_source.add_argument("--decision-json", help="Inline dispatcher decision payload.")
    decision_source.add_argument("--decision-file", help="Path to a JSON file containing the dispatcher decision payload.")
    decision_source.add_argument("--model", help="Use Ollama with this local model to produce the dispatcher decision.")
    dispatch.add_argument("--ollama-host", default="http://127.0.0.1:11434", help="Base URL for Ollama when --model is used.")
    dispatch.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds for Ollama dispatch.")
    dispatch.add_argument("--context-mode", choices=("summary-only", "diff-first", "full"), default=DEFAULT_DISPATCH_CONTEXT_MODE)
    dispatch.add_argument("--profile", choices=("tiny", "normal", "deep"), default=DEFAULT_DISPATCH_PROFILE)
    dispatch.add_argument("--include-graph", action="store_true", help="Include a local graph slice around the seed ref.")
    dispatch.add_argument("--include-registry", action="store_true", help="Include a compact registry summary.")
    dispatch.add_argument("--include-doctor", action="store_true", help="Include a doctor summary in the context bundle.")
    dispatch.add_argument(
        "--execution-mode",
        choices=("suggestion-only", "execute"),
        default=DEFAULT_DISPATCH_EXECUTION_MODE,
        help="Keep the default suggestion-only posture or explicitly execute the mapped command.",
    )
    dispatch.add_argument("--audit-log", default=DEFAULT_DISPATCH_AUDIT_LOG, help="Relative path to the JSONL dispatcher audit log.")
    dispatch.add_argument("--format", choices=("text", "json"), default="text")
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.set_defaults(func=cmd_sync_dispatch)

    return parser


def _run_json_command(args: argparse.Namespace) -> int:
    stdout_buffer = io.StringIO()
    payload: dict[str, object]
    exit_code = 0

    with redirect_stdout(stdout_buffer):
        try:
            result = args.func(args)
            payload = result if isinstance(result, dict) else {"result": result}
            payload.setdefault("ok", True)
        except HybridAssistError as exc:
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            }
        except DispatcherError as exc:
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            }
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
            payload = {
                "ok": False,
                "error": exc.code if isinstance(exc.code, str) else "command failed",
            }
        except Exception as exc:  # pragma: no cover - defensive JSON contract fallback
            exit_code = 1
            payload = {
                "ok": False,
                "error": str(exc) or exc.__class__.__name__,
            }

    logs = [line for line in stdout_buffer.getvalue().splitlines() if line.strip()]
    if logs:
        payload["logs"] = logs
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "format", "text") == "json":
        return _run_json_command(args)
    try:
        result = args.func(args)
    except HybridAssistError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except DispatcherError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

__all__ = [name for name in globals() if not name.startswith("__")]
