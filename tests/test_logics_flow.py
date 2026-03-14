from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LogicsFlowTest(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_flow.py"

    def _flow_manager_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager"

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


if __name__ == "__main__":
    unittest.main()
