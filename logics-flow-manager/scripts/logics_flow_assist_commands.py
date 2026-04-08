#!/usr/bin/env python3
from __future__ import annotations

from logics_flow_runtime_support import *  # noqa: F401,F403

def cmd_assist_runtime_status(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    model_selection = _hybrid_model_selection(
        config,
        requested_model_profile=getattr(args, "model_profile", None),
        requested_model=args.model,
    )
    payload = build_runtime_status(
        repo_root=repo_root,
        requested_backend=args.backend or _hybrid_default_backend(config),
        requested_model=args.model,
        config=config,
        host=args.ollama_host or _hybrid_default_host(config),
        model_profile=model_selection,
        supported_model_profiles=model_selection["supported_profiles"],
        model=str(model_selection["resolved_model"]),
        timeout_seconds=args.timeout or _hybrid_default_timeout(config),
        claude_bridge_status=_claude_bridge_status(repo_root),
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "runtime-status"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_context(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _build_hybrid_context(
        repo_root,
        args.flow_name,
        ref=getattr(args, "ref", None),
        context_mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        config=config,
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "context"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_roi_report(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    audit_path = (repo_root / (args.audit_log or _hybrid_audit_log(config))).resolve()
    measurement_path = (repo_root / (args.measurement_log or _hybrid_measurement_log(config))).resolve()
    payload = build_hybrid_roi_report(
        repo_root=repo_root,
        audit_log=audit_path,
        measurement_log=measurement_path,
        recent_limit=args.recent_limit,
        window_days=args.window_days,
    )
    payload["command"] = "assist"
    payload["assist_kind"] = "roi-report"
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.out:
        out_path = (repo_root / args.out).resolve()
        _write(out_path, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
        payload["output_path"] = _rel(repo_root, out_path)
    elif args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def _run_hybrid_assist(
    repo_root: Path,
    *,
    flow_name: str,
    ref: str | None,
    intent: str | None = None,
    requested_backend: str,
    requested_model_profile: str | None,
    requested_model: str | None,
    ollama_host: str,
    timeout_seconds: float,
    context_mode: str | None,
    profile: str | None,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    execution_mode: str,
    audit_log: str,
    measurement_log: str,
    config: dict[str, object],
    dry_run: bool,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    normalized_intent = " ".join(str(intent or "").split()).strip()
    if flow_name == "request-draft" and not normalized_intent:
        raise SystemExit("`request-draft` requires `--intent`.")
    if flow_name == "spec-first-pass" and not ref:
        raise SystemExit("`spec-first-pass` requires a backlog ref.")
    if flow_name == "backlog-groom" and not ref:
        raise SystemExit("`backlog-groom` requires a request ref.")
    docs_by_ref = _load_workflow_docs(repo_root, config=config)
    model_selection = _hybrid_model_selection(
        config,
        requested_model_profile=requested_model_profile,
        requested_model=requested_model,
    )
    resolved_profile = profile or str(default_context_spec(flow_name)["profile"])
    context_bundle, validation_payload = _prepare_hybrid_context_bundle(
        repo_root,
        flow_name=flow_name,
        ref=ref,
        intent=normalized_intent or None,
        context_mode=context_mode,
        profile=resolved_profile,
        include_graph=include_graph,
        include_registry=include_registry,
        include_doctor=include_doctor,
        audit_log=audit_log,
        measurement_log=measurement_log,
        config=config,
    )
    preclassified_result = _deterministic_preclassified_result(flow_name, context_bundle)
    profile_adjustment_reason: str | None = None

    if preclassified_result is not None:
        backend_status = _deterministic_backend_status(
            requested_backend=requested_backend,
            model_selection=model_selection,
        )
        degraded_reasons: list[str] = []
        raw_payload = dict(preclassified_result["validated"])
        transport = {
            "transport": "deterministic",
            "reason": "deterministic-preclassified",
            "selected_backend": "deterministic",
            "preclassification_reason": preclassified_result["reason"],
        }
        validated = dict(preclassified_result["validated"])
        active_model_profile = {
            "name": model_selection["name"],
            "family": model_selection["family"],
            "configured_model": model_selection["configured_model"],
            "resolved_model": model_selection["resolved_model"],
            "description": model_selection["description"],
            "example_tags": model_selection["example_tags"],
        }
        cache_path = (repo_root / _hybrid_result_cache_path(config)).resolve()
        cache_key = ""
        diff_fingerprint = ""
        cache_hit = False
    else:
        backend_status, backend_selection_reasons = _select_hybrid_backend_for_flow(
            requested_backend=requested_backend,
            flow_name=flow_name,
            repo_root=repo_root,
            config=config,
            requested_model=requested_model,
            host=ollama_host,
            model_profile=str(model_selection["name"]),
            model_family=str(model_selection["family"]),
            configured_model=str(model_selection["configured_model"]),
            model=str(model_selection["resolved_model"]),
            timeout_seconds=timeout_seconds,
        )
        effective_profile, profile_adjustment_reason, requested_profile_label = _resolve_runtime_context_profile(
            flow_name=flow_name,
            requested_profile=profile,
            backend_status=backend_status,
        )
        if effective_profile != resolved_profile:
            context_bundle, validation_payload = _prepare_hybrid_context_bundle(
                repo_root,
                flow_name=flow_name,
                ref=ref,
                context_mode=context_mode,
                profile=effective_profile,
                include_graph=include_graph,
                include_registry=include_registry,
                include_doctor=include_doctor,
                audit_log=audit_log,
                measurement_log=measurement_log,
                config=config,
            )
            context_bundle["context_profile"]["requested_profile"] = requested_profile_label
            context_bundle["context_profile"]["profile_adjustment"] = "capped-to-normal-for-remote-or-codex"
            resolved_profile = effective_profile
        cache_eligible = (
            execution_mode != "execute"
            and flow_name != "hybrid-insights-explainer"
            and context_bundle["contract"]["safety_class"] == "proposal-only"
        )
        cache_path, cache_key, diff_fingerprint, cached_entry = _read_hybrid_result_cache_entry(
            repo_root=repo_root,
            config=config,
            flow_name=flow_name,
            requested_backend=requested_backend,
            model_selection=model_selection,
            context_bundle=context_bundle,
            dry_run=dry_run,
        )
        cache_hit = cache_eligible and cached_entry is not None

        if cache_hit:
            backend_status = _cached_backend_status(cached_entry, requested_backend)
            degraded_reasons = []
            raw_payload = cached_entry.get("raw_payload") if isinstance(cached_entry.get("raw_payload"), dict) else None
            transport = {
                "transport": "cache",
                "reason": "cache-hit",
                "selected_backend": backend_status.selected_backend,
                "cache_key": cache_key,
            }
            validated = dict(cached_entry["validated_payload"])
            active_model_profile = (
                cached_entry.get("active_model_profile")
                if isinstance(cached_entry.get("active_model_profile"), dict)
                else None
            )
        else:
            execution = execute_hybrid_backend(
                backend_status=backend_status,
                requested_backend=requested_backend,
                flow_name=flow_name,
                context_bundle=context_bundle,
                repo_root=repo_root,
                config=config,
                requested_model=requested_model,
                timeout_seconds=timeout_seconds,
                docs_by_ref=docs_by_ref,
                validation_payload=validation_payload,
            )
            backend_status = execution["backend_status"]
            degraded_reasons = [*backend_selection_reasons, *execution["degraded_reasons"]]
            raw_payload = execution["raw_payload"]
            transport = execution["transport"]
            validated = execution["validated"]
            active_model_profile = {
                "name": model_selection["name"],
                "family": model_selection["family"],
                "configured_model": model_selection["configured_model"],
                "resolved_model": model_selection["resolved_model"],
                "description": model_selection["description"],
                "example_tags": model_selection["example_tags"],
            }

    if profile_adjustment_reason and profile_adjustment_reason not in degraded_reasons:
        degraded_reasons = [profile_adjustment_reason, *degraded_reasons]

    execution_result = None
    executed = False
    if flow_name == "next-step":
        decision = validate_dispatcher_decision(validated, docs_by_ref)
        mapped_command = map_decision_to_command(decision, docs_by_ref)
        if execution_mode == "execute":
            execution_result = _run_mapped_command(repo_root, mapped_command["argv"])
            executed = True
        validated = {"decision": decision.to_dict(), "mapped_command": mapped_command}
    elif flow_name == "request-draft":
        if execution_mode == "execute":
            execution_result = _execute_request_draft(
                repo_root=repo_root,
                intent=normalized_intent or "Request draft",
                validated=validated,
                dry_run=dry_run,
            )
            executed = bool(execution_result.get("written"))
    elif flow_name == "spec-first-pass":
        if execution_mode == "execute":
            source_doc = docs_by_ref[str(ref)]
            execution_result = _execute_spec_first_pass(
                repo_root=repo_root,
                source_doc=source_doc,
                validated=validated,
                dry_run=dry_run,
            )
            executed = bool(execution_result.get("written"))
    elif flow_name == "backlog-groom":
        if execution_mode == "execute":
            source_doc = docs_by_ref[str(ref)]
            execution_result = _execute_backlog_groom(
                repo_root=repo_root,
                source_doc=source_doc,
                validated=validated,
                dry_run=dry_run,
            )
            executed = bool(execution_result.get("written"))
    elif flow_name == "commit-all":
        raise SystemExit("Internal error: commit-all should route through cmd_assist_commit_all.")
    elif flow_name == "prepare-release":
        raise SystemExit("Internal error: prepare-release should route through cmd_assist_prepare_release.")
    elif flow_name == "publish-release":
        raise SystemExit("Internal error: publish-release should route through cmd_assist_publish_release.")

    result_status = "degraded" if degraded_reasons else "ok"
    audit_path = (repo_root / audit_log).resolve()
    measurement_path = (repo_root / measurement_log).resolve()
    confidence = None
    if flow_name == "next-step":
        confidence = float(validated["decision"]["confidence"])
    elif isinstance(validated, dict) and "confidence" in validated:
        confidence = float(validated["confidence"])
    review_recommended = bool(degraded_reasons) or (confidence is not None and confidence < 0.7)
    if not dry_run:
        append_jsonl_record(
            audit_path,
            build_hybrid_audit_record(
                flow_name=flow_name,
                result_status=result_status,
                backend_status=backend_status,
                context_bundle=context_bundle,
                raw_payload=raw_payload,
                validated_payload=validated,
                transport=transport,
                degraded_reasons=degraded_reasons,
                execution_result=execution_result,
            ),
        )
        append_jsonl_record(
            measurement_path,
            build_measurement_record(
                flow_name=flow_name,
                backend_status=backend_status,
                result_status=result_status,
                confidence=confidence,
                degraded_reasons=degraded_reasons,
                review_recommended=review_recommended,
                execution_path_override=(
                    "cache-hit"
                    if cache_hit
                    else ("deterministic-preclassified" if preclassified_result is not None else None)
                ),
                cache_hit=cache_hit,
            ),
        )
        if (
            preclassified_result is None
            and cache_eligible
            and not cache_hit
            and result_status == "ok"
            and isinstance(validated, dict)
            and isinstance(transport, dict)
            and _hybrid_result_cache_enabled(config)
        ):
            _write_hybrid_result_cache_entry(
                cache_path=cache_path,
                cache_key=cache_key,
                diff_fingerprint=diff_fingerprint,
                ttl_seconds=_hybrid_result_cache_ttl_seconds(config),
                flow_name=flow_name,
                requested_backend=requested_backend,
                model_selection=model_selection,
                backend_status=backend_status,
                result_status=result_status,
                raw_payload=raw_payload if isinstance(raw_payload, dict) else None,
                validated_payload=validated,
                transport=transport,
                confidence=confidence,
                review_recommended=review_recommended,
            )
    return {
        "command": "assist",
        "assist_kind": "run",
        "flow": flow_name,
        "seed_ref": ref,
        "backend_requested": requested_backend,
        "backend_used": backend_status.selected_backend,
        "backend_status": backend_status.to_dict(),
        "active_model_profile": active_model_profile,
        "result_status": result_status,
        "degraded_reasons": degraded_reasons,
        "context_bundle": context_bundle,
        "raw_result": raw_payload,
        "result": validated,
        "transport": transport,
        "cache_hit": cache_hit,
        "result_cache_path": _rel(repo_root, cache_path),
        "executed": executed,
        "execution_mode": execution_mode,
        "execution_result": execution_result,
        "audit_log": _rel(repo_root, audit_path),
        "measurement_log": _rel(repo_root, measurement_path),
        "review_recommended": review_recommended,
        "ok": True,
    }


def cmd_assist_run(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    payload = _run_hybrid_assist(
        repo_root,
        flow_name=args.flow_name,
        ref=getattr(args, "ref", None),
        intent=getattr(args, "intent", None),
        requested_backend=args.backend or _hybrid_default_backend(config),
        requested_model_profile=getattr(args, "model_profile", None),
        requested_model=args.model,
        ollama_host=args.ollama_host or _hybrid_default_host(config),
        timeout_seconds=args.timeout or _hybrid_default_timeout(config),
        context_mode=args.context_mode,
        profile=args.profile,
        include_graph=args.include_graph,
        include_registry=args.include_registry,
        include_doctor=args.include_doctor,
        execution_mode=args.execution_mode,
        audit_log=args.audit_log or _hybrid_audit_log(config),
        measurement_log=args.measurement_log or _hybrid_measurement_log(config),
        config=config,
        dry_run=args.dry_run,
    )
    payload["config_path"] = _rel(repo_root, config_path) if config_path is not None else None
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_commit_all(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": args.backend or _hybrid_default_backend(config),
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": args.include_graph,
        "include_registry": args.include_registry,
        "include_doctor": args.include_doctor,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }
    plan_payload = _run_hybrid_assist(flow_name="commit-plan", ref=None, **base_kwargs)
    root_message_payload = _run_hybrid_assist(flow_name="commit-message", ref=None, **base_kwargs)
    execution_result = None
    executed = False
    if args.execution_mode == "execute":
        plan = plan_payload["result"]
        steps = plan["steps"]
        step_results = []
        for step in steps:
            target_repo = repo_root / "logics" / "skills" if step["scope"] == "submodule" else repo_root
            target_snapshot = collect_git_snapshot(target_repo, refresh=True)
            if not target_snapshot.get("has_changes"):
                step_results.append(
                    {
                        "scope": step["scope"],
                        "message": None,
                        "stdout": "",
                        "stderr": "",
                        "skipped": True,
                        "reason": "working-tree-clean",
                    }
                )
                continue
            message_payload = _run_hybrid_assist(
                flow_name="commit-message",
                ref=None,
                repo_root=target_repo,
                requested_backend=args.backend or _hybrid_default_backend(config),
                requested_model_profile=getattr(args, "model_profile", None),
                requested_model=args.model,
                ollama_host=args.ollama_host or _hybrid_default_host(config),
                timeout_seconds=args.timeout or _hybrid_default_timeout(config),
                context_mode=args.context_mode,
                profile=args.profile,
                include_graph=args.include_graph,
                include_registry=args.include_registry,
                include_doctor=args.include_doctor,
                execution_mode="suggestion-only",
                audit_log=args.audit_log or _hybrid_audit_log(config),
                measurement_log=args.measurement_log or _hybrid_measurement_log(config),
                config=config,
                dry_run=True,
            )
            message = message_payload["result"]["subject"]
            commit_result = execute_commit_step(target_repo, message)
            step_results.append({"scope": step["scope"], "message": message, **commit_result})
        execution_result = {"steps": step_results}
        executed = True
    payload = {
        "command": "assist",
        "assist_kind": "commit-all",
        "flow": "commit-all",
        "plan": plan_payload["result"],
        "root_message": root_message_payload["result"],
        "executed": executed,
        "execution_mode": args.execution_mode,
        "execution_result": execution_result,
        "backend_requested": plan_payload["backend_requested"],
        "backend_used": plan_payload["backend_used"],
        "audit_log": plan_payload["audit_log"],
        "measurement_log": plan_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_prepare_release(args: argparse.Namespace) -> dict[str, object]:
    import re

    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": args.backend or _hybrid_default_backend(config),
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": args.include_graph,
        "include_registry": args.include_registry,
        "include_doctor": args.include_doctor,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }

    # Capture the git snapshot before any assist calls so audit log creation does not
    # pollute the working-tree status check.
    git_snapshot = collect_git_snapshot(repo_root, refresh=True)

    # release-changelog-status is policy-deterministic; always use auto so the backend
    # policy routes it correctly regardless of what the operator requested.
    changelog_status_payload = _run_hybrid_assist(
        flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
    )
    validation_payload = _run_hybrid_assist(flow_name="validation-checklist", ref=None, **base_kwargs)
    diff_risk_payload = _run_hybrid_assist(flow_name="diff-risk", ref=None, **base_kwargs)

    changelog_status = _rdict(changelog_status_payload["result"])
    changelog_ready = bool(changelog_status.get("exists", False))
    already_published = bool(changelog_status.get("already_published", False))
    version_mismatch = bool(changelog_status.get("version_mismatch", False))
    has_uncommitted = bool(git_snapshot.get("has_changes", False))
    readme_badge_ok = changelog_status.get("readme_badge_ok")
    version = str(changelog_status.get("version", "0.0.0"))

    prep_steps: list[str] = []
    prep_errors: list[str] = []

    if args.execution_mode == "execute":
        if already_published:
            next_version = str(changelog_status.get("next_version") or "").strip() or _next_patch_release_version(version)
            if next_version:
                if not args.dry_run:
                    updated_paths = _update_release_version_artifacts(repo_root, next_version)
                    if updated_paths:
                        prep_steps.append(f"bumped release version to {next_version}")
                    else:
                        prep_steps.append(f"release version already aligned at {next_version}")
                else:
                    prep_steps.append(f"(dry-run) would bump release version to {next_version}")

                collect_git_snapshot(repo_root, refresh=True)
                refreshed_status_payload = _run_hybrid_assist(
                    flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
                )
                changelog_status = _rdict(refreshed_status_payload["result"])
                changelog_ready = bool(changelog_status.get("exists", False))
                already_published = bool(changelog_status.get("already_published", False))
                version_mismatch = bool(changelog_status.get("version_mismatch", False))
                readme_badge_ok = changelog_status.get("readme_badge_ok")
                version = str(changelog_status.get("version", next_version))

        if version_mismatch:
            if not args.dry_run:
                _update_release_version_artifacts(repo_root, version)
                prep_steps.append("updated VERSION to match package.json")
                version_mismatch = False
            else:
                prep_steps.append("(dry-run) would update VERSION to match package.json")

        # Step 1: generate changelog via AI if missing
        if not changelog_ready:
            gen_payload = _run_hybrid_assist(flow_name="generate-changelog", ref=None, **base_kwargs)
            gen_result = _rdict(gen_payload["result"])
            changelog_content = str(gen_result.get("content", ""))
            relative_path = str(changelog_status.get("relative_path", f"changelogs/CHANGELOGS_{version.replace('.', '_')}.md"))
            changelog_file = repo_root / relative_path
            changelog_file.parent.mkdir(parents=True, exist_ok=True)
            if not args.dry_run:
                changelog_file.write_text(changelog_content, encoding="utf-8")
                prep_steps.append(f"wrote {relative_path}")
                changelog_ready = True
                collect_git_snapshot(repo_root, refresh=True)
            else:
                prep_steps.append(f"(dry-run) would write {relative_path}")

        # Step 2: update README version badge if stale
        if readme_badge_ok is False:
            for readme_name in ("README.md", "readme.md", "Readme.md"):
                readme_path = repo_root / readme_name
                if readme_path.is_file():
                    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
                    updated = re.sub(r"version-v[\d]+\.[\d]+\.[\d]+", f"version-v{version}", readme_text)
                    updated = re.sub(r"version/[\d]+\.[\d]+\.[\d]+", f"version/{version}", updated)
                    if updated != readme_text:
                        if not args.dry_run:
                            readme_path.write_text(updated, encoding="utf-8")
                            prep_steps.append(f"updated version badge in {readme_name}")
                            collect_git_snapshot(repo_root, refresh=True)
                        else:
                            prep_steps.append(f"(dry-run) would update version badge in {readme_name}")
                    break

        # Step 3: commit any prep changes
        if prep_steps and any("(dry-run)" not in s for s in prep_steps):
            try:
                execute_commit_step(repo_root, f"Prepare {version} release")
                prep_steps.append(f"committed prep changes for {version}")
                has_uncommitted = False
            except Exception as exc:  # noqa: BLE001
                prep_errors.append(str(exc))

        # Re-evaluate readiness after prep
        if not prep_errors:
            collect_git_snapshot(repo_root, refresh=True)
            updated_status_payload = _run_hybrid_assist(
                flow_name="release-changelog-status", ref=None, **{**base_kwargs, "requested_backend": "auto"}
            )
            changelog_status = _rdict(updated_status_payload["result"])
            changelog_ready = bool(changelog_status.get("exists", False))
            already_published = bool(changelog_status.get("already_published", False))
            version_mismatch = bool(changelog_status.get("version_mismatch", False))

    ready = changelog_ready and not has_uncommitted and not already_published and not version_mismatch

    payload = {
        "command": "assist",
        "assist_kind": "prepare-release",
        "flow": "prepare-release",
        "changelog_status": changelog_status,
        "validation_checklist": validation_payload["result"],
        "diff_risk": diff_risk_payload["result"],
        "git_snapshot": git_snapshot,
        "ready": ready,
        "execution_mode": args.execution_mode,
        "prep_steps": prep_steps,
        "prep_errors": prep_errors,
        "backend_requested": changelog_status_payload["backend_requested"],
        "backend_used": changelog_status_payload["backend_used"],
        "audit_log": changelog_status_payload["audit_log"],
        "measurement_log": changelog_status_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def cmd_assist_publish_release(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _find_repo_root(Path.cwd())
    config, config_path = _effective_config(repo_root)
    base_kwargs = {
        "repo_root": repo_root,
        "requested_backend": "auto",
        "requested_model_profile": getattr(args, "model_profile", None),
        "requested_model": args.model,
        "ollama_host": args.ollama_host or _hybrid_default_host(config),
        "timeout_seconds": args.timeout or _hybrid_default_timeout(config),
        "context_mode": args.context_mode,
        "profile": args.profile,
        "include_graph": False,
        "include_registry": False,
        "include_doctor": False,
        "execution_mode": "suggestion-only",
        "audit_log": args.audit_log or _hybrid_audit_log(config),
        "measurement_log": args.measurement_log or _hybrid_measurement_log(config),
        "config": config,
        "dry_run": args.dry_run,
    }

    # Capture git snapshot before assist calls.
    git_snapshot = collect_git_snapshot(repo_root, refresh=True)

    changelog_status_payload = _run_hybrid_assist(
        flow_name="release-changelog-status", ref=None, **base_kwargs
    )
    changelog_status = _rdict(changelog_status_payload["result"])
    release_branch = _release_branch_status(repo_root)
    changelog_ready = bool(changelog_status.get("exists", False))
    already_published = bool(changelog_status.get("already_published", False))
    version_mismatch = bool(changelog_status.get("version_mismatch", False))
    has_uncommitted = bool(git_snapshot.get("has_changes", False))
    ready = changelog_ready and not has_uncommitted and not already_published and not version_mismatch

    publish_result: dict[str, object] | None = None
    executed = False

    if args.execution_mode == "execute":
        _plugin_relative = repo_root / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
        _kit_direct = repo_root / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
        publish_script = _plugin_relative if _plugin_relative.is_file() else _kit_direct
        if not publish_script.is_file():
            publish_result = {"ok": False, "error": f"Publish script not found: {publish_script}"}
        elif not ready:
            blocking: list[str] = []
            if not changelog_ready:
                blocking.append("changelog not ready — run 'flow assist prepare-release --execution-mode execute' first")
            if already_published:
                blocking.append("version already published or tagged — bump the version before publishing again")
            if version_mismatch:
                blocking.append("VERSION is out of sync with package.json — run 'flow assist prepare-release --execution-mode execute' first")
            if has_uncommitted:
                blocking.append("uncommitted changes present")
            publish_result = {"ok": False, "error": "Release prerequisites not met.", "blocking": blocking}
        else:
            cmd = [sys.executable, str(publish_script)]
            version_override = getattr(args, "version", None)
            if version_override:
                cmd += ["--version", version_override]
            if getattr(args, "draft", False):
                cmd += ["--draft"]
            if getattr(args, "push", False):
                cmd += ["--create-tag", "--push"]
            if args.dry_run:
                cmd += ["--dry-run"]
            completed = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
            publish_result = {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "command": cmd,
            }
            executed = completed.returncode == 0
    else:
        # suggestion-only: show what would be done
        version = str(changelog_status.get("version", "0.0.0"))
        tag = str(changelog_status.get("tag", f"v{version}"))
        release_note = str(release_branch.get("suggestion", "")).strip()
        release_command = str(release_branch.get("command", "")).strip()
        release_guidance = ""
        if release_note:
            release_guidance = f"\n{release_note}"
            if release_command:
                release_guidance += f"\nSuggested command: {release_command}"
        publish_result = {
            "ok": True,
            "suggestion": (
                f"When ready, run: flow assist publish-release --execution-mode execute --push"
                f"\nThis will create tag {tag}, push main+tag, and publish the GitHub release."
                f"{release_guidance}"
                if ready
                else f"Release is not ready yet. Run 'flow assist prepare-release --execution-mode execute' first."
            ),
            "ready": ready,
        }

    payload = {
        "command": "assist",
        "assist_kind": "publish-release",
        "flow": "publish-release",
        "changelog_status": changelog_status,
        "release_branch": release_branch,
        "git_snapshot": git_snapshot,
        "ready": ready,
        "executed": executed,
        "execution_mode": args.execution_mode,
        "publish_result": publish_result,
        "backend_requested": changelog_status_payload["backend_requested"],
        "backend_used": changelog_status_payload["backend_used"],
        "audit_log": changelog_status_payload["audit_log"],
        "measurement_log": changelog_status_payload["measurement_log"],
        "config_path": _rel(repo_root, config_path) if config_path is not None else None,
        "ok": True,
    }
    if args.format == "text":
        print(json.dumps(payload, indent=2, sort_keys=True))
    return payload



__all__ = [name for name in globals() if not name.startswith("__")]
