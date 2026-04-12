from __future__ import annotations

import importlib.util
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


sys.path.insert(0, str(Path(__file__).resolve().parent))
from logics_flow_test_base import LogicsFlowTestBase

class LogicsFlowTest(LogicsFlowTestBase):
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
                    "- Derived from `item_000_harden_windows_support_for_extension_workflow_actions_and_runtime_detection`",
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
            self.assertIn("Keep this backlog item as one bounded delivery slice", backlog_text)
            self.assertIn("- Remove repetitive manual cleanup", backlog_text)
            self.assertIn("- AC1: promotion preserves useful indicators", backlog_text)
            self.assertIn(
                "- AC1 -> Scope: promotion preserves useful indicators. Proof: capture validation evidence in this doc.",
                backlog_text,
            )
            self.assertIn(
                "- AC2 -> Scope: backlog AC traceability is seeded. Proof: capture validation evidence in this doc.",
                backlog_text,
            )
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

    def test_promotion_normalizes_repo_absolute_markdown_references_to_relative_paths(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._install_flow_templates(repo)

            request = repo / "logics" / "request" / "req_000_reference_cleanup.md"
            self._write_doc(
                request,
                [
                    "## req_000_reference_cleanup - Reference cleanup",
                    "> From version: 1.10.5",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Keep references short.",
                    "",
                    "# References",
                    "- [README](/Users/alexandreagostini/Documents/cdx-logics-vscode/README.md)",
                    "- [flow skill](/Users/alexandreagostini/Documents/cdx-logics-vscode/logics/skills/logics-flow-manager/SKILL.md#L1)",
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

            backlog = repo / "logics" / "backlog" / "item_000_reference_cleanup.md"
            backlog_text = backlog.read_text(encoding="utf-8")
            self.assertIn("- `README.md`", backlog_text)
            self.assertIn("- `logics/skills/logics-flow-manager/SKILL.md`", backlog_text)
            self.assertNotIn("/Users/alexandreagostini/Documents", backlog_text)
