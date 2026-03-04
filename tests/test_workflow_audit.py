import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkflowAuditTest(unittest.TestCase):
    def _write_fixture_repo(self, repo: Path) -> None:
        (repo / "logics" / "request").mkdir(parents=True)
        (repo / "logics" / "backlog").mkdir(parents=True)
        (repo / "logics" / "tasks").mkdir(parents=True)

        (repo / "logics" / "request" / "req_000_demo_request.md").write_text(
            "\n".join(
                [
                    "## req_000_demo_request - Demo request",
                    "> From version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Acceptance criteria",
                    "- AC1: first criterion",
                    "- AC2: second criterion",
                    "",
                    "# Definition of Ready (DoR)",
                    "- [x] Problem statement is explicit.",
                    "",
                    "# Backlog",
                    "- `item_000_demo_item`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        (repo / "logics" / "backlog" / "item_000_demo_item.md").write_text(
            "\n".join(
                [
                    "## item_000_demo_item - Demo item",
                    "> From version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Demo",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        (repo / "logics" / "tasks" / "task_000_demo_task.md").write_text(
            "\n".join(
                [
                    "## task_000_demo_task - Demo task",
                    "> From version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Plan",
                    "- [ ] 1. demo",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_demo_item`",
                    "",
                    "# Definition of Done (DoD)",
                    "- [ ] Scope implemented and acceptance criteria covered.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_json_output_and_ac_autofix(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(repo)

            first_run = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(first_run.returncode, 1, first_run.stderr)
            payload = json.loads(first_run.stdout)
            self.assertFalse(payload["ok"])
            self.assertGreater(payload["issue_count"], 0)
            self.assertIn("ac_missing_item_traceability", payload["counts"]["by_code"])
            self.assertIn("ac_missing_task_traceability", payload["counts"]["by_code"])

            fix_run = subprocess.run(
                [sys.executable, str(script), "--format", "json", "--autofix-ac-traceability"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(fix_run.returncode, 0, fix_run.stderr)
            fix_payload = json.loads(fix_run.stdout)
            self.assertTrue(fix_payload["ok"])
            self.assertGreaterEqual(len(fix_payload["autofix"]["modified_files"]), 2)

            backlog_text = (repo / "logics" / "backlog" / "item_000_demo_item.md").read_text(encoding="utf-8")
            task_text = (repo / "logics" / "tasks" / "task_000_demo_task.md").read_text(encoding="utf-8")

            self.assertIn("# AC Traceability", backlog_text)
            self.assertIn("AC1", backlog_text)
            self.assertIn("Proof: TODO.", backlog_text)
            self.assertIn("# AC Traceability", task_text)
            self.assertIn("AC2", task_text)
            self.assertIn("Proof: TODO.", task_text)


if __name__ == "__main__":
    unittest.main()
