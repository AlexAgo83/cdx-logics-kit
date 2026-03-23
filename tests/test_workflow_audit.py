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

    def test_required_decision_framing_without_refs_is_reported(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)

            (repo / "logics" / "backlog" / "item_000_checkout.md").write_text(
                "\n".join(
                    [
                        "## item_000_checkout - Checkout framing",
                        "> From version: 1.2.0",
                        "> Status: Ready",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 0%",
                        "",
                        "# Decision framing",
                        "- Product framing: Required",
                        "- Architecture framing: Required",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("product_brief_required_missing_ref", payload["counts"]["by_code"])
            self.assertIn("architecture_decision_required_missing_ref", payload["counts"]["by_code"])

    def test_companion_docs_are_audited_for_links_mermaid_and_placeholders(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "product").mkdir(parents=True)

            (repo / "logics" / "product" / "prod_000_guest_checkout.md").write_text(
                "\n".join(
                    [
                        "## prod_000_guest_checkout - Guest checkout",
                        "> Date: 2026-03-14",
                        "> Status: Proposed",
                        "",
                        "# Overview",
                        "Summarize the product direction, the targeted user value, and the main expected outcomes.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("companion_doc_missing_primary_link", payload["counts"]["by_code"])
            self.assertIn("companion_doc_missing_mermaid", payload["counts"]["by_code"])
            self.assertIn("companion_doc_contains_placeholders", payload["counts"]["by_code"])

    def test_scoped_audit_can_focus_on_specific_ref_chain(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(repo)

            unrelated_request = repo / "logics" / "request" / "req_999_unrelated.md"
            unrelated_request.write_text(
                "\n".join(
                    [
                        "## req_999_unrelated - Unrelated request",
                        "> From version: 1.2.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json", "--refs", "req_000_demo_request"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            issue_paths = {issue["path"] for issue in payload["issues"]}
            self.assertTrue(any(path.endswith("req_000_demo_request.md") for path in issue_paths))
            self.assertFalse(any(path.endswith("req_999_unrelated.md") for path in issue_paths))

    def test_token_hygiene_reports_missing_ai_context_and_verbose_sections(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(repo)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            request.write_text(
                request.read_text(encoding="utf-8").replace(
                    "# Acceptance criteria",
                    "# Context\n"
                    + "\n".join(f"- Extra context line {idx}" for idx in range(1, 30))
                    + "\n\n# Acceptance criteria",
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json", "--token-hygiene"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("token_hygiene_missing_ai_context", payload["counts"]["by_code"])
            self.assertIn("token_hygiene_section_too_long", payload["counts"]["by_code"])

    def test_governance_profile_strict_enables_token_hygiene_by_default(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(repo)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            request.write_text(
                request.read_text(encoding="utf-8").replace(
                    "# Acceptance criteria",
                    "# Context\n"
                    + "\n".join(f"- Verbose line {idx}" for idx in range(1, 28))
                    + "\n\n# Acceptance criteria",
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json", "--governance-profile", "strict"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("token_hygiene_missing_ai_context", payload["counts"]["by_code"])
            self.assertIn("token_hygiene_section_too_long", payload["counts"]["by_code"])

    def test_structural_autofix_adds_schema_ai_context_and_gate_sections(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "workflow_audit.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)

            request = repo / "logics" / "request" / "req_000_structure_fix.md"
            request.write_text(
                "\n".join(
                    [
                        "## req_000_structure_fix - Structure fix",
                        "> From version: 1.0.0",
                        "> Status: Draft",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "",
                        "# Needs",
                        "- Normalize workflow metadata",
                        "",
                        "# Context",
                        "- This request was created before schema and AI Context support.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            task = repo / "logics" / "tasks" / "task_000_structure_fix.md"
            task.write_text(
                "\n".join(
                    [
                        "## task_000_structure_fix - Structure fix task",
                        "> From version: 1.0.0",
                        "> Status: Draft",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                        "> Progress: 0%",
                        "",
                        "# Context",
                        "- Normalize delivery metadata as well.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json", "--autofix-structure"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            request_text = request.read_text(encoding="utf-8")
            task_text = task.read_text(encoding="utf-8")
            self.assertIn("> Schema version: 1.0", request_text)
            self.assertIn("# AI Context", request_text)
            self.assertIn("# Definition of Ready (DoR)", request_text)
            self.assertIn("> Schema version: 1.0", task_text)
            self.assertIn("# AI Context", task_text)
            self.assertIn("# Definition of Done (DoD)", task_text)


if __name__ == "__main__":
    unittest.main()
