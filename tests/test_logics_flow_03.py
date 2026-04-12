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
                    "- Derived from `item_000_context_seed`",
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
                    "- Derived from `item_000_dispatch_seed`",
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
