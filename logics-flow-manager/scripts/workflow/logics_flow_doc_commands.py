#!/usr/bin/env python3
from __future__ import annotations

from logics_flow_assist_commands import *  # noqa: F401,F403

def _mutation_mode(args: argparse.Namespace, config: dict[str, object]) -> str:
    if getattr(args, "mutation_mode", None):
        return str(args.mutation_mode)
    return str(get_config_value(config, "mutations", "mode", default="transactional"))


def _mutation_audit_log(config: dict[str, object]) -> str:
    return str(get_config_value(config, "mutations", "audit_log", default="logics/mutation_audit.jsonl"))


def _enforce_split_policy(titles: list[str], args: argparse.Namespace, config: dict[str, object]) -> None:
    policy = str(get_config_value(config, "workflow", "split", "policy", default="minimal-coherent"))
    max_children = int(get_config_value(config, "workflow", "split", "max_children_without_override", default=2))
    if policy != "minimal-coherent":
        return
    if len(titles) <= max_children or getattr(args, "allow_extra_slices", False):
        return
    raise SystemExit(
        "Split policy `minimal-coherent` only allows "
        + f"{max_children} child slice(s) by default. "
        + "Reduce the split or pass `--allow-extra-slices` when the extra decomposition is genuinely required."
    )


