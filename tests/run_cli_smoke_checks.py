#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, text=True)


def link_skills_repo(project_root: Path) -> None:
    logics_dir = project_root / "logics"
    logics_dir.mkdir(parents=True, exist_ok=True)
    target = logics_dir / "skills"
    if target.exists():
        return
    try:
        target.symlink_to(REPO_ROOT, target_is_directory=True)
    except OSError:
        shutil.copytree(REPO_ROOT, target)


def mark_checkboxes_done(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("- [ ]", "- [x]"), encoding="utf-8")


def find_single(glob_pattern: str, root: Path) -> Path:
    matches = sorted(root.glob(glob_pattern))
    if len(matches) != 1:
        raise SystemExit(f"Expected one match for {glob_pattern}, found {len(matches)}")
    return matches[0]


def run_flow_fixture() -> None:
    with tempfile.TemporaryDirectory(prefix="logics-kit-flow-smoke-") as temp_dir:
        project_root = Path(temp_dir)
        link_skills_repo(project_root)

        run([sys.executable, "logics/skills/logics.py", "bootstrap"], cwd=project_root)
        run(
            [sys.executable, "logics/skills/logics.py", "flow", "new", "request", "--title", "Smoke request"],
            cwd=project_root,
        )
        request_path = find_single("logics/request/req_*.md", project_root)
        run(
            [
                sys.executable,
                "logics/skills/logics.py",
                "flow",
                "promote",
                "request-to-backlog",
                str(request_path.relative_to(project_root)),
            ],
            cwd=project_root,
        )
        backlog_path = find_single("logics/backlog/item_*.md", project_root)
        run(
            [
                sys.executable,
                "logics/skills/logics.py",
                "flow",
                "promote",
                "backlog-to-task",
                str(backlog_path.relative_to(project_root)),
            ],
            cwd=project_root,
        )
        task_path = find_single("logics/tasks/task_*.md", project_root)

        run(
            [
                sys.executable,
                "logics/skills/logics.py",
                "flow",
                "split",
                "request",
                str(request_path.relative_to(project_root)),
                "--title",
                "Smoke split child A",
                "--title",
                "Smoke split child B",
            ],
            cwd=project_root,
        )

        mark_checkboxes_done(request_path)
        mark_checkboxes_done(task_path)

        run([sys.executable, "logics/skills/logics.py", "lint"], cwd=project_root)
        run([sys.executable, "logics/skills/logics.py", "audit"], cwd=project_root)
        run(
            [
                sys.executable,
                "logics/skills/logics.py",
                "audit",
                "--refs",
                request_path.stem,
            ],
            cwd=project_root,
        )


def run_companion_fixture() -> None:
    with tempfile.TemporaryDirectory(prefix="logics-kit-companion-smoke-") as temp_dir:
        project_root = Path(temp_dir)
        link_skills_repo(project_root)

        run([sys.executable, "logics/skills/logics.py", "bootstrap"], cwd=project_root)
        run(
            [
                sys.executable,
                "logics/skills/logics.py",
                "flow",
                "new",
                "backlog",
                "--title",
                "Checkout auth migration",
                "--auto-create-product-brief",
                "--auto-create-adr",
            ],
            cwd=project_root,
        )
        run(
            [
                sys.executable,
                "logics/skills/logics-spec-writer/scripts/logics_spec.py",
                "new",
                "--title",
                "Smoke spec",
                "--from-version",
                "1.0.1",
            ],
            cwd=project_root,
        )
        if not list((project_root / "logics" / "product").glob("prod_*.md")):
            raise SystemExit("Expected generated product brief in companion smoke fixture.")
        if not list((project_root / "logics" / "architecture").glob("adr_*.md")):
            raise SystemExit("Expected generated ADR in companion smoke fixture.")
        run([sys.executable, "logics/skills/logics.py", "lint"], cwd=project_root)


def main() -> int:
    run_flow_fixture()
    run_companion_fixture()
    print("CLI smoke checks: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
