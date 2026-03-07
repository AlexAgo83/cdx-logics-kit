## {{DOC_REF}} - {{TITLE}}
> From version: {{FROM_VERSION}}
> Status: {{STATUS}}
> Understanding: {{UNDERSTANDING}}
> Confidence: {{CONFIDENCE}}
> Progress: {{PROGRESS}}
> Complexity: {{COMPLEXITY}}
> Theme: {{THEME}}
> Reminder: Update status/understanding/confidence/progress and dependencies/references when you edit this doc.

# Context
{{CONTEXT_PLACEHOLDER}}

```mermaid
flowchart LR
    Backlog[Backlog: {{BACKLOG_LINK_PLACEHOLDER}}] --> Step1[{{STEP_1}}]
    Step1 --> Step2[{{STEP_2}}]
    Step2 --> Step3[{{STEP_3}}]
    Step3 --> Validation[Validation]
    Validation --> Report[Report and Done]
```

# Plan
- [ ] 1. {{STEP_1}}
- [ ] 2. {{STEP_2}}
- [ ] 3. {{STEP_3}}
- [ ] FINAL: Update related Logics docs

# AC Traceability
- AC1 -> Implemented in the steps above. Proof: add test/commit/file links.

# Links
- Backlog item: {{BACKLOG_LINK_PLACEHOLDER}}
- Request(s): {{REQUEST_LINK_PLACEHOLDER}}

# Validation
- {{VALIDATION_1}}
- {{VALIDATION_2}}

# Definition of Done (DoD)
- [ ] Scope implemented and acceptance criteria covered.
- [ ] Validation commands executed and results captured.
- [ ] Linked request/backlog/task docs updated.
- [ ] Status is `Done` and progress is `100%`.

# Report
{{REPORT_PLACEHOLDER}}