def _run_mapped_command(repo_root: Path, argv: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "logics_flow.py"), *argv, "--format", "json"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "Mapped command failed."
        raise DispatcherError(
            "dispatcher_command_failed",
            error_message,
            details={"argv": argv, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DispatcherError(
            "dispatcher_command_invalid_json",
            f"Mapped command did not return valid JSON: {exc}",
            details={"argv": argv, "stdout": result.stdout},
        ) from exc
    return payload


def cmd_sync_dispatch_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_dispatcher_context(
        repo_root,
        args.ref,
        mode=args.mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "dispatch-context", **payload}


def cmd_sync_dispatch(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    context_bundle = _build_dispatcher_context(
        repo_root,
        args.ref,
        mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    docs_by_ref = _load_workflow_docs(repo_root, config=config)

    transport: dict[str, object]
    if args.decision_json:
        decision_payload = extract_json_object(args.decision_json)
        transport = {"transport": "inline", "source": "decision-json"}
    elif args.decision_file:
        decision_payload = extract_json_object(Path(args.decision_file).read_text(encoding="utf-8"))
        transport = {"transport": "file", "source": args.decision_file}
    elif args.model:
        transport = run_ollama_dispatch(
            host=args.ollama_host,
            model=args.model,
            context_bundle=context_bundle,
            timeout_seconds=args.timeout,
        )
        decision_payload = transport["decision_payload"]
    else:
        raise SystemExit("Provide exactly one of --decision-json, --decision-file, or --model.")

    validated = validate_dispatcher_decision(decision_payload, docs_by_ref)
    mapped = map_decision_to_command(validated, docs_by_ref)

    execution_result: dict[str, object] | None = None
    executed = False
    if args.execution_mode == "execute":
        execution_result = _run_mapped_command(repo_root, mapped["argv"])
        executed = True

    audit_path = (repo_root / args.audit_log).resolve()
    audit_record = build_audit_record(
        seed_ref=args.ref,
        execution_mode=args.execution_mode,
        context_bundle=context_bundle,
        decision_payload=decision_payload,
        validated_decision=validated,
        mapped_command=mapped,
        execution_result=execution_result,
        transport=transport,
    )
    if not args.dry_run:
        append_audit_record(audit_path, audit_record)

    if executed:
        print(f"Executed dispatcher action `{validated.action}` via {' '.join(mapped['argv'])}.")
    else:
        print(f"Suggested dispatcher action `{validated.action}` via {' '.join(mapped['argv'])}.")
    print(f"Audit log: {audit_path.relative_to(repo_root)}")

    return {
        "command": "sync",
        "sync_kind": "dispatch",
        "seed_ref": args.ref,
        "execution_mode": args.execution_mode,
        "executed": executed,
        "decision_source": transport["transport"],
        "audit_log": _rel(repo_root, audit_path),
        "context_bundle": context_bundle,
        "raw_decision": decision_payload,
        "validated_decision": validated.to_dict(),
        "mapped_command": mapped,
        "execution_result": execution_result,
        "transport": transport,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "dry_run": args.dry_run,
    }

def cmd_new(args: argparse.Namespace) -> None:
    doc_kind = DOC_KINDS[args.kind]
    repo_root = _find_repo_root(Path.cwd())
    planned = _reserve_doc(repo_root / doc_kind.directory, doc_kind.prefix, args.slug or args.title, args.dry_run)

    template_text = _template_path(Path(__file__), doc_kind.template_name).read_text(encoding="utf-8")
    args.from_version = _resolved_from_version(repo_root, getattr(args, "from_version", None))
    values = _build_template_values(args, planned.ref, args.title, doc_kind.include_progress, doc_kind.kind)
    _seed_new_doc_values(doc_kind.kind, args.title, values)
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(args.title))
    assessment = _assess_decision_framing(args.title, "")
    product_refs: list[str] = []
    architecture_refs: list[str] = []
    if doc_kind.kind in {"backlog", "task"}:
        product_refs, architecture_refs = _auto_create_companion_docs(
            repo_root,
            args.title,
            request_ref=None,
            backlog_ref=planned.ref if doc_kind.kind == "backlog" else None,
            task_ref=planned.ref if doc_kind.kind == "task" else None,
            assessment=assessment,
            product_refs=product_refs,
            architecture_refs=architecture_refs,
            args=args,
        )
        _apply_decision_assessment(values, assessment)
        if product_refs:
            values["PRODUCT_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in product_refs)
        if architecture_refs:
            values["ARCHITECTURE_LINK_PLACEHOLDER"] = ", ".join(f"`{ref}`" for ref in architecture_refs)

    values["MERMAID_BLOCK"] = _generate_workflow_mermaid(
        repo_root,
        doc_kind.kind,
        args.title,
        values,
        dry_run=args.dry_run,
    )
    content = _render_template(template_text, values).rstrip() + "\n"
    content, _changed = refresh_ai_context_text(content, doc_kind.kind)
    content, _changed = refresh_workflow_mermaid_signature_text(
        content,
        doc_kind.kind,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )
    _write(planned.path, content, args.dry_run)
    if doc_kind.kind in {"backlog", "task"}:
        _print_decision_summary(planned.ref, assessment, product_refs, architecture_refs)
    return {
        "command": "new",
        "kind": doc_kind.kind,
        "ref": planned.ref,
        "path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_promote_request_to_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Promoted backlog item"
    repo_root = _find_repo_root(Path.cwd())
    planned = _create_backlog_from_request(repo_root, source_path, title, args)
    print(
        "Created a backlog slice from the request. "
        "If the request spans multiple deliverables, use `python logics/skills/logics.py flow assist suggest-split <request-ref> --format json` "
        "followed by `python logics/skills/logics.py flow split request ...` so the request is covered by several bounded backlog items instead of one oversized item."
    )
    return {
        "command": "promote",
        "promotion": "request-to-backlog",
        "source": _rel(repo_root, source_path),
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_promote_backlog_to_task(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    title = _parse_title_from_source(source_path) or "Implementation task"
    repo_root = _find_repo_root(Path.cwd())
    planned = _create_task_from_backlog(repo_root, source_path, title, args)
    return {
        "command": "promote",
        "promotion": "backlog-to-task",
        "source": _rel(repo_root, source_path),
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "dry_run": args.dry_run,
    }


def cmd_split_request(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    config, _config_path = _effective_config(repo_root)
    titles = _split_titles(args.title)
    _enforce_split_policy(titles, args, config)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_backlog_from_request(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split request into {len(created_refs)} backlog item(s): {', '.join(created_refs)}")
    return {
        "command": "split",
        "kind": "request",
        "source": _rel(repo_root, source_path),
        "created_refs": created_refs,
        "dry_run": args.dry_run,
    }


def cmd_split_backlog(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")

    repo_root = _find_repo_root(Path.cwd())
    config, _config_path = _effective_config(repo_root)
    titles = _split_titles(args.title)
    _enforce_split_policy(titles, args, config)
    created_refs: list[str] = []
    for title in titles:
        planned = _create_task_from_backlog(repo_root, source_path, title, args)
        created_refs.append(planned.ref)

    print(f"Split backlog item into {len(created_refs)} task(s): {', '.join(created_refs)}")
    return {
        "command": "split",
        "kind": "backlog",
        "source": _rel(repo_root, source_path),
        "created_refs": created_refs,
        "dry_run": args.dry_run,
    }


def _maybe_close_request_chain(repo_root: Path, request_ref: str, dry_run: bool) -> None:
    request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
    if request_path is None:
        return

    linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
    if not linked_items:
        return

    if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
        if not _is_doc_done(request_path, DOC_KINDS["request"]):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")


def _sync_close_eligible_requests(repo_root: Path, dry_run: bool) -> tuple[int, int]:
    request_dir = repo_root / DOC_KINDS["request"].directory
    closed = 0
    scanned = 0
    for request_path in sorted(request_dir.glob("req_*.md")):
        request_ref = request_path.stem
        scanned += 1
        if _is_doc_done(request_path, DOC_KINDS["request"]):
            continue
        linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
        if not linked_items:
            continue
        if all(_is_doc_done(item_path, DOC_KINDS["backlog"]) for item_path in linked_items):
            _close_doc(request_path, DOC_KINDS["request"], dry_run)
            print(f"Auto-closed request {request_ref} (all linked backlog items are done).")
            closed += 1
    return scanned, closed


def cmd_sync_close_eligible_requests(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    scanned, closed = _sync_close_eligible_requests(repo_root, args.dry_run)
    print(f"Scanned {scanned} requests, auto-closed {closed}.")
    return {"command": "sync", "sync_kind": "close-eligible-requests", "scanned": scanned, "closed": closed, "dry_run": args.dry_run}


def cmd_sync_refresh_mermaid_signatures(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    refreshed: list[Path] = []
    for kind_name in ("request", "backlog", "task"):
        kind = DOC_KINDS[kind_name]
        directory = repo_root / kind.directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"{kind.prefix}_*.md")):
            if refresh_workflow_mermaid_signature_file(path, kind_name, args.dry_run, repo_root=repo_root):
                refreshed.append(path.relative_to(repo_root))

    if args.dry_run:
        print(f"Dry run: {len(refreshed)} Mermaid signature update(s) would be applied.")
    else:
        print(f"Refreshed Mermaid signatures in {len(refreshed)} workflow doc(s).")
    for path in refreshed:
        print(f"- {path}")
    return {
        "command": "sync",
        "sync_kind": "refresh-mermaid-signatures",
        "modified_files": [path.as_posix() for path in refreshed],
        "dry_run": args.dry_run,
    }


def cmd_sync_refresh_ai_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    modified: list[dict[str, object]] = []
    writes: list[TransactionWrite] = []
    for kind_name, path in _resolve_target_docs(repo_root, args.sources):
        original = path.read_text(encoding="utf-8")
        refreshed, changed = refresh_ai_context_text(original, kind_name)
        if not changed:
            continue
        mutation = build_planned_mutation(path, before=original, after=refreshed, reason="refresh AI Context", repo_root=repo_root)
        modified.append(mutation.to_dict())
        writes.append(TransactionWrite(path=path, content=refreshed, reason="refresh AI Context"))
    try:
        transaction = apply_transaction(
            repo_root,
            writes=writes,
            mode=_mutation_mode(args, config),
            audit_log=_mutation_audit_log(config),
            dry_run=args.preview or args.dry_run,
            command_name="sync refresh-ai-context",
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    if args.preview:
        print(f"Previewed AI Context refresh for {len(modified)} workflow doc(s).")
    else:
        print(f"Refreshed AI Context in {len(modified)} workflow doc(s).")
    for mutation in modified:
        print(f"- {mutation['path']}")
    return {
        "command": "sync",
        "sync_kind": "refresh-ai-context",
        "preview": args.preview,
        "dry_run": args.dry_run,
        "modified_files": modified,
        "mutation_mode": transaction.mode,
        "mutation_audit_log": transaction.audit_path,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
    }


def cmd_sync_context_pack(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_context_pack(repo_root, args.ref, mode=args.mode, profile=args.profile, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        _write(out_path, serialized, args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "context-pack", **payload}


def cmd_sync_schema_status(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    payload = _schema_status(repo_root, args.sources)
    print(f"Schema status: {payload['doc_count']} workflow doc(s) scanned.")
    for version, count in payload["counts"].items():
        print(f"- {version}: {count}")
    return {"command": "sync", "sync_kind": "schema-status", **payload}


def cmd_sync_migrate_schema(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    modified: list[dict[str, object]] = []
    writes: list[TransactionWrite] = []
    for kind_name, path in _resolve_target_docs(repo_root, args.sources):
        original = path.read_text(encoding="utf-8")
        refreshed, changed = _ensure_schema_version_text(original)
        if args.refresh_ai_context:
            refreshed, ai_changed = refresh_ai_context_text(refreshed, kind_name)
            changed = changed or ai_changed
        if not changed:
            continue
        mutation = build_planned_mutation(path, before=original, after=refreshed, reason="migrate workflow schema", repo_root=repo_root)
        modified.append(mutation.to_dict())
        writes.append(TransactionWrite(path=path, content=refreshed, reason="migrate workflow schema"))
    try:
        transaction = apply_transaction(
            repo_root,
            writes=writes,
            mode=_mutation_mode(args, config),
            audit_log=_mutation_audit_log(config),
            dry_run=args.preview or args.dry_run,
            command_name="sync migrate-schema",
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    if args.preview:
        print(f"Previewed schema migration for {len(modified)} workflow doc(s).")
    else:
        print(f"Migrated schema for {len(modified)} workflow doc(s).")
    for mutation in modified:
        print(f"- {mutation['path']}")
    return {
        "command": "sync",
        "sync_kind": "migrate-schema",
        "preview": args.preview,
        "dry_run": args.dry_run,
        "refresh_ai_context": args.refresh_ai_context,
        "modified_files": modified,
        "mutation_mode": transaction.mode,
        "mutation_audit_log": transaction.audit_path,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
    }


def cmd_sync_export_graph(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _graph_payload(repo_root, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "export-graph", **payload}


def cmd_sync_validate_skills(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _validate_skills_payload(repo_root, config=config)
    print(f"Validated {payload['skill_count']} skill package(s).")
    if payload["issues"]:
        for issue in payload["issues"]:
            print(f"- {issue['path']}: {'; '.join(issue['issues'])}")
    else:
        print("- No skill package issues detected.")
    return {"command": "sync", "sync_kind": "validate-skills", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_export_registry(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _export_registry_payload(repo_root, config=config)
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        print(f"Wrote {out_path.relative_to(repo_root)}")
        payload["output_path"] = _rel(repo_root, out_path)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "export-registry", **payload}


def cmd_sync_doctor(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _doctor_payload(repo_root, config=config)
    if payload["ok"]:
        print("Kit doctor: OK")
    else:
        print("Kit doctor: FAILED")
        for issue in payload["issues"]:
            print(f"- [{issue['code']}] {issue['path']}: {issue['message']}")
            print(f"  remediation: {issue['remediation']}")
    return {"command": "sync", "sync_kind": "doctor", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_benchmark_skills(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _benchmark_payload(repo_root, config=config)
    print(f"Benchmarked {payload['skill_count']} skill package(s) in {payload['duration_ms']} ms.")
    return {"command": "sync", "sync_kind": "benchmark-skills", "config_path": _rel(repo_root, config_path) if config_path is not None else None, **payload}


def cmd_sync_build_index(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = load_runtime_index(repo_root, config=config, force=args.force, dry_run=args.dry_run)
    print(
        "Runtime index: "
        + f"{payload['stats']['workflow_doc_count']} workflow doc(s), "
        + f"{payload['stats']['skill_count']} skill package(s), "
        + f"{payload['stats']['cache_hits']} cache hit(s), "
        + f"{payload['stats']['cache_misses']} cache miss(es)."
    )
    return {
        "command": "sync",
        "sync_kind": "build-index",
        "dry_run": args.dry_run,
        "force": args.force,
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        **payload,
    }


def cmd_sync_show_config(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = {
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "config": config,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return {"command": "sync", "sync_kind": "show-config", **payload}


def cmd_close(args: argparse.Namespace) -> None:
    repo_root = _find_repo_root(Path.cwd())
    kind = DOC_KINDS[args.kind]
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Source not found: {source_path}")
    if not source_path.stem.startswith(f"{kind.prefix}_"):
        raise SystemExit(f"Expected a `{kind.prefix}_...` file for kind `{kind.kind}`. Got: {source_path.name}")

    _close_doc(source_path, kind, args.dry_run)
    print(f"Closed {kind.kind}: {source_path.relative_to(repo_root)}")

    text = _strip_mermaid_blocks(source_path.read_text(encoding="utf-8"))
    processed_request_refs: set[str] = set()

    if kind.kind == "task":
        linked_item_refs = sorted(_extract_refs(text, REF_PREFIXES["backlog"]))
        for item_ref in linked_item_refs:
            item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
            if item_path is None:
                continue
            linked_tasks = _collect_docs_linking_ref(repo_root, DOC_KINDS["task"], item_ref)
            if linked_tasks and all(_is_doc_done(task_path, DOC_KINDS["task"]) for task_path in linked_tasks):
                if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
                    _close_doc(item_path, DOC_KINDS["backlog"], args.dry_run)
                    print(f"Auto-closed backlog item {item_ref} (all linked tasks are done).")

            item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
            for request_ref in sorted(_extract_refs(item_text, REF_PREFIXES["request"])):
                if request_ref in processed_request_refs:
                    continue
                processed_request_refs.add(request_ref)
                _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "backlog":
        for request_ref in sorted(_extract_refs(text, REF_PREFIXES["request"])):
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            _maybe_close_request_chain(repo_root, request_ref, args.dry_run)

    if kind.kind == "request":
        request_ref = source_path.stem
        _maybe_close_request_chain(repo_root, request_ref, args.dry_run)
    return {
        "command": "close",
        "kind": kind.kind,
        "source": _rel(repo_root, source_path),
        "dry_run": args.dry_run,
    }


def _verify_finished_task_chain(repo_root: Path, task_path: Path) -> list[str]:
    issues: list[str] = []
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))

    if not item_refs:
        return [f"task `{task_ref}` has no linked backlog item reference"]

    processed_request_refs: set[str] = set()
    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            issues.append(f"task `{task_ref}` references missing backlog item `{item_ref}`")
            continue
        if not _is_doc_done(item_path, DOC_KINDS["backlog"]):
            issues.append(f"linked backlog item `{item_ref}` is not closed after finishing task `{task_ref}`")

        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs = sorted(_extract_refs(item_text, REF_PREFIXES["request"]))
        if not request_refs:
            issues.append(f"linked backlog item `{item_ref}` has no request reference")
            continue

        for request_ref in request_refs:
            if request_ref in processed_request_refs:
                continue
            processed_request_refs.add(request_ref)
            request_path = _resolve_doc_path(repo_root, DOC_KINDS["request"], request_ref)
            if request_path is None:
                issues.append(f"backlog item `{item_ref}` references missing request `{request_ref}`")
                continue

            linked_items = _collect_docs_linking_ref(repo_root, DOC_KINDS["backlog"], request_ref)
            if linked_items and all(_is_doc_done(linked_item, DOC_KINDS["backlog"]) for linked_item in linked_items):
                if not _is_doc_done(request_path, DOC_KINDS["request"]):
                    issues.append(
                        f"request `{request_ref}` should be closed because all linked backlog items are done"
                    )

    return issues


def _record_finished_task_follow_up(repo_root: Path, task_path: Path, dry_run: bool) -> None:
    task_ref = task_path.stem
    task_text = _strip_mermaid_blocks(task_path.read_text(encoding="utf-8"))
    item_refs = sorted(_extract_refs(task_text, REF_PREFIXES["backlog"]))
    request_refs: set[str] = set()

    for item_ref in item_refs:
        item_path = _resolve_doc_path(repo_root, DOC_KINDS["backlog"], item_ref)
        if item_path is None:
            continue
        item_text = _strip_mermaid_blocks(item_path.read_text(encoding="utf-8"))
        request_refs.update(_extract_refs(item_text, REF_PREFIXES["request"]))
        _append_section_bullets(
            item_path,
            "Notes",
            [f"- Task `{task_ref}` was finished via `logics_flow.py finish task` on {date.today().isoformat()}."],
            dry_run,
        )

    validation_bullets = [
        f"- Finish workflow executed on {date.today().isoformat()}.",
        "- Linked backlog/request close verification passed.",
    ]
    report_bullets = [
        f"- Finished on {date.today().isoformat()}.",
        f"- Linked backlog item(s): {', '.join(f'`{ref}`' for ref in item_refs) if item_refs else '(none)'}",
        f"- Related request(s): {', '.join(f'`{ref}`' for ref in sorted(request_refs)) if request_refs else '(none)'}",
    ]
    _append_section_bullets(task_path, "Validation", validation_bullets, dry_run)
    _append_section_bullets(task_path, "Report", report_bullets, dry_run)



__all__ = [name for name in globals() if not name.startswith("__")]
