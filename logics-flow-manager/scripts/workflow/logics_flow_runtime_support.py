#!/usr/bin/env python3
from __future__ import annotations

from logics_flow_core import *  # noqa: F401,F403
from logics_flow_hybrid_helpers import (
    DEFAULT_HYBRID_HOST,
    DEFAULT_HYBRID_MODEL,
    DEFAULT_HYBRID_MODEL_PROFILE,
    _configured_flow_contract,
)
from logics_flow_hybrid_runtime_core import HybridBackendStatus

def _cached_backend_status(cached_entry: dict[str, object], requested_backend: str) -> HybridBackendStatus:
    cached_status = cached_entry.get("backend_status") if isinstance(cached_entry, dict) else {}
    status_dict = cached_status if isinstance(cached_status, dict) else {}
    return HybridBackendStatus(
        requested_backend=requested_backend,
        selected_backend=str(status_dict.get("selected_backend", "codex")),
        host=str(status_dict.get("host", DEFAULT_HYBRID_HOST)),
        model_profile=str(status_dict.get("model_profile", DEFAULT_HYBRID_MODEL_PROFILE)),
        model_family=str(status_dict.get("model_family", "")),
        configured_model=str(status_dict.get("configured_model", DEFAULT_HYBRID_MODEL)),
        model=str(status_dict.get("model", DEFAULT_HYBRID_MODEL)),
        ollama_reachable=bool(status_dict.get("ollama_reachable", False)),
        model_available=bool(status_dict.get("model_available", True)),
        healthy=True,
        reasons=[],
        response_time_ms=None,
        version=None,
        selection_reason="cache-hit",
        policy_mode=status_dict.get("policy_mode"),
    )


LOW_RISK_GENERATED_PATHS = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "Cargo.lock",
    "Pipfile.lock",
    "poetry.lock",
    "composer.lock",
}


def _is_low_risk_generated_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    lowered = normalized.lower()
    return (
        filename in LOW_RISK_GENERATED_PATHS
        or ".generated." in lowered
        or lowered.endswith(".snap")
        or lowered.startswith("dist/")
        or lowered.startswith("build/")
    )


def _is_schema_or_migration_path(path: str) -> bool:
    lowered = path.strip().replace("\\", "/").lower()
    return (
        "/migrations/" in lowered
        or lowered.startswith("migrations/")
        or "/migration/" in lowered
        or lowered.startswith("migration/")
        or lowered.endswith("schema.prisma")
        or lowered.endswith("schema.sql")
        or lowered.endswith("/schema.ts")
        or lowered.endswith("/schema.js")
        or "/db/schema" in lowered
        or "/alembic/" in lowered
    )


def _deterministic_preclassified_result(flow_name: str, context_bundle: dict[str, object]) -> dict[str, object] | None:
    if flow_name not in {"diff-risk", "windows-compat-risk"}:
        return None
    git_snapshot = context_bundle.get("git_snapshot", {})
    changed_paths = list(git_snapshot.get("changed_paths", [])) if isinstance(git_snapshot, dict) else []
    if not changed_paths:
        return {
            "reason": "empty-diff",
            "validated": {
                "risk": "low",
                "summary": "Deterministic pre-classifier marked the empty diff as low risk.",
                "drivers": ["No changed paths were detected in the working tree."],
                "confidence": 0.97,
                "rationale": "An empty diff does not require AI classification.",
            },
        }
    if any(_is_schema_or_migration_path(path) for path in changed_paths):
        return {
            "reason": "schema-or-migration",
            "validated": {
                "risk": "high",
                "summary": "Deterministic pre-classifier escalated the diff because schema or migration files changed.",
                "drivers": ["The change surface includes schema or migration files that require careful review."],
                "confidence": 0.95,
                "rationale": "Schema and migration changes are treated as high risk without an AI round-trip.",
            },
        }
    if all(_is_low_risk_generated_path(path) for path in changed_paths):
        return {
            "reason": "lock-or-generated-only",
            "validated": {
                "risk": "low",
                "summary": "Deterministic pre-classifier marked the diff as low risk because it only touches lock or generated files.",
                "drivers": ["Only lock-file or generated-artifact paths changed."],
                "confidence": 0.94,
                "rationale": "Lock-file-only and generated-only diffs are handled deterministically before any AI dispatch.",
            },
        }
    return None


