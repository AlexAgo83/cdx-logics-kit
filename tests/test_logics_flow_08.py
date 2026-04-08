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
    def test_assist_request_draft_execute_requires_confirmation_before_writing(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "request-draft",
                    "--intent",
                    "Draft a request for a release recap workflow",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                input="n\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["executed"])
            self.assertEqual(payload["execution_result"]["reason"], "operator-declined")
            self.assertFalse((repo / "logics" / "request").exists())

    def test_assist_request_draft_execute_writes_request_doc_after_confirmation(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "request-draft",
                    "--intent",
                    "Draft a request for a release recap workflow",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                input="yes\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            created_path = repo / payload["execution_result"]["created_path"]
            self.assertTrue(created_path.is_file())
            content = created_path.read_text(encoding="utf-8")
            self.assertIn("# Needs", content)
            self.assertIn("# Context", content)
            self.assertIn("release recap workflow", content.lower())
            self.assertNotIn("> From version: X.X.X", content)
            self.assertNotIn("> Understanding: ??%", content)
            self.assertNotIn("> Confidence: ??%", content)

    def test_assist_request_draft_openai_normalizes_multiline_string_lists(self) -> None:
        script = self._script()

        class OpenAIRequestDraftHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps({"id": "gpt-4.1-mini"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(
                                        {
                                            "needs": "- Capture the user problem\n- Keep the request bounded",
                                            "context": "Document constraints and why the request matters now.",
                                            "confidence": 0.84,
                                            "rationale": "The intent is clear enough for a bounded first draft.",
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAIRequestDraftHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1",
                            "      model: gpt-4.1-mini",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "request-draft",
                        "--intent",
                        "Draft a bounded request for mobile release checklists.",
                        "--backend",
                        "openai",
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
            self.assertEqual(payload["backend_used"], "openai")
            self.assertEqual(
                payload["result"]["needs"],
                ["Capture the user problem", "Keep the request bounded"],
            )
            self.assertEqual(
                payload["result"]["context"],
                ["Document constraints and why the request matters now."],
            )

    def test_assist_request_draft_openai_normalizes_structured_mapping_lists(self) -> None:
        script = self._script()

        class OpenAIRequestDraftStructuredHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps({"id": "gpt-4.1-mini"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(
                                        {
                                            "needs": {
                                                "ui": "Give the operator a quick way to capture the request.",
                                                "features": [
                                                    "Keep the scope bounded",
                                                    "Preserve reviewability",
                                                ],
                                            },
                                            "context": {
                                                "workflow": "This should stay proposal-only until the operator confirms it.",
                                                "profile": "normal",
                                            },
                                            "confidence": 0.87,
                                            "rationale": "The intent is concrete enough to turn structured fields into bounded list items.",
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAIRequestDraftStructuredHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1",
                            "      model: gpt-4.1-mini",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "request-draft",
                        "--intent",
                        "Draft a request for a bounded operator capture flow.",
                        "--backend",
                        "openai",
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
            self.assertEqual(payload["backend_used"], "openai")
            self.assertEqual(
                payload["result"]["needs"],
                [
                    "ui: Give the operator a quick way to capture the request.",
                    "features: Keep the scope bounded; Preserve reviewability",
                ],
            )
            self.assertEqual(
                payload["result"]["context"],
                [
                    "workflow: This should stay proposal-only until the operator confirms it.",
                    "profile: normal",
                ],
            )

    def test_assist_spec_first_pass_alias_returns_validated_json_without_writing_specs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            backlog = repo / "logics" / "backlog" / "item_000_spec_seed.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_spec_seed - Spec seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Define a first-pass spec for the delivery slice.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The outline should stay bounded and proposal-only.",
                    "- AC2: The spec should highlight open questions and constraints.",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "spec-first-pass",
                    "item_000_spec_seed",
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
            self.assertEqual(payload["flow"], "spec-first-pass")
            self.assertEqual(payload["backend_used"], "codex")
            self.assertTrue(payload["result"]["sections"])
            self.assertTrue(payload["result"]["open_questions"])
            self.assertTrue(payload["result"]["constraints"])
            self.assertFalse((repo / "logics" / "specs").exists())

            measurement_log = repo / payload["measurement_log"]
            self.assertTrue(measurement_log.is_file())
            measurement_records = [json.loads(line) for line in measurement_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(measurement_records[-1]["flow"], "spec-first-pass")

    def test_assist_spec_first_pass_execute_writes_spec_after_confirmation(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            backlog = repo / "logics" / "backlog" / "item_000_spec_seed.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_spec_seed - Spec seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Define a first-pass spec for the delivery slice.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The outline should stay bounded and proposal-only.",
                    "- AC2: The spec should highlight open questions and constraints.",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "spec-first-pass",
                    "item_000_spec_seed",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                input="yes\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            created_path = repo / payload["execution_result"]["created_path"]
            self.assertTrue(created_path.is_file())
            content = created_path.read_text(encoding="utf-8")
            self.assertIn("# Overview", content)
            self.assertIn("item_000_spec_seed", content)

    def test_assist_spec_first_pass_openai_drops_blank_entries_from_string_lists(self) -> None:
        script = self._script()

        class OpenAISpecFirstPassHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps({"id": "gpt-4.1-mini"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(
                                        {
                                            "sections": ["Summary", "", "Validation"],
                                            "open_questions": "- Which edge cases need deeper traceability?\n\n- Which validations are still missing?",
                                            "constraints": ["Stay proposal-only.", ""],
                                            "confidence": 0.81,
                                            "rationale": "The backlog slice is clear enough for a bounded spec outline.",
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            backlog = repo / "logics" / "backlog" / "item_000_spec_seed.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_spec_seed - Spec seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Define a first-pass spec for the delivery slice.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The outline should stay bounded and proposal-only.",
                    "- AC2: The spec should highlight open questions and constraints.",
                ],
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAISpecFirstPassHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1",
                            "      model: gpt-4.1-mini",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "spec-first-pass",
                        "item_000_spec_seed",
                        "--backend",
                        "openai",
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
            self.assertEqual(payload["backend_used"], "openai")
            self.assertEqual(payload["result"]["sections"], ["Summary", "Validation"])
            self.assertEqual(
                payload["result"]["open_questions"],
                [
                    "Which edge cases need deeper traceability?",
                    "Which validations are still missing?",
                ],
            )
            self.assertEqual(payload["result"]["constraints"], ["Stay proposal-only."])

    def test_assist_spec_first_pass_openai_normalizes_section_objects(self) -> None:
        script = self._script()

        class OpenAISpecStructuredHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps({"id": "gpt-4.1-mini"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(
                                        {
                                            "sections": [
                                                {"title": "Overview", "content": "Summarize the delivery slice."},
                                                {"title": "Validation", "content": "List the checks to run before closure."},
                                            ],
                                            "open_questions": ["Which acceptance criterion needs the deepest traceability?"],
                                            "constraints": {
                                                "mode": "Keep the outline proposal-only.",
                                                "scope": "Do not widen beyond the backlog slice.",
                                            },
                                            "confidence": 0.83,
                                            "rationale": "Structured sections from the remote provider should be normalized into string bullets.",
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            backlog = repo / "logics" / "backlog" / "item_000_spec_seed.md"
            self._write_doc(
                backlog,
                [
                    "## item_000_spec_seed - Spec seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 0%",
                    "",
                    "# Problem",
                    "- Define a first-pass spec for the delivery slice.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The outline should stay bounded and proposal-only.",
                    "- AC2: The spec should highlight open questions and constraints.",
                ],
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAISpecStructuredHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1",
                            "      model: gpt-4.1-mini",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "spec-first-pass",
                        "item_000_spec_seed",
                        "--backend",
                        "openai",
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
            self.assertEqual(payload["backend_used"], "openai")
            self.assertEqual(
                payload["result"]["sections"],
                [
                    "Overview: Summarize the delivery slice.",
                    "Validation: List the checks to run before closure.",
                ],
            )
            self.assertEqual(
                payload["result"]["constraints"],
                [
                    "mode: Keep the outline proposal-only.",
                    "scope: Do not widen beyond the backlog slice.",
                ],
            )

    def test_assist_backlog_groom_alias_returns_validated_json_without_writing_backlog_docs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_groom_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_groom_seed - Groom seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Define a bounded backlog slice for the operator workflow.",
                    "- Keep the proposal cheap and reviewable.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The backlog proposal includes a scoped title.",
                    "- AC2: The backlog proposal includes candidate acceptance criteria.",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "backlog-groom",
                    "req_000_groom_seed",
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
            self.assertEqual(payload["flow"], "backlog-groom")
            self.assertEqual(payload["backend_used"], "codex")
            self.assertTrue(payload["result"]["title"])
            self.assertIn(payload["result"]["complexity"], {"Low", "Medium", "High"})
            self.assertTrue(payload["result"]["acceptance_criteria"])
            self.assertFalse((repo / "logics" / "backlog").exists())

            measurement_log = repo / payload["measurement_log"]
            self.assertTrue(measurement_log.is_file())
            measurement_records = [json.loads(line) for line in measurement_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(measurement_records[-1]["flow"], "backlog-groom")

    def test_assist_backlog_groom_execute_writes_backlog_after_confirmation(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_groom_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_groom_seed - Groom seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Define a bounded backlog slice for the operator workflow.",
                    "- Keep the proposal cheap and reviewable.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The backlog proposal includes a scoped title.",
                    "- AC2: The backlog proposal includes candidate acceptance criteria.",
                    "",
                    "# Backlog",
                    "- (none yet)",
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "backlog-groom",
                    "req_000_groom_seed",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=repo,
                input="yes\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            created_path = repo / payload["execution_result"]["created_path"]
            self.assertTrue(created_path.is_file())
            content = created_path.read_text(encoding="utf-8")
            self.assertIn("# Acceptance criteria", content)
            self.assertIn("Hybrid rationale:", content)
            request_text = request.read_text(encoding="utf-8")
            self.assertIn(payload["execution_result"]["created_ref"], request_text)
