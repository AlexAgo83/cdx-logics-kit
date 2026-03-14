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
            subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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


if __name__ == "__main__":
    unittest.main()
