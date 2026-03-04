#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit("Could not locate repository root (missing .git).")


def _run_git(repo_root: Path, args: list[str]) -> list[str]:
    command = ["git", *args]
    try:
        proc = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_files(repo_root: Path, base: str | None) -> list[str]:
    paths: set[str] = set()
    if base:
        for p in _run_git(repo_root, ["diff", "--name-only", f"{base}...HEAD"]):
            paths.add(p)
    for p in _run_git(repo_root, ["diff", "--name-only"]):
        paths.add(p)
    for p in _run_git(repo_root, ["diff", "--name-only", "--cached"]):
        paths.add(p)
    return sorted(paths)


def _npm_scripts(repo_root: Path) -> dict[str, str]:
    package_json = repo_root / "package.json"
    if not package_json.is_file():
        return {}
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def _collect_test_files(repo_root: Path) -> list[Path]:
    result: list[Path] = []
    for rel in ("tests", "src"):
        root = repo_root / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            location = path.as_posix().lower()
            if ".test." in name or ".spec." in name or "__tests__" in location or "/e2e/" in location:
                result.append(path)
    return result


def _candidate_tests_for_source(test_files: list[Path], source_path: str, limit: int = 3) -> list[str]:
    stem_tokens = [t for t in re.split(r"[^a-z0-9]+", Path(source_path).stem.lower()) if len(t) >= 3]
    if not stem_tokens:
        return []

    scored: list[tuple[int, str]] = []
    for test_file in test_files:
        rel = test_file.as_posix().lower()
        score = sum(1 for token in stem_tokens if token in rel)
        if score:
            scored.append((score, rel))

    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[str] = []
    for _, rel in scored:
        if rel in chosen:
            continue
        chosen.append(rel)
        if len(chosen) >= limit:
            break
    return chosen


def _pick_script(scripts: dict[str, str], aliases: list[str]) -> str | None:
    return next((alias for alias in aliases if alias in scripts), None)


def _build_command_plan(changed: list[str], scripts: dict[str, str]) -> list[str]:
    changed_set = set(changed)
    has_source_changes = any(p.startswith("src/") for p in changed_set)
    has_test_changes = any(p.startswith("tests/") for p in changed_set)
    has_ts_changes = any(Path(p).suffix in {".ts", ".tsx", ".js", ".jsx"} for p in changed_set)
    has_config_changes = any(
        p in {"package.json", "package-lock.json", "vite.config.ts", "tsconfig.json", "eslint.config.js"}
        for p in changed_set
    )
    has_ui_changes = any(
        p.startswith("src/components/")
        or p.startswith("src/screens/")
        or p.startswith("src/pages/")
        or p.startswith("src/ui/")
        or p.startswith("tests/e2e/")
        for p in changed_set
    )

    commands: list[str] = []
    lint_script = _pick_script(scripts, ["lint"])
    unit_script = _pick_script(scripts, ["tests", "test", "test:unit"])
    typecheck_script = _pick_script(scripts, ["typecheck"])
    build_script = _pick_script(scripts, ["build"])
    e2e_script = _pick_script(scripts, ["test:e2e", "e2e", "playwright"])

    if (has_source_changes or has_test_changes or has_config_changes) and lint_script:
        commands.append(f"npm run {lint_script}")
    if (has_source_changes or has_test_changes) and unit_script:
        commands.append(f"npm run {unit_script}")
    if has_ts_changes and typecheck_script:
        commands.append(f"npm run {typecheck_script}")
    if has_ui_changes and e2e_script:
        commands.append(f"npm run {e2e_script}")
    if (has_source_changes or has_config_changes) and build_script:
        commands.append(f"npm run {build_script}")

    deduped: list[str] = []
    for command in commands:
        if command not in deduped:
            deduped.append(command)
    return deduped


def _render_report(changed: list[str], commands: list[str], source_to_tests: dict[str, list[str]]) -> str:
    lines: list[str] = []
    lines.append("# Test Impact Plan")
    lines.append("")
    if not changed:
        lines.append("_No changed files detected from git diff/staged/unstaged._")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("## Changed files")
    lines.append("")
    for path in changed:
        lines.append(f"- `{path}`")
    lines.append("")

    lines.append("## Suggested validation order")
    lines.append("")
    if not commands:
        lines.append("- _No matching npm scripts found. Add validation commands manually._")
    else:
        for i, command in enumerate(commands, start=1):
            lines.append(f"{i}. `{command}`")
    lines.append("")

    lines.append("## Candidate targeted tests")
    lines.append("")
    if not source_to_tests:
        lines.append("- _No source file changes requiring targeted test mapping._")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    for source_path, tests in source_to_tests.items():
        if tests:
            lines.append(f"- `{source_path}` -> " + ", ".join(f"`{t}`" for t in tests))
        else:
            lines.append(f"- `{source_path}` -> _no close test match found_")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a pragmatic test impact plan from current git changes.")
    parser.add_argument("--base", help="Optional base ref for committed diff (example: origin/main).")
    parser.add_argument("--out", help="Write report to this path instead of stdout.")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    changed = _changed_files(repo_root, args.base)
    scripts = _npm_scripts(repo_root)
    commands = _build_command_plan(changed, scripts)

    test_files = _collect_test_files(repo_root)
    source_to_tests: dict[str, list[str]] = {}
    for path in changed:
        if not path.startswith("src/"):
            continue
        if ".test." in path or ".spec." in path:
            continue
        source_to_tests[path] = _candidate_tests_for_source(test_files, path)

    report = _render_report(changed, commands, source_to_tests)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(repo_root) if out_path.is_relative_to(repo_root) else out_path}")
        return 0

    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
