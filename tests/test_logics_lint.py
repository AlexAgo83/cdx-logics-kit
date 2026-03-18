from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LogicsLintTest(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-doc-linter" / "scripts" / "logics_lint.py"

    def _init_git_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)

    def test_product_and_architecture_docs_are_linted(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "product").mkdir(parents=True)
            (repo / "logics" / "architecture").mkdir(parents=True)

            (repo / "logics" / "product" / "prod_000_guest_checkout.md").write_text(
                "\n".join(
                    [
                        "## prod_000_guest_checkout - Guest checkout",
                        "> Date: 2026-03-14",
                        "> Status: Proposed",
                        "> Related request: `req_000_guest_checkout`",
                        "> Related backlog: `item_000_guest_checkout`",
                        "> Related task: (none yet)",
                        "> Related architecture: `adr_000_guest_checkout`",
                        "> Reminder: Keep this brief aligned with the latest product direction.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            (repo / "logics" / "architecture" / "adr_000_guest_checkout.md").write_text(
                "\n".join(
                    [
                        "## adr_000_guest_checkout - Guest checkout",
                        "> Date: 2026-03-14",
                        "> Status: Accepted",
                        "> Drivers: Session boundaries and auth model.",
                        "> Related request: `req_000_guest_checkout`",
                        "> Related backlog: `item_000_guest_checkout`",
                        "> Related task: `task_000_guest_checkout`",
                        "> Reminder: Keep this ADR aligned with the latest architecture direction.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--require-status"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Logics lint: OK", completed.stdout)

    def test_require_status_rejects_missing_status(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "tasks").mkdir(parents=True)
            (repo / "logics" / "tasks" / "task_000_demo.md").write_text(
                "\n".join(
                    [
                        "## task_000_demo - Demo task",
                        "> From version: 1.0.0",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script), "--require-status"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("missing indicator: Status", result.stdout)

    def test_require_status_accepts_normalized_task(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "tasks").mkdir(parents=True)
            (repo / "logics" / "tasks" / "task_000_demo.md").write_text(
                "\n".join(
                    [
                        "## task_000_demo - Demo task",
                        "> From version: 1.0.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script), "--require-status"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Logics lint: OK", result.stdout)

    def test_status_only_normalization_does_not_require_other_indicator_updates(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo)
            (repo / "logics" / "tasks").mkdir(parents=True)
            task = repo / "logics" / "tasks" / "task_000_demo.md"
            task.write_text(
                "\n".join(
                    [
                        "## task_000_demo - Demo task",
                        "> From version: 1.0.0",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            task.write_text(
                "\n".join(
                    [
                        "## task_000_demo - Demo task",
                        "> From version: 1.0.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script), "--require-status"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Logics lint: OK", result.stdout)

    def test_untracked_workflow_doc_fails_on_critical_placeholder_indicators(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "README.md").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            request = repo / "logics" / "request" / "req_000_demo_ui.md"
            request.write_text(
                "\n".join(
                    [
                        "## req_000_demo_ui - Demo UI",
                        "> From version: X.X.X",
                        "> Status: Draft",
                        "> Understanding: ??%",
                        "> Confidence: ??%",
                        "",
                        "# Needs",
                        "- Demo need",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("placeholder indicator: From version = X.X.X", result.stdout)
            self.assertIn("placeholder indicator: Understanding = ??%", result.stdout)
            self.assertIn("placeholder indicator: Confidence = ??%", result.stdout)

    def test_untracked_workflow_doc_warns_on_template_filler_without_failing(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "README.md").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            request = repo / "logics" / "request" / "req_000_demo_ui.md"
            request.write_text(
                "\n".join(
                    [
                        "## req_000_demo_ui - Demo UI",
                        "> From version: 1.10.5",
                        "> Status: Draft",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "",
                        "# Needs",
                        "- Describe the need",
                        "",
                        "# Context",
                        "Add context and constraints",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Logics lint: OK (warnings)", result.stdout)
            self.assertIn("WARNING: contains template placeholder content", result.stdout)

    def test_untracked_workflow_doc_warns_on_generic_mermaid_scaffold(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "README.md").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            backlog = repo / "logics" / "backlog" / "item_000_demo_backlog.md"
            backlog.write_text(
                "\n".join(
                    [
                        "## item_000_demo_backlog - Demo backlog",
                        "> From version: 1.10.5",
                        "> Status: Ready",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 0%",
                        "",
                        "# Problem",
                        "- Improve read orchestration for operators",
                        "",
                        "```mermaid",
                        "flowchart LR",
                        "    Req[Request source] --> Problem[Problem to solve]",
                        "    Problem --> Scope[Scoped delivery]",
                        "```",
                        "",
                        "# Acceptance criteria",
                        "- AC1: read opens from the operator board",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Logics lint: OK (warnings)", result.stdout)
            self.assertIn("WARNING: contains generic Mermaid scaffold content", result.stdout)

    def test_untracked_workflow_doc_warns_on_stale_mermaid_signature(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo)
            (repo / "logics" / "tasks").mkdir(parents=True)
            (repo / "README.md").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "seed"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            task = repo / "logics" / "tasks" / "task_000_demo_task.md"
            task.write_text(
                "\n".join(
                    [
                        "## task_000_demo_task - Demo task",
                        "> From version: 1.10.5",
                        "> Status: Ready",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 0%",
                        "",
                        "# Context",
                        "- Derived from backlog item `item_000_demo_backlog`.",
                        "",
                        "```mermaid",
                        "%% logics-kind: task",
                        "%% logics-signature: task|stale-signature",
                        "flowchart LR",
                        "    Backlog[item_000_demo_backlog] --> Step1[Confirm scope]",
                        "    Step1 --> Validation[Run tests]",
                        "```",
                        "",
                        "# Plan",
                        "- [ ] 1. Confirm scope, dependencies, and linked acceptance criteria.",
                        "- [ ] 2. Implement the scoped changes from the backlog item.",
                        "- [ ] 3. Validate the result and update the linked Logics docs.",
                        "- [ ] FINAL: Update related Logics docs",
                        "",
                        "# Validation",
                        "- python3 -m pytest",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Logics lint: OK (warnings)", result.stdout)
            self.assertIn("WARNING: Mermaid context signature is stale", result.stdout)


if __name__ == "__main__":
    unittest.main()
