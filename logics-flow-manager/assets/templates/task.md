## {{DOC_REF}} - {{TITLE}}
> From version: {{FROM_VERSION}}
> Schema version: {{SCHEMA_VERSION}}
> Status: {{STATUS}}
> Understanding: {{UNDERSTANDING}}
> Confidence: {{CONFIDENCE}}
> Progress: {{PROGRESS}}
> Complexity: {{COMPLEXITY}}
> Theme: {{THEME}}
> Reminder: Update status/understanding/confidence/progress and dependencies/references when you edit this doc.

# Context
{{CONTEXT_PLACEHOLDER}}

{{MERMAID_BLOCK}}

# Plan
{{PLAN_BLOCK}}

# Delivery checkpoints
- Each completed wave should leave the repository in a coherent, commit-ready state.
- Update the linked Logics docs during the wave that changes the behavior, not only at final closure.
- Prefer a reviewed commit checkpoint at the end of each meaningful wave instead of accumulating several undocumented partial states.
- If the shared AI runtime is active and healthy, use `python logics/skills/logics.py flow assist commit-all` to prepare the commit checkpoint for each meaningful step, item, or wave.
- Do not mark a wave or step complete until the relevant automated tests and quality checks have been run successfully.

# AC Traceability
{{AC_TRACEABILITY_PLACEHOLDER}}

# Decision framing
- Product framing: {{PRODUCT_FRAMING_STATUS}}
- Product signals: {{PRODUCT_FRAMING_SIGNALS}}
- Product follow-up: {{PRODUCT_FRAMING_ACTION}}
- Architecture framing: {{ARCHITECTURE_FRAMING_STATUS}}
- Architecture signals: {{ARCHITECTURE_FRAMING_SIGNALS}}
- Architecture follow-up: {{ARCHITECTURE_FRAMING_ACTION}}

# Links
- Product brief(s): {{PRODUCT_LINK_PLACEHOLDER}}
- Architecture decision(s): {{ARCHITECTURE_LINK_PLACEHOLDER}}
- Backlog item: {{BACKLOG_LINK_PLACEHOLDER}}
- Request(s): {{REQUEST_LINK_PLACEHOLDER}}

# AI Context
- Summary: {{AI_SUMMARY_PLACEHOLDER}}
- Keywords: {{AI_KEYWORDS_PLACEHOLDER}}
- Use when: {{AI_USE_WHEN_PLACEHOLDER}}
- Skip when: {{AI_SKIP_WHEN_PLACEHOLDER}}

{{REFERENCES_SECTION}}

# Validation
{{VALIDATION_BLOCK}}

# Definition of Done (DoD)
- [ ] Scope implemented and acceptance criteria covered.
- [ ] Validation commands executed and results captured.
- [ ] No wave or step was closed before the relevant automated tests and quality checks passed.
- [ ] Linked request/backlog/task docs updated during completed waves and at closure.
- [ ] Each completed wave left a commit-ready checkpoint or an explicit exception is documented.
- [ ] Status is `Done` and progress is `100%`.

# Report
{{REPORT_PLACEHOLDER}}
