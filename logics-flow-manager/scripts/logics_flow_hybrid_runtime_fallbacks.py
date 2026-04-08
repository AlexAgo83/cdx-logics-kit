from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from logics_flow_hybrid_runtime_core import *  # noqa: F401,F403
from logics_flow_hybrid_runtime_metrics import *  # noqa: F401,F403



def build_fallback_result(
    flow_name: str,
    *,
    context_bundle: dict[str, Any],
    docs_by_ref: dict[str, WorkflowDocModel],
    validation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_ref = context_bundle.get("seed_ref")
    git_snapshot = context_bundle.get("git_snapshot", {})
    changed_paths = list(git_snapshot.get("changed_paths", []))
    if flow_name == "commit-message":
        scope = "submodule" if changed_paths and all(path.startswith("logics/skills/") or path == "logics/skills" for path in changed_paths) else "root"
        subject = _build_deterministic_commit_subject(git_snapshot)
        return {
            "subject": subject[:72],
            "body": _summarize_changed_paths(context_bundle),
            "scope": scope,
            "confidence": 0.64,
            "rationale": "Fallback commit message derived from changed-path categories.",
        }
    if flow_name == "pr-summary":
        return {
            "title": "Hybrid assist runtime and delivery automation updates",
            "summary": _summarize_changed_paths(context_bundle),
            "highlights": [
                "Adds shared hybrid runtime contracts and backend selection.",
                "Keeps risky execution outside raw model output.",
                "Updates delivery tooling and workflow surfaces around the new runtime.",
            ],
            "confidence": 0.62,
            "rationale": "Fallback PR summary derived from change categories.",
        }
    if flow_name == "changelog-summary":
        entries = ["Add hybrid assist runtime contracts and backend selection."]
        if git_snapshot.get("touches_plugin"):
            entries.append("Expose hybrid assist health and action surfaces in the VS Code plugin.")
        if git_snapshot.get("touches_runtime"):
            entries.append("Add bounded hybrid assist flows for delivery summaries, triage, and planning.")
        return {
            "title": "Hybrid assist delivery updates",
            "entries": entries,
            "confidence": 0.62,
            "rationale": "Fallback changelog summary derived from changed surfaces.",
        }
    if flow_name == "validation-summary":
        if validation_payload is None:
            validation_payload = {}
        statuses = validation_payload.get("statuses", [])
        overall = "pass" if statuses and all(item["ok"] for item in statuses) else "warning"
        if statuses and any(not item["ok"] for item in statuses):
            overall = "fail"
        return {
            "overall": overall,
            "summary": "Validation summary derived from the shared hybrid validation run.",
            "highlights": [item["summary"] for item in statuses] if statuses else ["No validation commands were executed."],
            "commands": [item["command"] for item in statuses] if statuses else [],
            "confidence": 0.7 if statuses else 0.45,
            "rationale": "Fallback validation summary reuses structured command results.",
        }
    if flow_name == "next-step":
        return _fallback_next_step(str(seed_ref), docs_by_ref).to_dict()
    if flow_name == "request-draft":
        operator_input = context_bundle.get("operator_input", {})
        raw_intent = operator_input.get("intent") if isinstance(operator_input, dict) else None
        normalized_intent = " ".join(str(raw_intent or "").split()).strip()
        needs = [normalized_intent or "Clarify the operator intent before drafting the request."]
        context = [
            "Capture the user problem, desired outcome, and why the request matters now.",
            "Keep the request bounded so it can promote cleanly into one or more backlog slices.",
        ]
        return {
            "needs": needs,
            "context": context,
            "confidence": 0.61,
            "rationale": "Fallback request draft uses the supplied operator intent and the shared Logics request posture.",
        }
    if flow_name == "spec-first-pass":
        doc = docs_by_ref[str(seed_ref)]
        acceptance_bullets = _section_bullets(doc, "Acceptance criteria")
        sections = [
            "Summary",
            "Scope",
            "Acceptance criteria",
            "Validation",
            "Open questions",
        ]
        open_questions = [
            "Which acceptance criteria need the deepest validation or traceability detail?",
        ]
        if not acceptance_bullets:
            open_questions.append("Acceptance criteria are missing or too thin; confirm the intended delivery contract.")
        constraints = [
            f"Stay aligned with `{doc.ref}` and keep the outline proposal-only for operator review.",
            "Do not write files or assume implementation details that are not present in the backlog item.",
        ]
        return {
            "sections": sections,
            "open_questions": open_questions,
            "constraints": constraints,
            "confidence": 0.64,
            "rationale": "Fallback spec outline is derived from the backlog item structure and acceptance-criteria surface.",
        }
    if flow_name == "backlog-groom":
        doc = docs_by_ref[str(seed_ref)]
        needs_bullets = _section_bullets(doc, "Needs")
        acceptance_bullets = _section_bullets(doc, "Acceptance criteria")
        candidate_criteria = acceptance_bullets or needs_bullets
        normalized_title = doc.title.strip() or doc.ref
        complexity = "Medium"
        if len(candidate_criteria) >= 4:
            complexity = "High"
        elif len(candidate_criteria) <= 1:
            complexity = "Low"
        return {
            "title": normalized_title[:120],
            "complexity": complexity,
            "acceptance_criteria": candidate_criteria[:5] or ["Define the bounded backlog slice and its acceptance criteria."],
            "confidence": 0.66,
            "rationale": "Fallback backlog grooming is derived from the request needs and acceptance-criteria surface.",
        }
    if flow_name == "triage":
        doc = docs_by_ref[str(seed_ref)]
        acceptance_count = _count_section_bullets(doc, "Acceptance criteria")
        needs_count = _count_section_bullets(doc, "Needs")
        if not acceptance_count and doc.kind != "task":
            classification = "needs-clarification"
            summary = "The doc is still missing acceptance criteria."
        elif doc.kind in {"request", "backlog"} and max(acceptance_count, needs_count) > 3:
            classification = "needs-split"
            summary = "The scope looks broad enough to justify a bounded split review."
        elif doc.indicators.get("Status") == "Blocked":
            classification = "blocked"
            summary = "The target doc is explicitly marked blocked."
        else:
            classification = "ready"
            summary = "The target doc looks ready for the next bounded workflow step."
        return {
            "target_ref": doc.ref,
            "classification": classification,
            "summary": summary,
            "next_actions": ["Review the suggested next-step flow.", "Confirm the target status and linked refs."],
            "confidence": 0.68,
            "rationale": "Fallback triage is based on status, acceptance-criteria presence, and scope size.",
        }
    if flow_name == "handoff-packet":
        doc = docs_by_ref[str(seed_ref)]
        files = [doc.path, *changed_paths[:5]]
        validations = [
            "python logics/skills/logics.py lint",
            "python logics/skills/logics.py audit --group-by-doc",
        ]
        return {
            "target_ref": doc.ref,
            "goal": f"Move `{doc.ref}` forward without losing workflow traceability.",
            "why_now": "The hybrid runtime needs a compact operator handoff packet.",
            "files_of_interest": list(dict.fromkeys(files)),
            "validation_targets": validations,
            "risks": ["Do not bypass the shared safety taxonomy.", "Keep workflow docs and runtime surfaces aligned."],
            "confidence": 0.63,
            "rationale": "Fallback handoff packet combines workflow target context with current changed paths.",
        }
    if flow_name == "suggest-split":
        doc = docs_by_ref[str(seed_ref)]
        source_bullets = _section_bullets(doc, "Acceptance criteria") or _section_bullets(doc, "Needs")
        titles = [bullet[:80] for bullet in source_bullets[:2] if bullet]
        if len(titles) < 2:
            titles = [f"{doc.title} slice A", f"{doc.title} slice B"]
        return {
            "target_ref": doc.ref,
            "suggested_titles": titles,
            "summary": "Fallback split suggestion keeps the source at the minimum coherent slice count.",
            "confidence": 0.61,
            "rationale": "Fallback split suggestion is derived from acceptance-criteria or needs bullets.",
        }
    if flow_name == "diff-risk":
        risk = "low"
        drivers: list[str] = []
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            risk = "high"
            drivers.append("Diff spans both runtime scripts and plugin surfaces.")
        elif git_snapshot.get("touches_runtime") or git_snapshot.get("touches_plugin"):
            risk = "medium"
            drivers.append("Diff touches execution or UI surfaces beyond docs only.")
        else:
            drivers.append("Diff is mostly limited to docs and light metadata.")
        if git_snapshot.get("touches_tests"):
            drivers.append("Tests are changing alongside implementation.")
        return {
            "risk": risk,
            "summary": "Fallback risk triage is based on changed-path categories.",
            "drivers": drivers,
            "confidence": 0.66,
            "rationale": "Fallback risk triage uses the shared git snapshot.",
        }
    if flow_name == "commit-plan":
        touches_submodule = git_snapshot.get("touches_submodule")
        submodule_has_changes = git_snapshot.get("submodule_has_changes")
        root_paths = [path for path in changed_paths if not path.startswith("logics/skills/") and path != "logics/skills"]
        if touches_submodule and submodule_has_changes and root_paths:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the kit/runtime changes inside logics/skills first.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Commit the parent repo updates and submodule pointer after the kit commit.", "paths": root_paths[:8] or ["logics/skills"]},
                ],
                "confidence": 0.86,
                "rationale": "Separate submodule and parent commits keep git history coherent.",
            }
        if touches_submodule and submodule_has_changes:
            return {
                "strategy": "submodule-then-root",
                "steps": [
                    {"scope": "submodule", "summary": "Commit the nested logics/skills changes.", "paths": ["logics/skills"]},
                    {"scope": "root", "summary": "Record the updated submodule pointer in the parent repo.", "paths": ["logics/skills"]},
                ],
                "confidence": 0.78,
                "rationale": "Submodule changes still require a parent pointer update.",
            }
        if touches_submodule:
            return {
                "strategy": "single",
                "steps": [{"scope": "root", "summary": "Commit the updated logics/skills submodule pointer in the parent repo.", "paths": root_paths[:8] or ["logics/skills"]}],
                "confidence": 0.82,
                "rationale": "The nested logics/skills repo is already clean, so only the parent pointer update still needs a commit.",
            }
        return {
            "strategy": "single",
            "steps": [{"scope": "root", "summary": "Commit all staged root-repo changes together.", "paths": changed_paths[:8] or ["."]}],
            "confidence": 0.74,
            "rationale": "No separate submodule step is required for the current diff.",
        }
    if flow_name == "closure-summary":
        doc = docs_by_ref[str(seed_ref)]
        linked = sorted({ref for refs in doc.refs.values() for ref in refs if ref in docs_by_ref})
        delivered = [doc.title, *[docs_by_ref[ref].title for ref in linked[:3]]]
        return {
            "target_ref": doc.ref,
            "summary": f"Fallback closure summary for `{doc.ref}` built from linked workflow docs and status metadata.",
            "delivered": delivered,
            "validations": ["python logics/skills/logics.py lint", "python logics/skills/logics.py audit --group-by-doc"],
            "remaining_risks": ["Confirm final validation results before closing delivery."],
            "confidence": 0.63,
            "rationale": "Fallback closure summary uses the workflow graph and standard validations.",
        }
    if flow_name == "validation-checklist":
        checks = ["python logics/skills/logics.py lint", "python logics/skills/logics.py audit --group-by-doc"]
        profile = "docs-only"
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            profile = "mixed"
            checks.extend(["python3 -m unittest discover -s logics/skills/tests -p 'test_*.py' -v", "npm test"])
        elif git_snapshot.get("touches_runtime"):
            profile = "runtime"
            checks.append("python3 -m unittest discover -s logics/skills/tests -p 'test_*.py' -v")
        elif git_snapshot.get("touches_plugin"):
            profile = "plugin"
            checks.extend(["npm test", "npm run test:smoke"])
        return {
            "profile": profile,
            "checks": checks,
            "confidence": 0.78,
            "rationale": "Fallback validation checklist is derived from the changed-path categories.",
        }
    if flow_name == "doc-consistency":
        issues = []
        follow_up = []
        statuses = validation_payload.get("statuses", []) if validation_payload else []
        for item in statuses:
            if not item["ok"]:
                issues.append(item["summary"])
                follow_up.append(f"Re-run or repair `{item['command']}`.")
        overall = "clean" if not issues else "issues-found"
        if not issues:
            issues = ["No consistency issues were detected by the fallback review."]
            follow_up = ["Keep the workflow audit and lint surfaces green."]
        return {
            "overall": overall,
            "summary": "Fallback doc-consistency review is based on workflow audit and lint results.",
            "issues": issues,
            "follow_up": follow_up,
            "confidence": 0.72 if statuses else 0.45,
            "rationale": "Fallback doc consistency review reuses the shared validation results.",
        }
    if flow_name == "changed-surface-summary":
        return {
            "summary": _summarize_changed_paths(context_bundle),
            "changed_paths": changed_paths or ["No changed paths detected."],
            "categories": _deterministic_categories(git_snapshot),
            "confidence": 0.9,
            "rationale": "Changed-surface summary is derived directly from the shared git snapshot.",
        }
    if flow_name == "release-changelog-status":
        return _resolve_release_changelog_status(Path(context_bundle.get("repo_root", ".")))
    if flow_name == "test-impact-summary":
        return _deterministic_test_impact_summary(Path(context_bundle.get("repo_root", ".")), changed_paths)
    if flow_name == "hybrid-insights-explainer":
        roi_report = context_bundle.get("roi_report", {})
        return _deterministic_hybrid_insights_explainer(roi_report if isinstance(roi_report, dict) else {})
    if flow_name == "windows-compat-risk":
        risk = "low"
        drivers: list[str] = []
        if any(path.endswith((".ps1", ".bat", ".cmd")) for path in changed_paths):
            risk = "medium"
            drivers.append("Windows-specific script surfaces changed and should be rechecked for entrypoint drift.")
        if any(path.startswith("scripts/") or path.endswith((".mjs", ".py")) for path in changed_paths):
            risk = "medium"
            drivers.append("Script or runtime entrypoints changed and may carry quoting or launcher assumptions.")
        if any(path in {"README.md", "package.json"} for path in changed_paths):
            drivers.append("Operator-facing command examples or npm scripts changed and should stay Windows-safe.")
        if git_snapshot.get("touches_runtime") and git_snapshot.get("touches_plugin"):
            risk = "high"
            drivers.append("The change spans runtime and plugin surfaces, so command contracts can drift across layers.")
        if not drivers:
            drivers.append("No obvious Windows-specific risk signal appears in the changed paths.")
        return {
            "risk": risk,
            "summary": "Fallback Windows compatibility review derived from changed-path categories.",
            "drivers": drivers,
            "confidence": 0.64,
            "rationale": "Fallback Windows review uses deterministic path heuristics when no validated local-model payload is available.",
        }
    if flow_name == "review-checklist":
        checks = ["Review the changed runtime and plugin contracts together.", "Confirm validation commands still match the changed surface."]
        if git_snapshot.get("touches_runtime"):
            checks.append("Inspect fallback, observability, and bounded-output semantics in the shared runtime.")
        if git_snapshot.get("touches_plugin"):
            checks.append("Verify the plugin stays a thin client over the shared runtime command surfaces.")
        if git_snapshot.get("touches_tests"):
            checks.append("Confirm updated tests still reflect real operator behavior rather than stale fixtures.")
        return {
            "profile": "mixed" if git_snapshot.get("touches_runtime") or git_snapshot.get("touches_plugin") else "docs-only",
            "checks": checks,
            "confidence": 0.7,
            "rationale": "Fallback review checklist is derived from the changed-path categories.",
        }
    if flow_name == "doc-link-suggestion":
        doc = docs_by_ref[str(seed_ref)]
        missing_links: list[str] = []
        suggested_follow_up: list[str] = []
        if doc.kind in {"request", "backlog", "task"} and not any(doc.refs.values()):
            missing_links.append("No workflow references are linked yet.")
            suggested_follow_up.append("Link the adjacent request, backlog item, or task before closing the slice.")
        if doc.kind in {"backlog", "task"} and "prod" not in doc.refs and "adr" not in doc.refs:
            missing_links.append("No companion product or architecture doc is linked.")
            suggested_follow_up.append("Confirm whether a product brief or ADR should be linked for this scope.")
        if not missing_links:
            missing_links.append("No obvious missing link was detected from the workflow graph.")
            suggested_follow_up.append("Keep references aligned if the scope or decision framing changes.")
        return {
            "target_ref": doc.ref,
            "missing_links": missing_links,
            "suggested_follow_up": suggested_follow_up,
            "confidence": 0.61,
            "rationale": "Fallback doc-link suggestion is derived from the existing workflow reference graph.",
        }
    if flow_name == "generate-changelog":
        version_info = _resolve_release_changelog_status(Path(context_bundle.get("repo_root", ".")))
        version = version_info.get("version", "0.0.0")
        tag = version_info.get("tag", f"v{version}")
        entries: list[str] = []
        if git_snapshot.get("touches_plugin"):
            entries.append("Expose new action surfaces in the VS Code plugin.")
        if git_snapshot.get("touches_runtime"):
            entries.append("Add bounded hybrid assist flows and delivery automation.")
        if git_snapshot.get("touches_tests"):
            entries.append("Add or update integration tests for the new flows.")
        if not entries:
            entries.append("Delivery automation and workflow surface updates.")
        content_lines = [f"# Changelog (`{tag}`)", "", "## Highlights", ""]
        content_lines += [f"- {e}" for e in entries]
        return {
            "content": "\n".join(content_lines),
            "title": f"Release {tag}",
            "entries": entries,
            "confidence": 0.6,
            "rationale": "Fallback changelog generated from changed-path categories when AI runtime is unavailable.",
        }
    raise HybridAssistError("hybrid_unhandled_flow", f"Unhandled hybrid assist flow `{flow_name}`.")


def execute_commit_step(repo_root: Path, message: str) -> dict[str, Any]:
    add = subprocess.run(["git", "add", "-A"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if add.returncode != 0:
        raise HybridAssistError("hybrid_git_add_failed", add.stderr.strip() or "git add failed", details={"repo_root": str(repo_root)})
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise HybridAssistError(
            "hybrid_git_commit_failed",
            commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
            details={"repo_root": str(repo_root), "message": message},
        )
    return {"stdout": commit.stdout.strip(), "stderr": commit.stderr.strip(), "message": message}


def run_validation_commands(
    repo_root: Path,
    commands: list[list[str]],
    *,
    command_labeler: Callable[[list[str]], str] | None = None,
) -> dict[str, Any]:
    statuses = []
    for argv in commands:
        label = command_labeler(argv) if command_labeler is not None else " ".join(argv)
        result = subprocess.run(
            argv,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        summary = result.stderr.strip() or result.stdout.strip() or ("ok" if result.returncode == 0 else "failed")
        statuses.append(
            {
                "command": label,
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "summary": summary.splitlines()[0][:240] if summary else "",
            }
        )
    return {"statuses": statuses}


__all__ = [name for name in globals() if not name.startswith("__")]
