---
name: logics-flow-manager
description: >-
  Manage this repository's Logics workflow (logics/request -> logics/backlog
  -> logics/tasks) and keep companion product or architecture refs aligned:
  create new request/backlog/task docs, promote between stages, keep From
  version, Understanding, Confidence, and Progress indicators consistent, and
  generate correctly-numbered filenames. Use when a user asks to triage an
  idea, write a request, promote it to a backlog item, or create an executable
  task plan.
---

# Logics flow

## Conventions

- Keep workflow docs in `logics/request/`, `logics/backlog/`, `logics/tasks/`.
- Use companion docs in `logics/product/` for structuring product framing and `logics/architecture/` for structuring technical decisions.
- Use numeric IDs and slugs in filenames: `req_001_my_title.md`, `item_002_some_scope.md`, `task_003_do_the_work.md`.
- Keep indicators at the top:
  - `From version: X.X.X`
  - `Status: Draft | Ready | In progress | Blocked | Done | Archived`
  - `Understanding: ??%`
  - `Confidence: ??%`
  - `Progress: ??%` (mainly tasks; optionally backlog)
  - `Complexity: Low | Medium | High`
  - `Theme: Combat | Items | Economy | UI | ...`
- When writing a request, the `# Context` section must include a Mermaid diagram that visualizes the need.
- Prefer a compact business-readable `flowchart TD` or `flowchart LR` showing inputs, decision points, outputs, and feedback loops.
- Backlog items should include a Mermaid diagram that makes the delivery slice explicit: request/source -> problem -> scope -> acceptance criteria -> task(s).
- Tasks should include a Mermaid diagram that shows the execution path: backlog/source -> implementation steps -> validation -> done/report.
- Generated workflow Mermaid blocks now include `%% logics-signature: ...` metadata comments; keep them aligned with the current doc context so stale diagrams can be detected automatically.
- Mermaid safety rules are mandatory:
  - use plain ASCII text labels only
  - do not use Markdown formatting inside node labels: no backticks, bold, italics, or inline code
  - do not put raw route syntax or braces in labels such as `/users/{id}`; rewrite them as plain text like `users-id route`
  - do not use `+` to concatenate task names inside labels; rewrite as plain text such as `task 1 and task 2`
  - keep labels short and business-readable so strict Mermaid renderers can display them consistently

If unsure, open `logics/instructions.md` and follow the workflow described there.

Command examples below use `python ...` as the canonical cross-platform launcher.
The preferred stable entrypoint is now `python logics/skills/logics.py ...`, which routes toward the flow manager and adjacent kit commands behind one operator-facing contract.
If your environment only exposes `python3` or `py -3`, substitute that launcher.

## Create a new doc (recommended)

Use the generator script (picks the next available ID, creates a file from templates):

```bash
python logics/skills/logics.py flow new request --title "Offline recap UI"
python logics/skills/logics.py flow new backlog --title "Offline recap UI"
python logics/skills/logics.py flow new task --title "Implement offline recap UI"
```

After creation, run **logics-confidence-booster** to raise Understanding/Confidence above 90%:

```bash
python logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/request/req_001_example.md
python logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/backlog/item_002_example.md
python logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/tasks/task_003_example.md
```

When a request or backlog item surfaces a structuring product choice, create a product brief before or alongside promotion:

```bash
python logics/skills/logics-product-brief-writer/scripts/new_product_brief.py --title "Guest checkout framing" --out-dir logics/product
```

When a backlog item surfaces a structuring technical choice, create an ADR/DAT:

```bash
python logics/skills/logics-architecture-decision-writer/scripts/new_adr.py --title "Choose cache strategy" --out-dir logics/architecture
```

For backlog/task creation or promotion, the script now auto-detects product and architecture signals and writes a `# Decision framing` section in generated docs. It stays advisory by default and can auto-create the companion docs when you opt in:

```bash
python logics/skills/logics.py flow new backlog --title "Checkout auth migration" --auto-create-product-brief --auto-create-adr
```

Optional flags:

- `--from-version 0.14.3`
- `--understanding 60% --confidence 40%`
- `--status Draft|Ready|In progress|Blocked|Done|Archived`
- `--complexity Low|Medium|High --theme UI`
- `--progress 0%` (task/backlog)
- `--auto-create-product-brief` (backlog/task only; create `logics/product/prod_###_*.md` when product framing is required)
- `--auto-create-adr` (backlog/task only; create `logics/architecture/adr_###_*.md` when architecture framing is required)
- `--dry-run` (show path + content preview, no writes)

## Promote between stages

Create the next-stage doc and link back to the source:

```bash
python logics/skills/logics.py flow promote request-to-backlog logics/request/req_001_offline_recap_ui.md
python logics/skills/logics.py flow promote backlog-to-task logics/backlog/item_002_offline_recap_ui.md
```

The promotion flow seeds more of the next-stage document automatically:
- source indicators such as `From version`, `Understanding`, `Confidence`, `Complexity`, and `Theme`;
- request acceptance criteria into backlog acceptance criteria + AC traceability;
- backlog acceptance criteria into task AC traceability;
- source context/problem statements into the generated problem/context sections;
- actionable `Decision framing` follow-up text inside the generated doc itself.

Split a broad request/backlog item into several executable children:

```bash
python logics/skills/logics.py flow split request logics/request/req_001_example.md --title "Slice A" --title "Slice B"
python logics/skills/logics.py flow split backlog logics/backlog/item_002_example.md --title "Task A" --title "Task B"
```

`logics.yaml` now drives the default split policy. The shipped default is `minimal-coherent`, so keep splits to the smallest coherent slice count unless you explicitly pass `--allow-extra-slices`.

Close docs with automatic transition propagation:

```bash
python logics/skills/logics.py flow close task logics/tasks/task_003_example.md
python logics/skills/logics.py flow close backlog logics/backlog/item_002_example.md
python logics/skills/logics.py flow close request logics/request/req_001_example.md
```

When a task is actually finished, prefer the kit-native guarded flow instead of editing indicators manually:

```bash
python logics/skills/logics.py flow finish task logics/tasks/task_003_example.md
```

`finish task` closes the task, propagates closure to linked backlog/request docs when eligible, verifies that the linked chain stayed synchronized, appends finish/report evidence to the task, and leaves a completion note in linked backlog items. Use `close` only when you explicitly want the lower-level primitive.

Generated tasks now include explicit wave checkpoints:

- each completed wave should leave the repository in a coherent, commit-ready state;
- linked Logics docs should be updated during the wave that changes the behavior;
- prefer one reviewed commit checkpoint per meaningful wave rather than several undocumented partial states.

Run workflow coherence audit:

```bash
python logics/skills/logics.py audit
python logics/skills/logics.py audit --stale-days 30
python logics/skills/logics.py audit --group-by-doc
python logics/skills/logics.py audit --format json
python logics/skills/logics.py audit --autofix-ac-traceability
python logics/skills/logics.py audit --refs req_001_example
python logics/skills/logics.py audit --paths logics/request logics/backlog
python logics/skills/logics.py audit --since-version 1.9.0
python logics/skills/logics.py flow sync refresh-mermaid-signatures
```

Use the guarded local dispatcher when you want a local model to propose a workflow action without giving it direct file-write authority:

```bash
python logics/skills/logics.py flow sync dispatch-context req_088_add_a_local_llm_dispatcher_for_deterministic_logics_flow_orchestration --include-graph --include-registry
python logics/skills/logics.py flow sync dispatch req_088_add_a_local_llm_dispatcher_for_deterministic_logics_flow_orchestration --model deepseek-coder-v2:16b --include-graph --include-registry
python logics/skills/logics.py flow sync dispatch req_088_add_a_local_llm_dispatcher_for_deterministic_logics_flow_orchestration --decision-file /tmp/dispatcher-decision.json --execution-mode execute
```

Dispatcher rules:

- `sync dispatch-context` builds a compact machine-readable bundle around `context-pack`, with optional graph, registry, and doctor summaries.
- `sync dispatch` validates a strict decision contract with only `new`, `promote`, `split`, `finish`, and safe non-destructive `sync` actions.
- `suggestion-only` is the default mode; use `--execution-mode execute` only when you explicitly want the runner to invoke the mapped Logics command.
- Dispatcher runs append JSONL audit records to `logics/dispatcher_audit.jsonl` unless you override `--audit-log`.
- The Ollama path is transport-specific only; the deterministic runner and decision schema stay runtime-agnostic.
- `sync build-index` refreshes the runtime cache used by repeated context, graph, doctor, validation, and registry operations.
- `sync show-config` exposes the effective `logics.yaml` merge so automation can inspect the active split policy, mutation mode, and cache path.
- `sync refresh-ai-context` and `sync migrate-schema` now support repo-configurable `transactional` apply-or-rollback semantics and emit JSONL audit records to `logics/mutation_audit.jsonl` by default.

Use the shared hybrid assist runtime when the user asks for repetitive delivery help that should opportunistically use Ollama but still degrade safely:

```bash
python logics/skills/logics.py flow assist runtime-status --format json
python logics/skills/logics.py flow assist roi-report --format json
python logics/skills/logics.py flow assist commit-all
python logics/skills/logics.py flow assist summarize-pr --format json
python logics/skills/logics.py flow assist summarize-validation --format json
python logics/skills/logics.py flow assist next-step req_089_add_a_hybrid_ollama_or_codex_local_orchestration_backend_for_repetitive_logics_delivery_tasks --format json
python logics/skills/logics.py flow assist triage req_090_add_high_roi_hybrid_ollama_or_codex_assist_flows_for_repetitive_logics_delivery_operations --format json
python logics/skills/logics.py flow assist handoff req_090_add_high_roi_hybrid_ollama_or_codex_assist_flows_for_repetitive_logics_delivery_operations --format json
```

Hybrid assist rules:

- prefer the named aliases over ad hoc shell commands;
- keep `python ...` as the canonical cross-platform launcher;
- `runtime-status` is the shared probe surface for plugin, Codex, and Claude integrations;
- `roi-report` is the shared observability surface for CLI automation and plugin insights, including explicit measured, derived, and estimated sections;
- use `--model-profile qwen-coder` when the operator explicitly wants the curated Qwen path instead of the default DeepSeek profile;
- the shared runtime keeps backend provenance, degraded reasons, audit JSONL, and measurement JSONL visible to downstream surfaces;
- risky execution stays bounded: `suggestion-only` remains the default unless the operator intent is explicit.

Manage per-repository Codex overlays when several repos expose Logics skills concurrently:

```bash
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py register
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py sync
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py status
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py doctor --fix
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py run -- codex
python logics/skills/logics-flow-manager/scripts/logics_codex_workspace.py clean
```

The overlay manager keeps `logics/skills/` canonical in the repo, projects repo-local skills into `~/.codex-workspaces/<repo-id>/`, lets repo-local skills shadow same-named global skills, and keeps shared user assets such as `auth.json`, `config.toml`, and `skills/.system` referenced from the primary `~/.codex/` home when available.

After promotion:

- Ensure the backlog item has clear acceptance criteria + priority.
- Ensure the task has a step-by-step plan and at least 1–2 validation commands relevant to the work.
- Ensure the source request lists any generated backlog items in its Backlog section.
- Carry forward any linked `prod_###` and `adr_###` refs so downstream docs keep the product and architecture framing visible.

Before promotion:

- If `Understanding` or `Confidence` is below 90% in the source doc, run the **logics-confidence-booster** skill first to clarify and update indicators.
- If the need requires a non-trivial product framing document, write a product brief in `logics/product/` and reference it from the source doc before promotion.
- If the need requires a non-trivial technical decision, write an ADR in `logics/architecture/` and reference it from the source doc before promotion.
- For request docs, replace the default Mermaid scaffold with a diagram specific to the need before considering the request ready.
- For backlog/task docs, replace the default Mermaid scaffold with a doc-specific diagram whenever the default no longer reflects the real flow.
- Refresh the Mermaid block whenever the title, problem/need, acceptance criteria, plan, validation path, or source links change in a way that changes the delivery story.
- Before finalizing any Mermaid diagram, sanity-check that the labels still obey the Mermaid safety rules above so previewers do not fall back to raw source rendering.
