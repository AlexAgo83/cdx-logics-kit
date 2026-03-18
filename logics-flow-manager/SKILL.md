---
name: logics-flow-manager
description: Manage this repository's Logics workflow (logics/request → logics/backlog → logics/tasks) and keep companion product or architecture refs aligned: create new request/backlog/task docs, promote between stages, keep From version/Understanding/Confidence/Progress indicators consistent, and generate correctly-numbered filenames. Use when a user asks to triage an idea, write a request, promote it to a backlog item, or create an executable task plan.
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

## Create a new doc (recommended)

Use the generator script (picks the next available ID, creates a file from templates):

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new request --title "Offline recap UI"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog --title "Offline recap UI"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new task --title "Implement offline recap UI"
```

After creation, run **logics-confidence-booster** to raise Understanding/Confidence above 90%:

```bash
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/request/req_001_example.md
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/backlog/item_002_example.md
python3 logics/skills/logics-confidence-booster/scripts/boost_confidence.py logics/tasks/task_003_example.md
```

When a request or backlog item surfaces a structuring product choice, create a product brief before or alongside promotion:

```bash
python3 logics/skills/logics-product-brief-writer/scripts/new_product_brief.py --title "Guest checkout framing" --out-dir logics/product
```

When a backlog item surfaces a structuring technical choice, create an ADR/DAT:

```bash
python3 logics/skills/logics-architecture-decision-writer/scripts/new_adr.py --title "Choose cache strategy" --out-dir logics/architecture
```

For backlog/task creation or promotion, the script now auto-detects product and architecture signals and writes a `# Decision framing` section in generated docs. It stays advisory by default and can auto-create the companion docs when you opt in:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog \
  --title "Checkout auth migration" \
  --auto-create-product-brief \
  --auto-create-adr
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
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/req_001_offline_recap_ui.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/item_002_offline_recap_ui.md
```

The promotion flow seeds more of the next-stage document automatically:
- source indicators such as `From version`, `Understanding`, `Confidence`, `Complexity`, and `Theme`;
- request acceptance criteria into backlog acceptance criteria + AC traceability;
- backlog acceptance criteria into task AC traceability;
- source context/problem statements into the generated problem/context sections;
- actionable `Decision framing` follow-up text inside the generated doc itself.

Split a broad request/backlog item into several executable children:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py split request logics/request/req_001_example.md --title "Slice A" --title "Slice B"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py split backlog logics/backlog/item_002_example.md --title "Task A" --title "Task B"
```

Close docs with automatic transition propagation:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close task logics/tasks/task_003_example.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close backlog logics/backlog/item_002_example.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py close request logics/request/req_001_example.md
```

When a task is actually finished, prefer the kit-native guarded flow instead of editing indicators manually:

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py finish task logics/tasks/task_003_example.md
```

`finish task` closes the task, propagates closure to linked backlog/request docs when eligible, verifies that the linked chain stayed synchronized, appends finish/report evidence to the task, and leaves a completion note in linked backlog items. Use `close` only when you explicitly want the lower-level primitive.

Run workflow coherence audit:

```bash
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --stale-days 30
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --group-by-doc
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --format json
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --autofix-ac-traceability
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --refs req_001_example
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --paths logics/request logics/backlog
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py --since-version 1.9.0
```

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