def _prepare_hybrid_context_bundle(
    repo_root: Path,
    *,
    flow_name: str,
    ref: str | None,
    intent: str | None = None,
    context_mode: str | None,
    profile: str,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    audit_log: str,
    measurement_log: str,
    config: dict[str, object],
) -> tuple[dict[str, object], dict[str, object] | None]:
    context_bundle = _build_hybrid_context(
        repo_root,
        flow_name,
        ref=ref,
        intent=intent,
        context_mode=context_mode,
        profile=profile,
        include_graph=include_graph,
        include_registry=include_registry,
        include_doctor=include_doctor,
        config=config,
    )
    context_bundle["repo_root"] = str(repo_root)
    validation_payload = None
    if flow_name in {"validation-summary", "doc-consistency", "review-checklist"}:
        validation_payload = _hybrid_validation_payload(repo_root)
        context_bundle["validation_payload"] = validation_payload
    if flow_name == "hybrid-insights-explainer":
        context_bundle["roi_report"] = build_hybrid_roi_report(
            repo_root=repo_root,
            audit_log=(repo_root / audit_log).resolve(),
            measurement_log=(repo_root / measurement_log).resolve(),
        )
    return context_bundle, validation_payload


def _resolve_runtime_context_profile(
    *,
    flow_name: str,
    requested_profile: str | None,
    backend_status: HybridBackendStatus,
) -> tuple[str, str | None, str]:
    resolved_profile = requested_profile or str(default_context_spec(flow_name)["profile"])
    if flow_name != "handoff-packet":
        return resolved_profile, None, resolved_profile
    if requested_profile == "deep":
        return resolved_profile, None, resolved_profile
    if resolved_profile != "deep":
        return resolved_profile, None, resolved_profile
    if backend_status.selected_backend not in {"openai", "gemini", "codex"}:
        return resolved_profile, None, resolved_profile
    return "normal", "profile-downgrade", resolved_profile


def _deterministic_backend_status(
    *,
    requested_backend: str,
    model_selection: dict[str, object],
) -> HybridBackendStatus:
    return HybridBackendStatus(
        requested_backend=requested_backend,
        selected_backend="deterministic",
        host=DEFAULT_HYBRID_HOST,
        model_profile=str(model_selection["name"]),
        model_family=str(model_selection["family"]),
        configured_model=str(model_selection["configured_model"]),
        model=str(model_selection["resolved_model"]),
        ollama_reachable=False,
        model_available=True,
        healthy=True,
        reasons=[],
        response_time_ms=None,
        version=None,
        selection_reason="deterministic-preclassified",
        policy_mode=None,
    )


def _build_hybrid_context(
    repo_root: Path,
    flow_name: str,
    *,
    ref: str | None,
    intent: str | None = None,
    context_mode: str | None,
    profile: str | None,
    include_graph: bool | None,
    include_registry: bool | None,
    include_doctor: bool | None,
    config: dict[str, object],
) -> dict[str, object]:
    spec = default_context_spec(flow_name)
    resolved_mode = context_mode or spec["mode"]
    resolved_profile = profile or spec["profile"]
    resolved_graph = spec["include_graph"] if include_graph is None else include_graph
    resolved_registry = spec["include_registry"] if include_registry is None else include_registry
    resolved_doctor = spec["include_doctor"] if include_doctor is None else include_doctor

    bundle: dict[str, object] = {
        "schema_version": CURRENT_WORKFLOW_SCHEMA_VERSION,
        "assist_schema_version": build_shared_hybrid_contract()["schema_version"],
        "flow": flow_name,
        "seed_ref": ref,
        "context_profile": {
            "mode": resolved_mode,
            "profile": resolved_profile,
            "include_graph": resolved_graph,
            "include_registry": resolved_registry,
            "include_doctor": resolved_doctor,
        },
        "contract": _configured_flow_contract(flow_name, config),
        "git_snapshot": collect_git_snapshot(repo_root),
        "claude_bridge": _claude_bridge_status(repo_root),
        "claude_bridge_available": _claude_bridge_available(repo_root),
    }
    if ref:
        bundle["context_pack"] = _build_context_pack(repo_root, ref, mode=resolved_mode, profile=resolved_profile, config=config)
        if resolved_graph:
            bundle["graph"] = _dispatcher_graph_slice(repo_root, ref, config=config)
    else:
        bundle["context_pack"] = {
            "ref": None,
            "mode": resolved_mode,
            "profile": resolved_profile,
            "docs": [],
            "budgets": {"max_docs": 0},
            "changed_paths": bundle["git_snapshot"]["changed_paths"],
            "estimates": {"doc_count": 0, "char_count": 0},
        }
    normalized_intent = " ".join(str(intent or "").split()).strip()
    if normalized_intent:
        bundle["operator_input"] = {"intent": normalized_intent}
    if resolved_registry:
        bundle["registry"] = _dispatcher_registry_summary(repo_root, config=config)
    if resolved_doctor:
        doctor_payload = _doctor_payload(repo_root, config=config)
        bundle["doctor"] = {
            "ok": doctor_payload["ok"],
            "issue_count": len(doctor_payload["issues"]),
            "issues": doctor_payload["issues"],
        }
    return bundle


