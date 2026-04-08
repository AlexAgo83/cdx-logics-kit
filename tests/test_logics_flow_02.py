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
            self.assertIn(
                "- AC1 -> Scope: tasks are created. Proof: capture validation evidence in this doc.",
                task_text,
            )

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
        flow = self._flow_module()

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

            captured: dict[str, object] = {}
            sentinel = "\n".join(
                [
                    "```mermaid",
                    "%% logics-kind: request",
                    "%% logics-signature: request|demo-request|sentinel",
                    "flowchart TD",
                    "    Trigger[Demo request] --> Need[Keep signatures aligned]",
                    "```",
                ]
            )
            original_generate = flow.refresh_workflow_mermaid_signature_file.__globals__["_generate_workflow_mermaid"]

            def fake_generate(repo_root: Path, kind_name: str, title: str, values: dict[str, str], *, dry_run: bool) -> str:
                captured["repo_root"] = repo_root
                captured["kind_name"] = kind_name
                captured["title"] = title
                captured["values"] = dict(values)
                captured["dry_run"] = dry_run
                return sentinel

            flow.refresh_workflow_mermaid_signature_file.__globals__["_generate_workflow_mermaid"] = fake_generate
            try:
                changed = flow.refresh_workflow_mermaid_signature_file(request, "request", False, repo_root=repo)
            finally:
                flow.refresh_workflow_mermaid_signature_file.__globals__["_generate_workflow_mermaid"] = original_generate

            self.assertTrue(changed)
            self.assertEqual(Path(captured["repo_root"]).resolve(), repo.resolve())
            self.assertEqual(captured["kind_name"], "request")
            self.assertEqual(captured["title"], "Demo request")
            self.assertEqual(captured["dry_run"], False)
            self.assertIn("- Keep signatures aligned", str(captured["values"]))
            refreshed = request.read_text(encoding="utf-8")
            self.assertIn(sentinel, refreshed)
            self.assertNotIn("%% logics-signature: request|stale|signature", refreshed)

    def test_cmd_new_routes_mermaid_generation_through_skill_entry_point(self) -> None:
        flow = self._flow_module()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            sentinel = "\n".join(
                [
                    "```mermaid",
                    "%% logics-kind: request",
                    "%% logics-signature: request|generated-via-skill",
                    "flowchart TD",
                    "    Trigger[Generated through skill] --> Need[Wired]",
                    "```",
                ]
            )
            original_generate = flow._generate_workflow_mermaid
            original_refresh_generate = flow.refresh_workflow_mermaid_signature_text.__globals__["_generate_workflow_mermaid"]
            captured: dict[str, object] = {}

            def fake_generate(repo_root: Path, kind_name: str, title: str, values: dict[str, str], *, dry_run: bool) -> str:
                captured["repo_root"] = repo_root
                captured["kind_name"] = kind_name
                captured["title"] = title
                captured["values"] = dict(values)
                captured["dry_run"] = dry_run
                return sentinel

            flow._generate_workflow_mermaid = fake_generate
            flow.refresh_workflow_mermaid_signature_text.__globals__["_generate_workflow_mermaid"] = fake_generate
            previous_cwd = Path.cwd()
            os.chdir(repo)
            try:
                payload = flow.cmd_new(
                    flow.argparse.Namespace(
                        kind="request",
                        title="Demo request",
                        slug=None,
                        from_version="1.2.0",
                        understanding="100%",
                        confidence="100%",
                        status="Draft",
                        progress="0%",
                        complexity="Medium",
                        theme="General",
                        auto_create_product_brief=False,
                        auto_create_adr=False,
                        dry_run=False,
                    )
                )
            finally:
                os.chdir(previous_cwd)
                flow._generate_workflow_mermaid = original_generate
                flow.refresh_workflow_mermaid_signature_text.__globals__["_generate_workflow_mermaid"] = original_refresh_generate

            self.assertEqual(payload["command"], "new")
            self.assertEqual(Path(captured["repo_root"]).resolve(), repo.resolve())
            self.assertEqual(captured["kind_name"], "request")
            self.assertEqual(captured["title"], "Demo request")
            self.assertEqual(captured["dry_run"], False)
            created = repo / payload["path"]
            self.assertTrue(created.is_file())
            self.assertIn(sentinel, created.read_text(encoding="utf-8"))

    def test_cmd_new_request_uses_non_placeholder_defaults(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "new",
                    "request",
                    "--title",
                    "Demo request",
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
            created = repo / payload["path"]
            content = created.read_text(encoding="utf-8")
            self.assertNotIn("> From version: X.X.X", content)
            self.assertNotIn("> Understanding: ??%", content)
            self.assertNotIn("> Confidence: ??%", content)
            self.assertNotIn("Describe the need", content)
            self.assertNotIn("Add context and constraints", content)

    def test_promotions_route_mermaid_generation_through_skill_entry_point(self) -> None:
        flow = self._flow_module()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_demo_request.md"
            backlog = repo / "logics" / "backlog" / "item_000_demo_backlog.md"
            self._write_doc(
                request,
                [
                    "## req_000_demo_request - Demo request",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Route promotions through the shared Mermaid skill",
                    "",
                    "# Context",
                    "- Operators promote docs from requests to backlog items",
                    "",
                    "# Acceptance criteria",
                    "- AC1: Backlog promotion uses the skill entry point",
                ],
            )
            self._write_doc(
                backlog,
                [
                    "## item_000_demo_backlog - Demo backlog",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Route promotions through the shared Mermaid skill",
                    "",
                    "# Acceptance criteria",
                    "- AC1: Task promotion uses the skill entry point",
                    "",
                    "# Links",
                    "- Request: `req_000_demo_request`",
                ],
            )

            captured: list[tuple[str, str]] = []
            original_generate = flow._create_backlog_from_request.__globals__["_generate_workflow_mermaid"]

            def fake_generate(repo_root: Path, kind_name: str, title: str, values: dict[str, str], *, dry_run: bool) -> str:
                captured.append((kind_name, title))
                return "\n".join(
                    [
                        "```mermaid",
                        f"%% logics-kind: {kind_name}",
                        f"%% logics-signature: {kind_name}|generated-via-skill",
                        "flowchart LR",
                        f"    Source[{title}] --> Output[Generated via skill]",
                        "```",
                    ]
                )

            flow._create_backlog_from_request.__globals__["_generate_workflow_mermaid"] = fake_generate
            previous_cwd = Path.cwd()
            os.chdir(repo)
            try:
                backlog_payload = flow.cmd_promote_request_to_backlog(
                    flow.argparse.Namespace(
                        source=str(request),
                        dry_run=False,
                        from_version="1.0.0",
                        understanding="100%",
                        confidence="100%",
                        status="Ready",
                        progress="0%",
                        complexity="Medium",
                        theme="General",
                        auto_create_product_brief=False,
                        auto_create_adr=False,
                    )
                )
                task_payload = flow.cmd_promote_backlog_to_task(
                    flow.argparse.Namespace(
                        source=str(backlog),
                        dry_run=False,
                        from_version="1.0.0",
                        understanding="100%",
                        confidence="100%",
                        status="Ready",
                        progress="0%",
                        complexity="Medium",
                        theme="General",
                        auto_create_product_brief=False,
                        auto_create_adr=False,
                    )
                )
            finally:
                os.chdir(previous_cwd)
                flow._create_backlog_from_request.__globals__["_generate_workflow_mermaid"] = original_generate

            self.assertEqual(
                captured,
                [
                    ("backlog", "Demo request"),
                    ("backlog", "Demo request"),
                    ("task", "Demo backlog"),
                    ("task", "Demo backlog"),
                ],
            )
            self.assertIn("generated-via-skill", (repo / backlog_payload["created_path"]).read_text(encoding="utf-8"))
            self.assertIn("generated-via-skill", (repo / task_payload["created_path"]).read_text(encoding="utf-8"))

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
            self.assertIn("flow assist commit-all", task_text)
            self.assertIn("Do not mark a wave or step complete", task_text)
            self.assertIn("CHECKPOINT: leave the current wave commit-ready", task_text)
            self.assertIn("GATE: do not close a wave or step", task_text)
            self.assertIn("before closing the current wave or step", task_text)
            self.assertIn("Each completed wave left a commit-ready checkpoint", task_text)
            self.assertIn("No wave or step was closed before the relevant automated tests", task_text)
            self.assertIn("# AI Context", task_text)
            self.assertIn("- Use when: Use when executing the current implementation wave for Demo backlog.", task_text)
