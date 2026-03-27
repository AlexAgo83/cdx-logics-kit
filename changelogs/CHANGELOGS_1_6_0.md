# Changelog (`1.5.0 -> 1.6.0`)

## Highlights

- Expanded the shared hybrid assist runtime with deterministic helper flows for changed-surface summaries, release changelog resolution, test-impact summaries, and Hybrid Insights explanations.
- Added new bounded Ollama-first proposal flows for Windows compatibility review, review checklist generation, and missing workflow-link suggestions.
- Hardened `commit-all` so parent repositories with only a submodule pointer update no longer fail by trying to re-commit an already-clean nested repo.
- Tightened workflow linting so active request, backlog, and task docs now fail on blocking proof and AC-traceability placeholders instead of passing with warning-only template text.
- Stopped versioning generated runtime cache content by ignoring `logics/.cache/` and removing `logics/.cache/runtime_index.json` from the tracked kit surface.

## Hybrid assist expansion

- Added deterministic backend policy support alongside `ollama-first` and `codex-only`, while keeping backend policy metadata visible through shared runtime status output.
- Extended the shared assist aliases and validation contracts for:
  - `changed-surface-summary`
  - `release-changelog-status`
  - `test-impact-summary`
  - `hybrid-insights-explainer`
  - `windows-compat-risk`
  - `review-checklist`
  - `doc-link-suggestion`
- Kept deterministic flows off the Ollama transport path so bounded outputs can be derived directly from git, changelog, and ROI-report inputs.

## Commit-all and submodule safety

- Updated `commit-plan` fallback logic to distinguish a dirty nested `logics/skills` repo from a clean submodule whose parent pointer alone has changed.
- Updated `commit-all` execution to skip empty submodule steps instead of failing on `git commit` with `nothing to commit`.
- Added regression coverage with a real local git submodule fixture to keep pointer-only parent commits working end-to-end.

## Workflow lint and repository hygiene

- Added blocking placeholder detection for active workflow docs so traceability sections with `Proof: TODO` and similar AC placeholders now fail lint.
- Made changed-doc lint checks able to inspect the latest commit diff when the worktree is clean, improving CI coverage for recently committed workflow docs.
- Ignored Python bytecode caches, hybrid assist runtime logs, and `logics/.cache/` artifacts to keep generated kit runtime files out of versioned history.

## Validation

- `python3 -m unittest tests.test_logics_flow.LogicsFlowTest.test_assist_commit_all_execute_commits_simple_repo tests.test_logics_flow.LogicsFlowTest.test_assist_commit_all_skips_clean_submodule_and_commits_parent_pointer -v`
- `python3 -m unittest tests.test_logics_flow tests.test_logics_lint tests.test_workflow_audit -v`
- `python3 logics-version-release-manager/scripts/publish_version_release.py --dry-run`