def _section_bullets(doc: WorkflowDocModel, heading: str) -> list[str]:
    bullets: list[str] = []
    for line in doc.sections.get(heading, []):
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            candidate = stripped[6:].strip()
        elif stripped.startswith("- [x] "):
            candidate = stripped[6:].strip()
        elif stripped.startswith("- "):
            candidate = stripped[2:].strip()
        else:
            continue
        if candidate:
            bullets.append(candidate)
    return bullets


def _replace_top_level_section(text: str, heading: str, replacement_lines: list[str]) -> str:
    lines = text.splitlines()
    section_start = None
    section_end = len(lines)
    target = f"# {heading}".strip().lower()
    for index, line in enumerate(lines):
        if line.strip().lower() == target:
            section_start = index
            break
    if section_start is None:
        return text
    for index in range(section_start + 1, len(lines)):
        if lines[index].startswith("# "):
            section_end = index
            break
    updated_lines = lines[: section_start + 1] + replacement_lines + lines[section_end:]
    return "\n".join(updated_lines).rstrip() + "\n"


def _confirmation_prompt(prompt: str, *, dry_run: bool) -> bool:
    if dry_run:
        return True
    sys.stderr.write(f"{prompt} [y/N] ")
    sys.stderr.flush()
    response = sys.stdin.readline()
    return response.strip().lower() in {"y", "yes"}


def _confidence_percentage(confidence: object, *, fallback: str = "85%") -> str:
    if isinstance(confidence, (int, float)):
        bounded = max(0.0, min(1.0, float(confidence)))
        return f"{round(bounded * 100)}%"
    return fallback


def _default_from_version(repo_root: Path) -> str:
    version_path = repo_root / "VERSION"
    if version_path.is_file():
        value = version_path.read_text(encoding="utf-8").strip()
        if value:
            return value.splitlines()[0].strip()

    package_path = repo_root / "package.json"
    if package_path.is_file():
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        version = payload.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()

    return "0.0.0"


