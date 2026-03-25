from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


class LogicsFlowTest(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_flow.py"

    def _cli_script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics.py"

    def _flow_manager_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager"

    def _fixtures_root(self) -> Path:
        return Path(__file__).resolve().parent / "fixtures"

    def _write_doc(self, path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _install_flow_templates(self, repo: Path) -> None:
        source_root = self._flow_manager_root()
        target_root = repo / "logics" / "skills" / "logics-flow-manager"
        for template_name in ("request.md", "backlog.md", "task.md"):
            source = source_root / "assets" / "templates" / template_name
            target = target_root / "assets" / "templates" / template_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def _install_skill_fixture(self, repo: Path, fixture_name: str, skill_name: str) -> Path:
        source = self._fixtures_root() / fixture_name
        target = repo / "logics" / "skills" / skill_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return target

    def _status(self, path: Path) -> str | None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("> Status:"):
                return line.split(":", 1)[1].strip()
        return None

    def _progress(self, path: Path) -> str | None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("> Progress:"):
                return line.split(":", 1)[1].strip()
        return None

    def test_finish_task_closes_linked_backlog_and_request(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            backlog = repo / "logics" / "backlog" / "item_000_demo_item.md"
            task = repo / "logics" / "tasks" / "task_000_demo_task.md"

            self._write_doc(
                request,
                [
                    "## req_000_demo_request - Demo request",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Backlog",
                    "- `item_000_demo_item`",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_demo_item - Demo item",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_demo_task - Demo task",
                    "> From version: 1.0.0",
                    "> Status: In progress",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 80%",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_demo_item`",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "finish", "task", str(task)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Finish verification: OK", result.stdout)
            self.assertEqual(self._status(task), "Done")
            self.assertEqual(self._progress(task), "100%")
            self.assertEqual(self._status(backlog), "Done")
            self.assertEqual(self._progress(backlog), "100%")
            self.assertEqual(self._status(request), "Done")

    def test_finish_task_fails_when_backlog_has_no_request_link(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            backlog = repo / "logics" / "backlog" / "item_000_demo_item.md"
            task = repo / "logics" / "tasks" / "task_000_demo_task.md"

            self._write_doc(
                backlog,
                [
                    "## item_000_demo_item - Demo item",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Demo",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_demo_task - Demo task",
                    "> From version: 1.0.0",
                    "> Status: In progress",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 80%",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_demo_item`",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "finish", "task", str(task)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Finish verification failed:", result.stderr)
            self.assertIn("linked backlog item `item_000_demo_item` has no request reference", result.stderr)

    def test_finish_task_ignores_truncated_mermaid_signature_refs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_harden_windows_compatibility_across_the_vs_code_plugin_and_logics_kit.md"
            backlog = repo / "logics" / "backlog" / "item_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection.md"
            task = repo / "logics" / "tasks" / "task_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection.md"

            self._write_doc(
                request,
                [
                    "## req_000_harden_windows_compatibility_across_the_vs_code_plugin_and_logics_kit - Demo request",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Backlog",
                    "- `item_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection`",
                    "",
                    "```mermaid",
                    "%% logics-kind: request",
                    "%% logics-signature: request|harden-windows-compatibility-across-the|workflow-source",
                    "flowchart LR",
                    "    A[Request] --> B[Backlog]",
                    "```",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection - Demo backlog",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Links",
                    "- Request: `req_000_harden_windows_compatibility_across_the_vs_code_plugin_and_logics_kit`",
                    "",
                    "```mermaid",
                    "%% logics-kind: backlog",
                    "%% logics-signature: backlog|harden-windows-support-for-extension-|req-000-harden-windows-compatibility-acr",
                    "flowchart LR",
                    "    A[Request] --> B[Backlog]",
                    "```",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection - Demo task",
                    "> From version: 1.0.0",
                    "> Status: In progress",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 80%",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection`",
                    "",
                    "```mermaid",
                    "%% logics-kind: task",
                    "%% logics-signature: task|harden-windows-support-for-extension-|item-000-harden-windows-support-for-extens",
                    "flowchart LR",
                    "    A[Backlog] --> B[Done]",
                    "```",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "finish", "task", str(task)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Finish verification: OK", result.stdout)
            task_text = task.read_text(encoding="utf-8")
            backlog_text = backlog.read_text(encoding="utf-8")
            request_text = request.read_text(encoding="utf-8")
            self.assertIn("> Status: Done", task_text)
            self.assertIn("> Status: Done", backlog_text)
            self.assertIn("> Status: Done", request_text)
            self.assertNotIn(
                "missing linked backlog item `item_000_harden_windows_support_for_extens`",
                result.stderr,
            )

    def test_promotions_preserve_product_and_architecture_refs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_guest_checkout.md"
            self._write_doc(
                request,
                [
                    "## req_000_guest_checkout - Guest checkout",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Context",
                    "- Related product brief: `prod_003_guest_checkout_framing`",
                    "- Related architecture decision: `adr_004_checkout_session_strategy`",
                ],
            )

            backlog_result = subprocess.run(
                [sys.executable, str(script), "promote", "request-to-backlog", str(request)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(backlog_result.returncode, 0, backlog_result.stderr)

            backlog = repo / "logics" / "backlog" / "item_000_guest_checkout.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("- Product brief(s): `prod_003_guest_checkout_framing`", backlog_text)
            self.assertIn("- Architecture decision(s): `adr_004_checkout_session_strategy`", backlog_text)

            task_result = subprocess.run(
                [sys.executable, str(script), "promote", "backlog-to-task", str(backlog)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(task_result.returncode, 0, task_result.stderr)

            task = repo / "logics" / "tasks" / "task_000_guest_checkout.md"
            task_text = task.read_text(encoding="utf-8")
            self.assertIn("- Product brief(s): `prod_003_guest_checkout_framing`", task_text)
            self.assertIn("- Architecture decision(s): `adr_004_checkout_session_strategy`", task_text)

    def test_new_backlog_can_auto_create_product_and_architecture_docs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "new",
                    "backlog",
                    "--title",
                    "Checkout auth migration",
                    "--auto-create-product-brief",
                    "--auto-create-adr",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            backlog = repo / "logics" / "backlog" / "item_000_checkout_auth_migration.md"
            product = repo / "logics" / "product" / "prod_000_checkout_auth_migration.md"
            architecture = repo / "logics" / "architecture" / "adr_000_checkout_auth_migration.md"

            self.assertTrue(backlog.is_file())
            self.assertTrue(product.is_file())
            self.assertTrue(architecture.is_file())

            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("- Product framing: Required", backlog_text)
            self.assertIn("- Architecture framing: Required", backlog_text)
            self.assertIn("- Product brief(s): `prod_000_checkout_auth_migration`", backlog_text)
            self.assertIn("- Architecture decision(s): `adr_000_checkout_auth_migration`", backlog_text)

    def test_new_request_recreates_missing_request_directory(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()
            self.assertFalse((repo / "logics" / "request").exists())

            result = subprocess.run(
                [sys.executable, str(script), "new", "request", "--title", "Recovered request directory"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            request_files = sorted((repo / "logics" / "request").glob("req_*.md"))
            self.assertEqual(len(request_files), 1)
            self.assertTrue(request_files[0].is_file())

    def test_new_backlog_recreates_missing_backlog_directory(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()
            self.assertFalse((repo / "logics" / "backlog").exists())

            result = subprocess.run(
                [sys.executable, str(script), "new", "backlog", "--title", "Recovered backlog directory"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            backlog_files = sorted((repo / "logics" / "backlog").glob("item_*.md"))
            self.assertEqual(len(backlog_files), 1)
            self.assertTrue(backlog_files[0].is_file())

    def test_new_task_recreates_missing_task_directory(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()
            self.assertFalse((repo / "logics" / "tasks").exists())

            result = subprocess.run(
                [sys.executable, str(script), "new", "task", "--title", "Recovered task directory"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_files = sorted((repo / "logics" / "tasks").glob("task_*.md"))
            self.assertEqual(len(task_files), 1)
            self.assertTrue(task_files[0].is_file())

    def test_request_to_backlog_updates_request_companion_section(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_checkout_auth_migration.md"
            self._write_doc(
                request,
                [
                    "## req_000_checkout_auth_migration - Checkout auth migration",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Context",
                    "- Imported request that should trigger companions.",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "promote",
                    "request-to-backlog",
                    str(request),
                    "--auto-create-product-brief",
                    "--auto-create-adr",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            request_text = request.read_text(encoding="utf-8")
            self.assertIn("# Companion docs", request_text)
            self.assertIn("- Product brief(s): `prod_000_checkout_auth_migration`", request_text)
            self.assertIn("- Architecture decision(s): `adr_000_checkout_auth_migration`", request_text)

    def test_request_to_backlog_seeds_indicators_problem_and_ac_traceability(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_seeded_request.md"
            self._write_doc(
                request,
                [
                    "## req_000_seeded_request - Seeded request",
                    "> From version: 1.9.1",
                    "> Status: Ready",
                    "> Understanding: 91%",
                    "> Confidence: 88%",
                    "> Complexity: High",
                    "> Theme: Workflow",
                    "",
                    "# Needs",
                    "- Remove repetitive manual cleanup",
                    "",
                    "# Context",
                    "- Promotion should carry useful data forward.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: promotion preserves useful indicators",
                    "- AC2: backlog AC traceability is seeded",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "promote", "request-to-backlog", str(request)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            backlog = repo / "logics" / "backlog" / "item_000_seeded_request.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("> From version: 1.9.1", backlog_text)
            self.assertIn("> Understanding: 91%", backlog_text)
            self.assertIn("> Confidence: 88%", backlog_text)
            self.assertIn("> Complexity: High", backlog_text)
            self.assertIn("> Theme: Workflow", backlog_text)
            self.assertIn("- Remove repetitive manual cleanup", backlog_text)
            self.assertIn("- AC1: promotion preserves useful indicators", backlog_text)
            self.assertIn("- AC1 -> Scope: promotion preserves useful indicators. Proof: TODO.", backlog_text)
            self.assertIn("- AC2 -> Scope: backlog AC traceability is seeded. Proof: TODO.", backlog_text)
            self.assertIn("# AI Context", backlog_text)
            self.assertIn("- Summary: Remove repetitive manual cleanup", backlog_text)
            self.assertIn("- Use when: Use when implementing or reviewing the delivery slice for Seeded request.", backlog_text)

    def test_frontend_oriented_request_surfaces_ui_steering_reference_through_promotion(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_react_admin_ui.md"
            self._write_doc(
                request,
                [
                    "## req_000_react_admin_ui - React admin UI",
                    "> From version: 1.10.5",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Improve the React admin UI",
                    "",
                    "# Context",
                    "- This workflow is focused on a user-facing webview interface.",
                ],
            )

            backlog_result = subprocess.run(
                [sys.executable, str(script), "promote", "request-to-backlog", str(request)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(backlog_result.returncode, 0, backlog_result.stderr)

            backlog = repo / "logics" / "backlog" / "item_000_react_admin_ui.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("# References", backlog_text)
            self.assertIn("- `logics/skills/logics-ui-steering/SKILL.md`", backlog_text)

            task_result = subprocess.run(
                [sys.executable, str(script), "promote", "backlog-to-task", str(backlog)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(task_result.returncode, 0, task_result.stderr)

            task = repo / "logics" / "tasks" / "task_000_react_admin_ui.md"
            task_text = task.read_text(encoding="utf-8")
            self.assertIn("# References", task_text)
            self.assertIn("- `logics/skills/logics-ui-steering/SKILL.md`", task_text)

    def test_promotions_generate_context_aware_mermaid_signatures(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_admin_read_flow.md"
            self._write_doc(
                request,
                [
                    "## req_000_admin_read_flow - Admin read flow",
                    "> From version: 1.10.5",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Double click should open the read panel",
                    "",
                    "# Context",
                    "- The board and list should behave consistently for operators.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: double click opens read from board and list items",
                ],
            )

            backlog_result = subprocess.run(
                [sys.executable, str(script), "promote", "request-to-backlog", str(request)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(backlog_result.returncode, 0, backlog_result.stderr)

            backlog = repo / "logics" / "backlog" / "item_000_admin_read_flow.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("%% logics-kind: backlog", backlog_text)
            self.assertIn("%% logics-signature: backlog|admin-read-flow|req-000-admin-read-flow", backlog_text)
            self.assertIn("Double click should open the read panel", backlog_text)
            self.assertNotIn("Request source", backlog_text)

            task_result = subprocess.run(
                [sys.executable, str(script), "promote", "backlog-to-task", str(backlog)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(task_result.returncode, 0, task_result.stderr)

            task = repo / "logics" / "tasks" / "task_000_admin_read_flow.md"
            task_text = task.read_text(encoding="utf-8")
            self.assertIn("%% logics-kind: task", task_text)
            self.assertIn("%% logics-signature: task|admin-read-flow|item-000-admin-read-flow", task_text)
            self.assertIn("Confirm scope dependencies and linked", task_text)
            self.assertNotIn("Backlog source", task_text)

    def test_split_request_creates_multiple_backlog_items(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_split_me.md"
            self._write_doc(
                request,
                [
                    "## req_000_split_me - Split me",
                    "> From version: 1.9.1",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- One request covering two deliveries",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "split",
                    "request",
                    str(request),
                    "--title",
                    "First delivery slice",
                    "--title",
                    "Second delivery slice",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            backlog_files = sorted((repo / "logics" / "backlog").glob("item_*.md"))
            self.assertEqual(len(backlog_files), 2)
            request_text = request.read_text(encoding="utf-8")
            self.assertIn("item_000_first_delivery_slice", request_text)
            self.assertIn("item_001_second_delivery_slice", request_text)

    def test_split_backlog_creates_multiple_tasks_and_updates_task_links(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            backlog = repo / "logics" / "backlog" / "item_000_split_me.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_split_me - Split me",
                    "> From version: 1.9.1",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- One backlog item covering two implementation tasks",
                    "",
                    "# Acceptance criteria",
                    "- AC1: tasks are created",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "split",
                    "backlog",
                    str(backlog),
                    "--title",
                    "Implementation slice A",
                    "--title",
                    "Implementation slice B",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_files = sorted((repo / "logics" / "tasks").glob("task_*.md"))
            self.assertEqual(len(task_files), 2)
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("task_000_implementation_slice_a", backlog_text)
            self.assertIn("task_001_implementation_slice_b", backlog_text)
            task_text = task_files[0].read_text(encoding="utf-8")
            self.assertIn("- AC1 -> Scope: tasks are created. Proof: TODO.", task_text)

    def test_new_backlog_includes_decision_follow_up_guidance(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "new",
                    "backlog",
                    "--title",
                    "Checkout auth migration",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            backlog = repo / "logics" / "backlog" / "item_000_checkout_auth_migration.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("- Product follow-up: Create or link a product brief before implementation moves deeper into delivery.", backlog_text)
            self.assertIn("- Architecture follow-up: Create or link an architecture decision before irreversible implementation work starts.", backlog_text)

    def test_finish_task_appends_validation_report_and_backlog_note(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            backlog = repo / "logics" / "backlog" / "item_000_demo_item.md"
            task = repo / "logics" / "tasks" / "task_000_demo_task.md"

            self._write_doc(
                request,
                [
                    "## req_000_demo_request - Demo request",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Backlog",
                    "- `item_000_demo_item`",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_demo_item - Demo item",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                    "",
                    "# Notes",
                    "- Existing note",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_demo_task - Demo task",
                    "> From version: 1.0.0",
                    "> Status: In progress",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 80%",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_demo_item`",
                    "",
                    "# Validation",
                    "- Existing validation",
                    "",
                    "# Definition of Done (DoD)",
                    "- [ ] Scope implemented and acceptance criteria covered.",
                    "- [ ] Validation commands executed and results captured.",
                    "",
                    "# Report",
                    "- Existing report",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "finish", "task", str(task)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_text = task.read_text(encoding="utf-8")
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("- Finish workflow executed on ", task_text)
            self.assertIn("- Linked backlog/request close verification passed.", task_text)
            self.assertIn("- Finished on ", task_text)
            self.assertIn("- Linked backlog item(s): `item_000_demo_item`", task_text)
            self.assertIn("- Related request(s): `req_000_demo_request`", task_text)
            self.assertIn("- Task `task_000_demo_task` was finished via `logics_flow.py finish task` on ", backlog_text)

    def test_sync_refresh_mermaid_signatures_updates_stale_workflow_docs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            self._write_doc(
                request,
                [
                    "## req_000_demo_request - Demo request",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Keep signatures aligned",
                    "",
                    "# Context",
                    "- Operators edit docs manually",
                    "",
                    "# Acceptance criteria",
                    "- AC1: Signatures can be refreshed safely",
                    "",
                    "```mermaid",
                    "%% logics-kind: request",
                    "%% logics-signature: request|stale|signature",
                    "flowchart LR",
                    "    A[Edit] --> B[Refresh]",
                    "```",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "sync", "refresh-mermaid-signatures"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Refreshed Mermaid signatures in 1 workflow doc(s).", result.stdout)
            refreshed = request.read_text(encoding="utf-8")
            self.assertIn(
                "%% logics-signature: request|demo-request|keep-signatures-aligned|ac1-signatures-can-be-refreshed-safely",
                refreshed,
            )
            self.assertNotIn("%% logics-signature: request|stale|signature", refreshed)

    def test_promoted_task_includes_wave_checkpoint_guidance(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)
            backlog = repo / "logics" / "backlog" / "item_000_demo_backlog.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_demo_backlog - Demo backlog",
                    "> From version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Demo problem",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The task carries delivery checkpoints",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                ],
            )

            result = subprocess.run(
                [sys.executable, str(script), "promote", "backlog-to-task", str(backlog)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            created_task = next((repo / "logics" / "tasks").glob("task_*.md"))
            task_text = created_task.read_text(encoding="utf-8")
            self.assertIn("# Delivery checkpoints", task_text)
            self.assertIn("commit-ready state", task_text)
            self.assertIn("CHECKPOINT: leave the current wave commit-ready", task_text)
            self.assertIn("Each completed wave left a commit-ready checkpoint", task_text)
            self.assertIn("# AI Context", task_text)
            self.assertIn("- Use when: Use when executing the current implementation wave for Demo backlog.", task_text)

    def test_new_request_json_output_includes_machine_readable_payload(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "new",
                    "request",
                    "--title",
                    "JSON request",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "new")
            self.assertEqual(payload["kind"], "request")
            self.assertEqual(payload["ref"], "req_000_json_request")
            self.assertEqual(payload["path"], "logics/request/req_000_json_request.md")
            self.assertTrue((repo / payload["path"]).is_file())
            self.assertTrue(any("Wrote" in line for line in payload["logs"]))

    def test_sync_migrate_schema_preview_and_apply_support_json_output(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_schema_gap.md"
            self._write_doc(
                request,
                [
                    "## req_000_schema_gap - Schema gap",
                    "> From version: 1.0.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Backfill compact AI context",
                    "",
                    "# Context",
                    "- This doc predates the explicit schema version indicator.",
                ],
            )

            preview = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "migrate-schema",
                    "req_000_schema_gap",
                    "--refresh-ai-context",
                    "--preview",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_payload = json.loads(preview.stdout)
            self.assertTrue(preview_payload["ok"])
            self.assertTrue(preview_payload["preview"])
            self.assertEqual(len(preview_payload["modified_files"]), 1)
            self.assertEqual(preview_payload["modified_files"][0]["reason"], "migrate workflow schema")
            self.assertIn("> From version: 1.0.0", request.read_text(encoding="utf-8"))
            self.assertNotIn("> Schema version:", request.read_text(encoding="utf-8"))

            apply = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "migrate-schema",
                    "req_000_schema_gap",
                    "--refresh-ai-context",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(apply.returncode, 0, apply.stderr)
            applied_payload = json.loads(apply.stdout)
            self.assertTrue(applied_payload["ok"])
            migrated_text = request.read_text(encoding="utf-8")
            self.assertIn("> Schema version: 1.0", migrated_text)
            self.assertIn("# AI Context", migrated_text)

            status = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "schema-status",
                    "req_000_schema_gap",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["current_schema_version"], "1.0")
            self.assertEqual(status_payload["counts"]["1.0"], 1)
            self.assertFalse(status_payload["missing"])

    def test_sync_context_pack_and_export_graph_support_json_output(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_context_seed.md"
            backlog = repo / "logics" / "backlog" / "item_000_context_seed.md"
            task = repo / "logics" / "tasks" / "task_000_context_seed.md"

            self._write_doc(
                request,
                [
                    "## req_000_context_seed - Context seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Keep context packs compact",
                    "",
                    "# Acceptance criteria",
                    "- AC1: include direct workflow neighbors",
                    "",
                    "# AI Context",
                    "- Summary: Keep context packs compact and deterministic.",
                    "- Keywords: context-pack, workflow, kit",
                    "- Use when: Use when building a compact handoff for the seeded request.",
                    "- Skip when: Skip when another workflow ref is the active entrypoint.",
                    "",
                    "# Backlog",
                    "- `item_000_context_seed`",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_context_seed - Context seed backlog",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Keep kit-native context-pack output stable.",
                    "",
                    "# AI Context",
                    "- Summary: Backlog slice for the context-pack output.",
                    "- Keywords: backlog, context-pack, kit",
                    "- Use when: Use when executing the compact context-pack backlog slice.",
                    "- Skip when: Skip when another backlog item is active.",
                    "",
                    "# Links",
                    "- Request: `req_000_context_seed`",
                    "- Task(s): `task_000_context_seed`",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_context_seed - Context seed task",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Context",
                    "- Implement the context-pack output contract.",
                    "",
                    "# AI Context",
                    "- Summary: Task slice for the context-pack output contract.",
                    "- Keywords: task, context-pack, output",
                    "- Use when: Use when executing the context-pack task slice.",
                    "- Skip when: Skip when another task is active.",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_context_seed`",
                ],
            )

            pack = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "context-pack",
                    "req_000_context_seed",
                    "--mode",
                    "summary-only",
                    "--profile",
                    "tiny",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(pack.returncode, 0, pack.stderr)
            pack_payload = json.loads(pack.stdout)
            self.assertEqual(pack_payload["sync_kind"], "context-pack")
            self.assertEqual(pack_payload["budgets"]["max_docs"], 2)
            self.assertEqual(pack_payload["estimates"]["doc_count"], 2)
            self.assertEqual(pack_payload["docs"][0]["ref"], "req_000_context_seed")
            self.assertEqual(pack_payload["docs"][1]["ref"], "item_000_context_seed")

            graph = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "export-graph",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(graph.returncode, 0, graph.stderr)
            graph_payload = json.loads(graph.stdout)
            node_refs = {node["ref"] for node in graph_payload["nodes"]}
            edges = {(edge["from"], edge["to"]) for edge in graph_payload["edges"]}
            self.assertEqual(node_refs, {"req_000_context_seed", "item_000_context_seed", "task_000_context_seed"})
            self.assertIn(("req_000_context_seed", "item_000_context_seed"), edges)
            self.assertIn(("item_000_context_seed", "req_000_context_seed"), edges)
            self.assertIn(("item_000_context_seed", "task_000_context_seed"), edges)

    def test_sync_skill_registry_doctor_and_benchmark_support_json_output(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for directory in ("logics/request", "logics/backlog", "logics/tasks", "logics/skills", "logics/skills/changelogs"):
                (repo / directory).mkdir(parents=True, exist_ok=True)

            self._write_doc(
                repo / "logics" / "request" / "req_000_doctor_check.md",
                [
                    "## req_000_doctor_check - Doctor check",
                    "> From version: 1.0.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Trigger schema diagnostics",
                ],
            )
            self._install_skill_fixture(repo, "skill_package_valid", "fixture-valid-skill")
            self._install_skill_fixture(repo, "skill_package_invalid", "fixture-invalid-skill")
            (repo / "logics" / "skills" / "changelogs" / "CHANGELOGS_1_2_3.md").write_text(
                "# Changelog\n- Added registry export\n- Added doctor diagnostics\n",
                encoding="utf-8",
            )

            validate = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "validate-skills",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(validate.returncode, 0, validate.stderr)
            validate_payload = json.loads(validate.stdout)
            self.assertEqual(validate_payload["skill_count"], 2)
            self.assertFalse(validate_payload["ok"])
            self.assertEqual(validate_payload["issues"][0]["skill"], "fixture-invalid-skill")

            doctor = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "doctor",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            doctor_payload = json.loads(doctor.stdout)
            doctor_codes = {issue["code"] for issue in doctor_payload["issues"]}
            self.assertIn("invalid_skill_package", doctor_codes)
            self.assertIn("missing_schema_version", doctor_codes)

            registry = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "export-registry",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(registry.returncode, 0, registry.stderr)
            registry_payload = json.loads(registry.stdout)
            self.assertEqual(registry_payload["schema_version"], "1.0")
            self.assertEqual(registry_payload["releases"][0]["version"], "1.2.3")
            self.assertEqual(len(registry_payload["skills"]), 2)

            benchmark = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "benchmark-skills",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(benchmark.returncode, 0, benchmark.stderr)
            benchmark_payload = json.loads(benchmark.stdout)
            self.assertEqual(benchmark_payload["skill_count"], 2)
            self.assertGreaterEqual(benchmark_payload["duration_ms"], 0.0)

    def test_sync_dispatch_context_supports_json_output(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "skills").mkdir(parents=True, exist_ok=True)
            request = repo / "logics" / "request" / "req_000_dispatch_seed.md"
            backlog = repo / "logics" / "backlog" / "item_000_dispatch_seed.md"
            task = repo / "logics" / "tasks" / "task_000_dispatch_seed.md"

            self._write_doc(
                request,
                [
                    "## req_000_dispatch_seed - Dispatch seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Turn local model output into guarded workflow actions.",
                    "",
                    "# AI Context",
                    "- Summary: Seed request for local dispatcher tests.",
                    "- Keywords: dispatcher, workflow, local",
                    "- Use when: Use when testing local dispatcher context assembly.",
                    "- Skip when: Skip when another workflow ref is active.",
                    "",
                    "# Backlog",
                    "- `item_000_dispatch_seed`",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_dispatch_seed - Dispatch seed backlog",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Convert requests into executable slices safely.",
                    "",
                    "# Links",
                    "- Request: `req_000_dispatch_seed`",
                    "- Task(s): `task_000_dispatch_seed`",
                ],
            )
            self._write_doc(
                task,
                [
                    "## task_000_dispatch_seed - Dispatch seed task",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Context",
                    "- Provide a deterministic runner for local dispatch.",
                    "",
                    "# Links",
                    "- Backlog item: `item_000_dispatch_seed`",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "dispatch-context",
                    "req_000_dispatch_seed",
                    "--include-graph",
                    "--include-registry",
                    "--include-doctor",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["sync_kind"], "dispatch-context")
            self.assertEqual(payload["seed_ref"], "req_000_dispatch_seed")
            self.assertEqual(payload["context_pack"]["ref"], "req_000_dispatch_seed")
            self.assertIn("graph", payload)
            self.assertEqual(payload["graph"]["seed_ref"], "req_000_dispatch_seed")
            self.assertIn("registry", payload)
            self.assertEqual(payload["registry"]["skill_count"], 0)
            self.assertIn("doctor", payload)
            self.assertTrue(payload["doctor"]["ok"])

    def test_sync_dispatch_suggestion_only_validates_and_maps_inline_payload(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)
            request = repo / "logics" / "request" / "req_000_dispatch_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_dispatch_seed - Dispatch seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Convert a request into an executable backlog slice.",
                ],
            )

            decision = json.dumps(
                {
                    "action": "promote",
                    "target_ref": "req_000_dispatch_seed",
                    "proposed_args": {},
                    "rationale": "A request should be promoted into a backlog item before implementation.",
                    "confidence": 0.84,
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "dispatch",
                    "req_000_dispatch_seed",
                    "--decision-json",
                    decision,
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["executed"])
            self.assertEqual(payload["decision_source"], "inline")
            self.assertEqual(payload["validated_decision"]["action"], "promote")
            self.assertEqual(payload["mapped_command"]["argv"][:2], ["promote", "request-to-backlog"])
            self.assertFalse((repo / "logics" / "backlog" / "item_000_dispatch_seed.md").exists())

            audit_path = repo / payload["audit_log"]
            self.assertTrue(audit_path.is_file())
            audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(audit_lines), 1)
            audit_record = json.loads(audit_lines[0])
            self.assertEqual(audit_record["execution_mode"], "suggestion-only")
            self.assertEqual(audit_record["validated_decision"]["target_ref"], "req_000_dispatch_seed")
            self.assertIsNone(audit_record["execution_result"])

    def test_sync_dispatch_execute_runs_mapped_command_and_appends_audit_log(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)
            request = repo / "logics" / "request" / "req_000_dispatch_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_dispatch_seed - Dispatch seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Convert a request into an executable backlog slice.",
                ],
            )

            decision = json.dumps(
                {
                    "action": "promote",
                    "target_ref": "req_000_dispatch_seed",
                    "proposed_args": {},
                    "rationale": "A request should be promoted into a backlog item before implementation.",
                    "confidence": 0.91,
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "dispatch",
                    "req_000_dispatch_seed",
                    "--decision-json",
                    decision,
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            self.assertEqual(payload["execution_result"]["command"], "promote")
            backlog = repo / "logics" / "backlog" / "item_000_dispatch_seed.md"
            self.assertTrue(backlog.is_file())

            audit_record = json.loads((repo / payload["audit_log"]).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(audit_record["execution_mode"], "execute")
            self.assertEqual(audit_record["execution_result"]["command"], "promote")

    def test_sync_dispatch_returns_structured_error_for_invalid_payload(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_dispatch_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_dispatch_seed - Dispatch seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Reject invalid dispatcher payloads.",
                ],
            )

            decision = json.dumps(
                {
                    "action": "finish",
                    "target_ref": "req_000_dispatch_seed",
                    "proposed_args": {},
                    "rationale": "This is intentionally invalid for a request target.",
                    "confidence": 0.5,
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "sync",
                    "dispatch",
                    "req_000_dispatch_seed",
                    "--decision-json",
                    decision,
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "dispatcher_invalid_finish_target")

    def test_sync_dispatch_ollama_adapter_supports_local_http_backend(self) -> None:
        script = self._script()

        class OllamaHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                request_payload = json.loads(body)
                response_payload = {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "sync",
                                "target_ref": None,
                                "proposed_args": {"sync_kind": "doctor"},
                                "rationale": "Start with a safe health check before mutating workflow docs.",
                                "confidence": 0.88,
                            }
                        )
                    },
                    "echo_model": request_payload["model"],
                }
                encoded = json.dumps(response_payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_dispatch_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_dispatch_seed - Dispatch seed",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Verify the local Ollama adapter path.",
                ],
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "sync",
                        "dispatch",
                        "req_000_dispatch_seed",
                        "--model",
                        "fake-dispatcher",
                        "--ollama-host",
                        f"http://127.0.0.1:{server.server_port}",
                        "--format",
                        "json",
                    ],
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["decision_source"], "ollama")
            self.assertEqual(payload["validated_decision"]["action"], "sync")
            self.assertEqual(payload["validated_decision"]["proposed_args"]["sync_kind"], "doctor")
            self.assertEqual(payload["transport"]["model"], "fake-dispatcher")
            self.assertIn("request_payload", payload["transport"])

    def test_split_policy_uses_repo_config_and_allows_override(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)
            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "workflow:",
                        "  split:",
                        "    policy: minimal-coherent",
                        "    max_children_without_override: 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            request = repo / "logics" / "request" / "req_000_split_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_split_seed - Split seed",
                    "> From version: 1.2.0",
                    "> Schema version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Acceptance criteria",
                    "- AC1: keep splits coherent",
                ],
            )

            blocked = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "split",
                    "request",
                    str(request),
                    "--title",
                    "Slice A",
                    "--title",
                    "Slice B",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 1)
            self.assertIn("minimal-coherent", blocked.stderr)

            allowed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "split",
                    "request",
                    str(request),
                    "--title",
                    "Slice A",
                    "--title",
                    "Slice B",
                    "--allow-extra-slices",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            payload = json.loads(allowed.stdout)
            self.assertEqual(payload["kind"], "request")
            self.assertEqual(len(payload["created_refs"]), 2)

    def test_sync_build_index_reuses_cached_entries(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()
            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "index:",
                        "  enabled: true",
                        "  path: logics/.cache/runtime_index.json",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            request = repo / "logics" / "request" / "req_000_index_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_index_seed - Index seed",
                    "> From version: 1.2.0",
                    "> Schema version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                ],
            )

            first = subprocess.run(
                [sys.executable, str(script), "sync", "build-index", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertGreaterEqual(first_payload["stats"]["cache_misses"], 1)

            second = subprocess.run(
                [sys.executable, str(script), "sync", "build-index", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertGreaterEqual(second_payload["stats"]["cache_hits"], 1)
            self.assertTrue((repo / "logics" / ".cache" / "runtime_index.json").is_file())

    def test_transactional_migrate_schema_rolls_back_on_failure(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "mutations:",
                        "  mode: transactional",
                        "  audit_log: logics/mutation_audit.jsonl",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            request = repo / "logics" / "request" / "req_000_schema_seed.md"
            backlog = repo / "logics" / "backlog" / "item_000_schema_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_schema_seed - Schema seed",
                    "> From version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_schema_seed - Schema seed",
                    "> From version: 1.2.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                ],
            )

            env = dict(os.environ, LOGICS_MUTATION_FAIL_AFTER_WRITES="1")
            failed = subprocess.run(
                [sys.executable, str(script), "sync", "migrate-schema", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(failed.returncode, 1)
            payload = json.loads(failed.stdout)
            self.assertFalse(payload["ok"])

            self.assertNotIn("> Schema version:", request.read_text(encoding="utf-8"))
            self.assertNotIn("> Schema version:", backlog.read_text(encoding="utf-8"))

            audit_lines = (repo / "logics" / "mutation_audit.jsonl").read_text(encoding="utf-8").splitlines()
            audit_record = json.loads(audit_lines[0])
            self.assertEqual(audit_record["status"], "rolled_back")
            self.assertTrue(audit_record["rolled_back"])

    def test_unified_cli_routes_bootstrap_and_config_show(self) -> None:
        script = self._cli_script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            bootstrap = subprocess.run(
                [sys.executable, str(script), "bootstrap", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            bootstrap_payload = json.loads(bootstrap.stdout)
            self.assertTrue(bootstrap_payload["ok"])
            self.assertTrue((repo / "logics.yaml").is_file())

            config_show = subprocess.run(
                [sys.executable, str(script), "config", "show", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(config_show.returncode, 0, config_show.stderr)
            config_payload = json.loads(config_show.stdout)
            self.assertEqual(config_payload["config"]["workflow"]["split"]["policy"], "minimal-coherent")
            self.assertEqual(config_payload["config"]["mutations"]["mode"], "transactional")
            self.assertEqual(config_payload["config"]["hybrid_assist"]["default_backend"], "auto")
            self.assertEqual(config_payload["config"]["hybrid_assist"]["default_model_profile"], "deepseek-coder")
            self.assertEqual(config_payload["config"]["hybrid_assist"]["default_model"], "deepseek-coder-v2:16b")
            self.assertIn("qwen-coder", config_payload["config"]["hybrid_assist"]["model_profiles"])

    def test_assist_runtime_status_reports_hybrid_backend_health(self) -> None:
        script = self._script()

        class OllamaStatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/api/version":
                    payload = {"version": "test-ollama"}
                elif self.path == "/api/tags":
                    payload = {"models": [{"name": "deepseek-coder-v2:16b"}]}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / ".claude" / "commands").mkdir(parents=True)
            (repo / ".claude" / "agents").mkdir(parents=True)
            (repo / ".claude" / "commands" / "logics-flow.md").write_text("bridge\n", encoding="utf-8")
            (repo / ".claude" / "agents" / "logics-flow-manager.md").write_text("bridge\n", encoding="utf-8")

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "runtime-status",
                        "--backend",
                        "auto",
                        "--model",
                        "deepseek-coder-v2:16b",
                        "--ollama-host",
                        f"http://127.0.0.1:{server.server_port}",
                        "--format",
                        "json",
                    ],
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["backend"]["selected_backend"], "ollama")
            self.assertTrue(payload["backend"]["healthy"])
            self.assertEqual(payload["backend"]["model_profile"], "deepseek-coder")
            self.assertEqual(payload["active_model_profile"]["name"], "deepseek-coder")
            self.assertTrue(payload["claude_bridge_available"])

    def test_assist_runtime_status_uses_configured_qwen_profile(self) -> None:
        script = self._script()

        class OllamaStatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/api/version":
                    payload = {"version": "test-ollama"}
                elif self.path == "/api/tags":
                    payload = {"models": [{"name": "qwen2.5-coder:14b"}]}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "hybrid_assist:",
                        "  default_model_profile: qwen-coder",
                        "  model_profiles:",
                        "    qwen-coder:",
                        "      family: qwen",
                        "      model: qwen2.5-coder:14b",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "runtime-status",
                        "--backend",
                        "auto",
                        "--ollama-host",
                        f"http://127.0.0.1:{server.server_port}",
                        "--format",
                        "json",
                    ],
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["backend"]["selected_backend"], "ollama")
            self.assertEqual(payload["backend"]["model_profile"], "qwen-coder")
            self.assertEqual(payload["backend"]["configured_model"], "qwen2.5-coder:14b")
            self.assertEqual(payload["backend"]["model"], "qwen2.5-coder:14b")
            self.assertEqual(payload["active_model_profile"]["family"], "qwen")

    def test_assist_run_diff_risk_supports_codex_fallback_and_audit(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            changed = repo / "README.md"
            changed.parent.mkdir(parents=True, exist_ok=True)
            changed.write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "add", "README.md"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            changed.write_text("demo\nchange\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "run",
                    "diff-risk",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["backend_used"], "codex")
            self.assertIn(payload["result"]["risk"], {"low", "medium", "high"})
            self.assertTrue((repo / "logics" / "hybrid_assist_audit.jsonl").is_file())
            self.assertTrue((repo / "logics" / "hybrid_assist_measurements.jsonl").is_file())

    def test_assist_next_step_alias_routes_to_shared_runtime(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_hybrid_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_hybrid_seed - Hybrid seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Promote this request into the next bounded slice.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The request should produce a next-step suggestion.",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "next-step",
                    "req_000_hybrid_seed",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["flow"], "next-step")
            self.assertEqual(payload["result"]["decision"]["action"], "promote")
            self.assertEqual(payload["result"]["decision"]["target_ref"], "req_000_hybrid_seed")

    def test_assist_handoff_and_split_aliases_return_targeted_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_handoff_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_handoff_seed - Handoff seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Prepare a compact handoff packet.",
                    "- Keep the split to the minimum coherent slices.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: Generate a reusable handoff.",
                    "- AC2: Suggest a bounded split.",
                ],
            )

            handoff = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "handoff",
                    "req_000_handoff_seed",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            split = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "suggest-split",
                    "req_000_handoff_seed",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            self.assertEqual(split.returncode, 0, split.stderr)
            handoff_payload = json.loads(handoff.stdout)
            split_payload = json.loads(split.stdout)
            self.assertEqual(handoff_payload["result"]["target_ref"], "req_000_handoff_seed")
            self.assertTrue(handoff_payload["result"]["files_of_interest"])
            self.assertEqual(split_payload["result"]["target_ref"], "req_000_handoff_seed")
            self.assertGreaterEqual(len(split_payload["result"]["suggested_titles"]), 2)

    def test_assist_validation_and_consistency_aliases_return_structured_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True, exist_ok=True)
            validation = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-validation",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            consistency = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "doc-consistency",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertEqual(consistency.returncode, 0, consistency.stderr)
            validation_payload = json.loads(validation.stdout)
            consistency_payload = json.loads(consistency.stdout)
            self.assertIn(validation_payload["result"]["overall"], {"pass", "warning", "fail"})
            self.assertTrue(validation_payload["result"]["commands"])
            self.assertIn(consistency_payload["result"]["overall"], {"clean", "issues-found"})
            self.assertTrue(consistency_payload["result"]["issues"])

    def test_assist_summary_and_closure_aliases_return_structured_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = repo / "logics" / "tasks" / "task_000_summary_seed.md"
            self._write_doc(
                task,
                [
                    "## task_000_summary_seed - Summary seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Done",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 100%",
                    "",
                    "# Context",
                    "- Summarize this delivery.",
                    "",
                    "# Validation",
                    "- python logics/skills/logics.py lint",
                ],
            )

            pr_summary = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-pr",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            changelog = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-changelog",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            closure = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "closure-summary",
                    "task_000_summary_seed",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(pr_summary.returncode, 0, pr_summary.stderr)
            self.assertEqual(changelog.returncode, 0, changelog.stderr)
            self.assertEqual(closure.returncode, 0, closure.stderr)
            pr_payload = json.loads(pr_summary.stdout)
            changelog_payload = json.loads(changelog.stdout)
            closure_payload = json.loads(closure.stdout)
            self.assertTrue(pr_payload["result"]["highlights"])
            self.assertTrue(changelog_payload["result"]["entries"])
            self.assertEqual(closure_payload["result"]["target_ref"], "task_000_summary_seed")
            self.assertTrue(closure_payload["result"]["delivered"])

    def test_assist_validation_checklist_alias_responds_to_plugin_and_runtime_changes(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (repo / "src").mkdir(parents=True, exist_ok=True)
            (repo / "src" / "feature.ts").write_text("export const x = 1;\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "validation-checklist",
                    "--backend",
                    "codex",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["result"]["checks"])
            self.assertIn(payload["result"]["profile"], {"docs-only", "runtime", "plugin", "mixed"})

    def test_assist_commit_all_execute_commits_simple_repo(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            readme = repo / "README.md"
            readme.write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            readme.write_text("demo\nmore\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "commit-all",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            self.assertEqual(len(payload["execution_result"]["steps"]), 1)
            log = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(log.returncode, 0, log.stderr)
            self.assertEqual(log.stdout.strip(), payload["execution_result"]["steps"][0]["message"])


if __name__ == "__main__":
    unittest.main()
