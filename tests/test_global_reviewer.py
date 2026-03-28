from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class GlobalReviewerTest(unittest.TestCase):
    def test_suggested_commands_use_cross_platform_python_entrypoint(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-global-reviewer" / "scripts" / "logics_global_review.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_demo.md"
            request.parent.mkdir(parents=True, exist_ok=True)
            request.write_text(
                "\n".join(
                    [
                        "## req_000_demo - Demo request",
                        "> From version: 1.0.0",
                        "> Status: Ready",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "",
                        "# Needs",
                        "- Demo request for global reviewer output.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("## Suggested commands", completed.stdout)
            self.assertIn("`python logics/skills/logics-doc-linter/scripts/logics_lint.py`", completed.stdout)
            self.assertNotIn("python3 logics/skills/", completed.stdout)

    def test_decorated_progress_is_bucketed_like_plain_progress(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-global-reviewer" / "scripts" / "logics_global_review.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = repo / "logics" / "tasks" / "task_000_demo.md"
            task.parent.mkdir(parents=True, exist_ok=True)
            task.write_text(
                "\n".join(
                    [
                        "## task_000_demo - Demo task",
                        "> From version: 1.0.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 100% (audit-aligned)",
                        "",
                        "# Context",
                        "- Demo task for progress parsing.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("| 100% | 1 |", completed.stdout)
            self.assertIn("| (invalid) | 0 |", completed.stdout)


if __name__ == "__main__":
    unittest.main()