def _resolved_from_version(repo_root: Path, value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized and normalized != "X.X.X":
            return normalized
    return _default_from_version(repo_root)


def _seed_new_doc_values(doc_kind: str, title: str, values: dict[str, str]) -> None:
    normalized_title = " ".join(title.split()).strip() or "this workflow doc"
    if doc_kind == "request":
        values["NEEDS_PLACEHOLDER"] = f"Clarify the scope and user value of {normalized_title}."
        values["CONTEXT_PLACEHOLDER"] = f"- Capture the relevant context, constraints, and stakeholders for {normalized_title}."
        values["ACCEPTANCE_PLACEHOLDER"] = f"AC1: Confirm {normalized_title} is framed clearly enough for backlog grooming."
        return

    if doc_kind == "backlog":
        values["PROBLEM_PLACEHOLDER"] = f"- Deliver the bounded slice for {normalized_title} without widening scope."
        values["ACCEPTANCE_BLOCK"] = f"- AC1: Confirm {normalized_title} delivers one coherent backlog slice."
        values["AC_TRACEABILITY_PLACEHOLDER"] = (
            f"- AC1 -> Scope: Deliver the bounded slice for {normalized_title}. "
            "Proof: capture validation evidence in this doc."
        )
        values["REQUEST_LINK_PLACEHOLDER"] = "(none yet)"
        values["TASK_LINK_PLACEHOLDER"] = "(none yet)"
        return

    if doc_kind == "task":
        values["CONTEXT_PLACEHOLDER"] = f"- Execute the bounded delivery slice for {normalized_title}."
        values["AC_TRACEABILITY_PLACEHOLDER"] = (
            f"- AC1 -> Scope: Execute the bounded delivery slice for {normalized_title}. "
            "Proof: capture validation evidence in this doc."
        )
        values["BACKLOG_LINK_PLACEHOLDER"] = "(none yet)"
        values["REQUEST_LINK_PLACEHOLDER"] = "(none yet)"


def _title_from_request_intent(intent: str) -> str:
    cleaned = " ".join(intent.split()).strip()
    cleaned = re.sub(r"^(draft|create|add|write|prepare)\s+(a|an)?\s*request\s*(for|about)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .:-")
    if not cleaned:
        return "Request draft"
    return cleaned[:1].upper() + cleaned[1:120]


def _build_authoring_args(
    *,
    repo_root: Path,
    kind: str,
    confidence: object,
    dry_run: bool,
    complexity: str = "Medium",
    status: str | None = None,
    theme: str = "Hybrid assist",
) -> argparse.Namespace:
    return argparse.Namespace(
        from_version=_default_from_version(repo_root),
        understanding="90%",
        confidence=_confidence_percentage(confidence),
        status=status or STATUS_BY_KIND_DEFAULT[kind],
        progress="0%" if DOC_KINDS[kind].include_progress else "",
        complexity=complexity if kind != "request" else "Medium",
        theme=theme,
        auto_create_product_brief=False,
        auto_create_adr=False,
        format="json",
        dry_run=dry_run,
    )


def _format_acceptance_criteria(items: list[str]) -> list[str]:
    formatted: list[str] = []
    for index, item in enumerate(items, start=1):
        normalized = " ".join(item.split()).strip().rstrip(".")
        if not normalized:
            continue
        if re.match(r"^AC\d+:", normalized, flags=re.IGNORECASE):
            formatted.append(f"- {normalized}")
        else:
            formatted.append(f"- AC{index}: {normalized}.")
    return formatted or ["- AC1: Confirm the bounded proposal is acceptable before promotion."]


def _execute_request_draft(
    *,
    repo_root: Path,
    intent: str,
    validated: dict[str, object],
    dry_run: bool,
) -> dict[str, object]:
    title = _title_from_request_intent(intent)
    if not _confirmation_prompt(f"Create request doc `{title}` in logics/request?", dry_run=dry_run):
        return {"written": False, "confirmed": False, "reason": "operator-declined"}

    planned = _reserve_doc(repo_root / DOC_KINDS["request"].directory, DOC_KINDS["request"].prefix, title, dry_run)
    args = _build_authoring_args(repo_root=repo_root, kind="request", confidence=validated.get("confidence"), dry_run=dry_run)
    template_text = _template_path(Path(__file__), DOC_KINDS["request"].template_name).read_text(encoding="utf-8")
    values = _build_template_values(args, planned.ref, title, include_progress=False, doc_kind="request")
    needs = [str(item) for item in validated.get("needs", []) if str(item).strip()]
    context = [str(item) for item in validated.get("context", []) if str(item).strip()]
    values["NEEDS_PLACEHOLDER"] = "\n- ".join(needs or ["Describe the need"])
    values["CONTEXT_PLACEHOLDER"] = "\n".join(f"- {item}" for item in (context or ["Add context and constraints"]))
    values["ACCEPTANCE_PLACEHOLDER"] = "\n- ".join(line[2:] for line in _format_acceptance_criteria(needs))
    values["REFERENCES_SECTION"] = _render_references_section(_collect_reference_items(title, intent))
    values["MERMAID_BLOCK"] = _generate_workflow_mermaid(repo_root, "request", title, values, dry_run=dry_run)
    content = _render_template(template_text, values).rstrip() + "\n"
    content, _changed = refresh_ai_context_text(content, "request")
    content, _changed = refresh_workflow_mermaid_signature_text(content, "request", repo_root=repo_root, dry_run=dry_run)
    _write(planned.path, content, dry_run)
    return {
        "written": not dry_run,
        "confirmed": True,
        "kind": "request",
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "title": title,
        "dry_run": dry_run,
    }


def _execute_spec_first_pass(
    *,
    repo_root: Path,
    source_doc: WorkflowDocModel,
    validated: dict[str, object],
    dry_run: bool,
) -> dict[str, object]:
    title = f"{source_doc.title} first-pass spec"
    if not _confirmation_prompt(f"Create spec doc `{title}` in logics/specs?", dry_run=dry_run):
        return {"written": False, "confirmed": False, "reason": "operator-declined"}

    planned = _reserve_doc(repo_root / "logics" / "specs", "spec", title, dry_run)
    template_path = Path(__file__).resolve().parents[3] / "logics-spec-writer" / "assets" / "templates" / "spec.md"
    template_text = template_path.read_text(encoding="utf-8")
    sections = [str(item) for item in validated.get("sections", []) if str(item).strip()]
    open_questions = [str(item) for item in validated.get("open_questions", []) if str(item).strip()]
    constraints = [str(item) for item in validated.get("constraints", []) if str(item).strip()]
    acceptance = _section_bullets(source_doc, "Acceptance criteria")
    values = {
        "DOC_REF": planned.ref,
        "TITLE": title,
        "FROM_VERSION": _resolved_from_version(repo_root, source_doc.indicators.get("From version")),
        "UNDERSTANDING": "90%",
        "CONFIDENCE": _confidence_percentage(validated.get("confidence")),
        "OVERVIEW": f"Derived from `{source_doc.ref}`. {str(validated.get('rationale', '')).strip()}".strip(),
        "GOAL_1": "\n- ".join(sections or ["Capture the first-pass spec structure for the backlog item."]),
        "NON_GOAL_1": "Expand implementation scope beyond the linked backlog slice without review.",
        "USE_CASE_1": f"Operators need a bounded spec draft derived from `{source_doc.ref}` before implementation starts.",
        "REQ_1": "\n- ".join(sections or ["Document the required sections for the first-pass spec."]),
        "AC_1": "\n- ".join(acceptance or ["Preserve the bounded acceptance scope from the source backlog item."]),
        "TEST_1": "\n- ".join(constraints or ["Validate the outline against the source backlog item before implementation."]),
        "QUESTION_1": "\n- ".join(open_questions or ["Which acceptance criterion needs deeper specification?"]),
    }
    content = _render_template(template_text, values).rstrip() + "\n"
    _write(planned.path, content, dry_run)
    return {
        "written": not dry_run,
        "confirmed": True,
        "kind": "spec",
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "title": title,
        "dry_run": dry_run,
    }


def _execute_backlog_groom(
    *,
    repo_root: Path,
    source_doc: WorkflowDocModel,
    validated: dict[str, object],
    dry_run: bool,
) -> dict[str, object]:
    title = str(validated.get("title", "")).strip() or source_doc.title or source_doc.ref
    if not _confirmation_prompt(f"Create backlog doc `{title}` in logics/backlog?", dry_run=dry_run):
        return {"written": False, "confirmed": False, "reason": "operator-declined"}

    source_path = (repo_root / source_doc.path).resolve()
    args = _build_authoring_args(
        repo_root=repo_root,
        kind="backlog",
        confidence=validated.get("confidence"),
        dry_run=dry_run,
        complexity=str(validated.get("complexity", "Medium")),
    )
    planned = _create_backlog_from_request(repo_root, source_path, title, args)
    acceptance_lines = _format_acceptance_criteria(
        [str(item) for item in validated.get("acceptance_criteria", []) if str(item).strip()]
    )
    notes_lines = [f"- Hybrid rationale: {str(validated.get('rationale', '')).strip()}".rstrip()]
    updated = planned.path.read_text(encoding="utf-8") if planned.path.exists() else ""
    if updated:
        updated = _replace_top_level_section(updated, "Acceptance criteria", acceptance_lines)
        updated = _replace_top_level_section(updated, "Notes", notes_lines)
        updated, _changed = refresh_ai_context_text(updated, "backlog")
        updated, _changed = refresh_workflow_mermaid_signature_text(updated, "backlog", repo_root=repo_root, dry_run=dry_run)
        _write(planned.path, updated, dry_run)
    return {
        "written": not dry_run,
        "confirmed": True,
        "kind": "backlog",
        "created_ref": planned.ref,
        "created_path": _rel(repo_root, planned.path),
        "title": title,
        "dry_run": dry_run,
    }


def _hybrid_validation_payload(repo_root: Path) -> dict[str, object]:
    commands = [
        [sys.executable, str(Path(__file__).resolve().parents[3] / "logics.py"), "lint", "--format", "json"],
        [sys.executable, str(Path(__file__).resolve().parents[3] / "logics.py"), "audit", "--group-by-doc", "--format", "json"],
        [sys.executable, str(Path(__file__).resolve().parents[3] / "logics.py"), "doctor", "--format", "json"],
    ]
    return run_validation_commands(repo_root, commands)



__all__ = [name for name in globals() if not name.startswith("__")]
