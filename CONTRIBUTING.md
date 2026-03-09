# Contributing to cdx-logics-kit

## Scope

This repository provides reusable Logics skills, scripts, templates, and tests intended to be imported into other repositories under `logics/skills/`.

Keep contributions aligned with that purpose:

- prefer reusable workflow improvements over project-specific customizations
- keep scripts dependency-light unless an external dependency is clearly justified
- preserve backward compatibility for existing `logics/*` document conventions when practical

## Recommended workflow

1. Create a focused branch for the change.
2. Update the relevant script, template, skill doc, or README.
3. Add or update tests when behavior changes.
4. Run the relevant validation commands locally.
5. Submit a reviewable pull request with a concise rationale and impact summary.

## Validation

Run the checks that match the area you changed:

```bash
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py
python3 logics/skills/logics-flow-manager/scripts/workflow_audit.py
python3 -m unittest discover -s logics/skills/tests -p "test_*.py" -v
```

If you modify a specific connector or helper, also run a targeted smoke check for that script.

## Documentation expectations

- keep `README.md` aligned with the actual CLI and skill behavior
- update examples when commands, flags, or recommended flows change
- prefer examples that work inside a project importing the kit under `logics/skills/`

## Script and template changes

- keep generated document structure consistent with the rest of the kit
- avoid introducing breaking filename or section format changes unless they are deliberate and documented
- preserve clear stdout/stderr messages because the VS Code extension and agent workflows depend on actionable feedback

## Pull requests

A good pull request should include:

- what changed
- why it changed
- whether existing repositories need migration or follow-up actions
- which tests or smoke checks were run

## Collaboration

Use issues or pull requests for substantive changes so behavior, migration cost, and workflow impact stay explicit and reviewable.
