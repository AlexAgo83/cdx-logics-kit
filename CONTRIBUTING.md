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

Canonical examples use `python ...` as the cross-platform launcher.
If your environment only exposes `python3` or `py -3`, substitute that launcher.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python tests/run_test_coverage.py
python tests/run_cli_smoke_checks.py
python logics-version-changelog-manager/scripts/generate_version_changelog.py --out changelogs/CHANGELOGS_PREVIEW.md --overwrite
python logics-version-release-manager/scripts/publish_version_release.py --dry-run
```

If you modify a specific connector or helper, also run a targeted smoke check for that script.

Line endings:

- Let Git handle `CRLF`/`LF` conversion through the repository attributes instead of manually rewriting generated Markdown or YAML files on Windows.
- Prefer repository-relative temp or preview paths in docs and examples when the exact OS temp directory is not important.

## Documentation expectations

- keep `README.md` aligned with the actual CLI and skill behavior
- update examples when commands, flags, or recommended flows change
- prefer examples that work inside a project importing the kit under `logics/skills/`
- keep `VERSION`, `changelogs/`, and release tooling aligned when preparing a new release

## Script and template changes

- keep generated document structure consistent with the rest of the kit
- avoid introducing breaking filename or section format changes unless they are deliberate and documented
- preserve clear stdout/stderr messages because the VS Code extension and agent workflows depend on actionable feedback
- prefer shared flow-manager helpers or canonical parse/normalize models over duplicating ad hoc workflow logic in each connector

## Skill extension contract

Skills should satisfy a lightweight package contract so kit tooling can validate and benchmark them consistently:

- provide a `SKILL.md` with valid frontmatter and a non-empty `description`
- provide `agents/openai.yaml` with an `interface:` mapping that explains the skill boundary
- keep optional `scripts/`, `assets/`, and `tests/` directories predictable so capability discovery remains machine-readable
- add reusable fixture input when a skill introduces a new package shape or parsing contract
- keep lightweight benchmark or smoke-check expectations deterministic enough for CI

Fixture examples used by the kit test suite live under [`tests/fixtures`](/Users/alexandreagostini/Documents/cdx-logics-vscode/logics/skills/tests/fixtures).

## Pull requests

A good pull request should include:

- what changed
- why it changed
- whether existing repositories need migration or follow-up actions
- which tests or smoke checks were run

## Collaboration

Use issues or pull requests for substantive changes so behavior, migration cost, and workflow impact stay explicit and reviewable.
