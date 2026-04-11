from __future__ import annotations

import re
from pathlib import Path

from workflow_audit import (
    AuditIssue,
    COMPANION_PLACEHOLDERS,
    DOC_KINDS,
    GOVERNANCE_PROFILES,
    STATUS_IN_PROGRESS,
    TOKEN_HYGIENE_PLACEHOLDERS,
    TOKEN_HYGIENE_SECTION_LIMITS,
    DocMeta,
    _apply_scope,
    _autofix_ac_traceability,
    _autofix_structure,
    _collect_docs,
    _decision_framing_value,
    _extract_ai_context_fields,
    _extract_checkboxes,
    _extract_refs,
    _extract_request_ac_ids,
    _extract_section_lines,
    _find_repo_root,
    _has_ac_with_proof,
    _has_mermaid_block,
    _is_done,
    _is_strict_scope,
    _last_modified_age_days,
    _linked_items_for_request,
    _linked_requests_for_item,
    _linked_tasks_for_item,
    _parse_semver,
    _print_json_report,
    _print_text_report,
    _section_content_line_count,
    _sorted_issues,
    _scan_hybrid_cache_for_credentials,
    build_parser,
)


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    profile = GOVERNANCE_PROFILES[args.governance_profile]
    if args.stale_days == 45:
        args.stale_days = int(profile["stale_days"])
    if not args.token_hygiene and profile["token_hygiene"]:
        args.token_hygiene = True
    if profile["require_gates"] is False:
        args.skip_gates = True
    if profile["require_ac_traceability"] is False:
        args.skip_ac_traceability = True
    cutoff = _parse_semver(args.legacy_cutoff_version)
    if args.legacy_cutoff_version and cutoff is None:
        raise SystemExit(
            f"Invalid --legacy-cutoff-version `{args.legacy_cutoff_version}`. Expected semantic version like 1.3.0."
        )
    scope_since = _parse_semver(args.since_version)
    if args.since_version and scope_since is None:
        raise SystemExit(
            f"Invalid --since-version `{args.since_version}`. Expected semantic version like 1.3.0."
        )
    repo_root = _find_repo_root(Path.cwd())
    all_docs = _collect_docs(repo_root)
    docs = _apply_scope(all_docs, repo_root, args.paths, args.refs, scope_since)

    issues: list[AuditIssue] = []
    autofix_targets: dict[Path, set[str]] = {}
    autofix_modified: list[Path] = []

    # 1) task done/100% while item/request closure is inconsistent.
    for doc in docs.values():
        if doc.kind.kind != "task":
            continue
        if not _is_done(doc):
            continue

        item_refs = _extract_refs(doc.text, DOC_KINDS["backlog"].prefix)
        if not item_refs:
            issues.append(
                AuditIssue(
                    code="task_missing_backlog_ref",
                    path=doc.path,
                    message="done task has no linked backlog item reference",
                )
            )
            continue

        for item_ref in sorted(item_refs):
            item_doc = all_docs.get(item_ref)
            if item_doc is None or item_doc.kind.kind != "backlog":
                issues.append(
                    AuditIssue(
                        code="task_refs_missing_backlog",
                        path=doc.path,
                        message=f"references missing backlog item `{item_ref}`",
                    )
                )
                continue
            if not _is_done(item_doc):
                issues.append(
                    AuditIssue(
                        code="task_links_open_backlog",
                        path=doc.path,
                        message=f"done task linked to backlog item not closed `{item_ref}`",
                    )
                )

            for request_doc in _linked_requests_for_item(item_doc, all_docs):
                request_items = _linked_items_for_request(request_doc, all_docs)
                if request_items and all(_is_done(item) for item in request_items) and not _is_done(request_doc):
                    issues.append(
                        AuditIssue(
                            code="request_not_closed_after_backlog_done",
                            path=request_doc.path,
                            message="all backlog items are done but request is not closed",
                        )
                    )

    # 2) orphan backlog items (no request link).
    for doc in docs.values():
        if doc.kind.kind != "backlog":
            continue
        request_refs = _extract_refs(doc.text, DOC_KINDS["request"].prefix)
        if not request_refs:
            issues.append(
                AuditIssue(
                    code="backlog_orphan_no_request",
                    path=doc.path,
                    message="orphan backlog item (no linked request)",
                )
            )

    # 2b) required product/architecture framing without linked companion docs.
    for doc in docs.values():
        if doc.kind.kind not in {"backlog", "task"}:
            continue
        product_framing = _decision_framing_value(doc.text, "Product framing")
        architecture_framing = _decision_framing_value(doc.text, "Architecture framing")
        product_refs = _extract_refs(doc.text, "prod")
        architecture_refs = _extract_refs(doc.text, "adr")
        if product_framing == "Required" and not product_refs:
            issues.append(
                AuditIssue(
                    code="product_brief_required_missing_ref",
                    path=doc.path,
                    message="product framing is required but no linked product brief was found",
                )
            )
        if architecture_framing == "Required" and not architecture_refs:
            issues.append(
                AuditIssue(
                    code="architecture_decision_required_missing_ref",
                    path=doc.path,
                    message="architecture framing is required but no linked ADR was found",
                )
            )

    # 2c) companion docs must be connected and maintained.
    for doc in docs.values():
        if doc.kind.kind not in {"product", "architecture"}:
            continue
        linked_refs = set()
        for prefix in ("req", "item", "task", "prod", "adr"):
            linked_refs.update(_extract_refs(doc.text, prefix))

        if not any(ref.startswith(("req_", "item_", "task_")) for ref in linked_refs):
            issues.append(
                AuditIssue(
                    code="companion_doc_missing_primary_link",
                    path=doc.path,
                    message="companion doc has no linked request, backlog item, or task reference",
                )
            )

        if not _has_mermaid_block(doc.text):
            issues.append(
                AuditIssue(
                    code="companion_doc_missing_mermaid",
                    path=doc.path,
                    message="companion doc is missing its overview Mermaid diagram",
                )
            )

        placeholders = COMPANION_PLACEHOLDERS.get(doc.kind.kind, ())
        if any(snippet in doc.text for snippet in placeholders):
            issues.append(
                AuditIssue(
                    code="companion_doc_contains_placeholders",
                    path=doc.path,
                    message="companion doc still contains generator placeholder content",
                )
            )

        for ref in sorted(linked_refs):
            if ref == doc.ref:
                continue
            if ref not in all_docs:
                issues.append(
                    AuditIssue(
                        code="companion_doc_refs_missing_target",
                        path=doc.path,
                        message=f"companion doc references missing target `{ref}`",
                    )
                )

    # 3) delivered requests with incomplete backlog.
    for doc in docs.values():
        if doc.kind.kind != "request":
            continue
        if not _is_done(doc):
            continue
        request_items = _linked_items_for_request(doc, all_docs)
        if not request_items:
            issues.append(
                AuditIssue(
                    code="request_done_without_backlog",
                    path=doc.path,
                    message="delivered request has no linked backlog items",
                )
            )
            continue
        for item in request_items:
            if not _is_done(item):
                issues.append(
                    AuditIssue(
                        code="request_done_with_open_backlog",
                        path=doc.path,
                        message=f"delivered request linked to incomplete backlog item `{item.ref}`",
                    )
                )

    # 4) stale pending docs.
    if args.stale_days > 0:
        for doc in docs.values():
            if doc.status not in STATUS_IN_PROGRESS:
                continue
            age_days = _last_modified_age_days(doc.path)
            if age_days >= args.stale_days:
                issues.append(
                    AuditIssue(
                        code="stale_pending_doc",
                        path=doc.path,
                        message=f"stale pending doc ({age_days:.1f} days, status={doc.status})",
                    )
                )

    # 5) AC traceability mapping with proof (request AC -> item/task).
    if not args.skip_ac_traceability:
        for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
            if not _is_strict_scope(request, cutoff):
                continue
            ac_ids = _extract_request_ac_ids(request)
            if not ac_ids:
                continue

            linked_items = _linked_items_for_request(request, all_docs)
            if not linked_items:
                issues.append(
                    AuditIssue(
                        code="ac_no_linked_backlog",
                        path=request.path,
                        message="request has ACs but no linked backlog items",
                    )
                )
                continue

            linked_tasks: list[DocMeta] = []
            for item in linked_items:
                linked_tasks.extend(_linked_tasks_for_item(item, all_docs))

            if not linked_tasks:
                issues.append(
                    AuditIssue(
                        code="ac_no_linked_tasks",
                        path=request.path,
                        message="request has ACs but no linked tasks",
                    )
                )
                continue

            for ac_id in ac_ids:
                item_has_mapping = any(_has_ac_with_proof(item.text, ac_id) for item in linked_items)
                if not item_has_mapping:
                    if args.autofix_ac_traceability and linked_items:
                        autofix_targets.setdefault(linked_items[0].path, set()).add(ac_id)
                    else:
                        issues.append(
                            AuditIssue(
                                code="ac_missing_item_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing item-level traceability with proof",
                            )
                        )

                task_has_mapping = any(_has_ac_with_proof(task.text, ac_id) for task in linked_tasks)
                if not task_has_mapping:
                    if args.autofix_ac_traceability and linked_tasks:
                        autofix_targets.setdefault(linked_tasks[0].path, set()).add(ac_id)
                    else:
                        issues.append(
                            AuditIssue(
                                code="ac_missing_task_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing task-level traceability with proof",
                            )
                        )

    # 6) DoR/DoD gates.
    if not args.skip_gates:
        for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
            if not _is_strict_scope(request, cutoff):
                continue
            if request.status not in {"ready", "in progress", "done"}:
                continue
            dor_checks = _extract_checkboxes(_extract_section_lines(request.text, "Definition of Ready (DoR)"))
            if not dor_checks:
                issues.append(
                    AuditIssue(
                        code="request_missing_dor",
                        path=request.path,
                        message="missing DoR checklist",
                    )
                )
            elif any(not checked for checked, _label in dor_checks):
                issues.append(
                    AuditIssue(
                        code="request_dor_unchecked",
                        path=request.path,
                        message="DoR checklist contains unchecked items",
                    )
                )

        for task in [doc for doc in docs.values() if doc.kind.kind == "task"]:
            if not _is_strict_scope(task, cutoff):
                continue
            if not _is_done(task):
                continue
            dod_checks = _extract_checkboxes(_extract_section_lines(task.text, "Definition of Done (DoD)"))
            if not dod_checks:
                issues.append(
                    AuditIssue(
                        code="task_missing_dod",
                        path=task.path,
                        message="missing DoD checklist",
                    )
                )
            elif any(not checked for checked, _label in dod_checks):
                issues.append(
                    AuditIssue(
                        code="task_dod_unchecked",
                        path=task.path,
                        message="DoD checklist contains unchecked items",
                    )
                )

    # 7) Token hygiene and compact AI context.
    if args.token_hygiene:
        for doc in docs.values():
            if doc.kind.kind not in {"request", "backlog", "task"}:
                continue

            ai_fields = _extract_ai_context_fields(doc.text)
            if not ai_fields:
                issues.append(
                    AuditIssue(
                        code="token_hygiene_missing_ai_context",
                        path=doc.path,
                        message="missing `# AI Context` section for compact handoff metadata",
                    )
                )
            else:
                summary = ai_fields.get("summary", "")
                if not summary or any(snippet.lower() in summary.lower() for snippet in TOKEN_HYGIENE_PLACEHOLDERS):
                    issues.append(
                        AuditIssue(
                            code="token_hygiene_ai_summary_weak",
                            path=doc.path,
                            message="AI summary is missing or still contains placeholder text",
                        )
                    )
                keywords = ai_fields.get("keywords", "")
                keyword_count = len([part for part in re.split(r"[,;]", keywords) if part.strip()])
                if keyword_count > 10:
                    issues.append(
                        AuditIssue(
                            code="token_hygiene_ai_keywords_too_many",
                            path=doc.path,
                            message=f"AI keywords should stay compact (found {keyword_count}, limit 10)",
                        )
                    )
                use_when = ai_fields.get("use when", "")
                skip_when = ai_fields.get("skip when", "")
                if not use_when or not skip_when:
                    issues.append(
                        AuditIssue(
                            code="token_hygiene_ai_usage_incomplete",
                            path=doc.path,
                            message="AI Context must define both `Use when` and `Skip when` guidance",
                        )
                    )

            section_limits = TOKEN_HYGIENE_SECTION_LIMITS.get(doc.kind.kind, {})
            for heading, max_lines in section_limits.items():
                line_count = _section_content_line_count(doc.text, heading)
                if line_count > max_lines:
                    issues.append(
                        AuditIssue(
                            code="token_hygiene_section_too_long",
                            path=doc.path,
                            message=f"`# {heading}` is too verbose for lean handoffs ({line_count} lines, limit {max_lines})",
                        )
                    )

    if args.autofix_ac_traceability and autofix_targets:
        for path, ac_ids in sorted(autofix_targets.items(), key=lambda pair: pair[0].as_posix()):
            if _autofix_ac_traceability(path, ac_ids):
                autofix_modified.append(path)

        if autofix_modified:
            all_docs = _collect_docs(repo_root)
            docs = _apply_scope(all_docs, repo_root, args.paths, args.refs, scope_since)
            issues = [
                issue
                for issue in issues
                if issue.code not in {"ac_missing_item_traceability", "ac_missing_task_traceability"}
            ]

            for request in [doc for doc in docs.values() if doc.kind.kind == "request"]:
                if args.skip_ac_traceability:
                    break
                if not _is_strict_scope(request, cutoff):
                    continue
                ac_ids = _extract_request_ac_ids(request)
                if not ac_ids:
                    continue
                linked_items = _linked_items_for_request(request, all_docs)
                linked_tasks: list[DocMeta] = []
                for item in linked_items:
                    linked_tasks.extend(_linked_tasks_for_item(item, all_docs))
                for ac_id in ac_ids:
                    if linked_items and not any(_has_ac_with_proof(item.text, ac_id) for item in linked_items):
                        issues.append(
                            AuditIssue(
                                code="ac_missing_item_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing item-level traceability with proof",
                            )
                        )
                    if linked_tasks and not any(_has_ac_with_proof(task.text, ac_id) for task in linked_tasks):
                        issues.append(
                            AuditIssue(
                                code="ac_missing_task_traceability",
                                path=request.path,
                                message=f"`{ac_id}` missing task-level traceability with proof",
                            )
                        )

    if args.autofix_structure:
        for doc in docs.values():
            if doc.kind.kind not in {"request", "backlog", "task"}:
                continue
            if _autofix_structure(doc.path, doc.kind.kind):
                autofix_modified.append(doc.path)

        if autofix_modified:
            all_docs = _collect_docs(repo_root)
            docs = _apply_scope(all_docs, repo_root, args.paths, args.refs, scope_since)
            issues = []

            return main(
                [
                    *([f"--stale-days={args.stale_days}"] if args.stale_days >= 0 else []),
                    *([] if not args.skip_ac_traceability else ["--skip-ac-traceability"]),
                    *([] if not args.skip_gates else ["--skip-gates"]),
                    *([f"--legacy-cutoff-version={args.legacy_cutoff_version}"] if args.legacy_cutoff_version else []),
                    *([f"--format={args.format}"]),
                    *(["--group-by-doc"] if args.group_by_doc else []),
                    *(["--token-hygiene"] if args.token_hygiene else []),
                    *(["--governance-profile", args.governance_profile] if args.governance_profile else []),
                    *(["--paths", *args.paths] if args.paths else []),
                    *(["--refs", *args.refs] if args.refs else []),
                    *(["--since-version", args.since_version] if args.since_version else []),
                ]
            )

    issues.extend(_scan_hybrid_cache_for_credentials(repo_root))
    sorted_issues = _sorted_issues(issues, repo_root)

    if args.format == "json":
        _print_json_report(sorted_issues, repo_root, args.autofix_ac_traceability, autofix_modified)
    else:
        _print_text_report(sorted_issues, repo_root, args.group_by_doc)

    return 0 if not sorted_issues else 1
