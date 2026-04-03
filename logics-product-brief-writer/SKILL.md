---
name: logics-product-brief-writer
description: Write product briefs in `logics/product`. Use when Codex identifies a structuring product framing need (user problem, target users, scope, trade-offs, success signals) and should create a concise product decision document linked to request/backlog/task docs.
---

# Product brief

## Create a new product brief

```bash
python logics/skills/logics-product-brief-writer/scripts/new_product_brief.py --title "Guest checkout framing" --out-dir logics/product
```

## Structure

- Use `# Overview` to state the product direction in 3 to 5 short lines.
- Keep the Mermaid in `# Overview` macro-level only: user problem -> chosen product direction -> expected outcomes.
- Keep the document product-only: user value, scope, trade-offs, success signals, open questions.
- Do not drift into implementation design or system internals. Link to `logics/architecture/` when a technical decision is also required.

## Update discipline

- When you edit an existing product brief, update `Status` and every impacted linked ref (`request`, `backlog`, `task`, `architecture`).
- Keep `# Scope and guardrails`, `# Key product decisions`, `# Success signals`, and `# Open questions` aligned with the latest product direction.
- Remove stale placeholders and replace the `# Overview` Mermaid when the direction materially changes.
