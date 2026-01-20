---
name: logics-acceptance-to-tests
description: Convert acceptance criteria into a concrete validation/test plan. Use when Codex should turn backlog/spec acceptance criteria into unit/integration/e2e test ideas and update the task/spec validation section with relevant commands.
---

# Acceptance → Tests

## Do

- Rewrite each acceptance criterion as a verifiable check.
- Map checks to test types:
  - Unit: pure logic and edge cases
  - Integration: components + state + API boundaries
  - E2E: user flows and regressions
- Update the `# Validation` section in tasks with the most relevant commands:
  - `npm run lint`
  - `npm run tests`
  - `npm run typecheck`
  - `npm run build`

