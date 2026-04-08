# Changelog (`1.10.0 -> 1.10.1`)

## Major Highlights

- Generated from 7 commit(s) between `v1.10.0` and `HEAD` on 2026-04-08.
- Touched areas: Workflow and Skills, Validation and CI.
- test(ci): add kit coverage reporting
- test(kit): add 112 unit tests for highest-risk flow-manager modules (wave 2)
- test(kit): add 9 sandbox lifecycle tests for bootstrap, doctor, and schema migration (wave 4)

## Generated Commit Summary

## Workflow and Skills

- Configure RTK for Codex in skills repo

## Validation and CI

- test(ci): add kit coverage reporting
- test(kit): add 112 unit tests for highest-risk flow-manager modules (wave 2)
- test(kit): add 9 sandbox lifecycle tests for bootstrap, doctor, and schema migration (wave 4)
- test(kit): add 13 opt-in live provider integration tests (wave 5)
- fix: prevent coverage/ output dir from shadowing Python coverage package
- Complete flow-manager modularization wave

## Validation and Regression Evidence

- `python3 logics.py flow assist release-changelog-status --format json`
- `python3 logics.py flow assist validation-checklist --format json`
- `python3 logics.py flow assist diff-risk --format json`
