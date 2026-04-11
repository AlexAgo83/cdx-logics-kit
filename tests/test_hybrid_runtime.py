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
    def test_assist_run_next_step_stays_on_codex_under_auto_policy_even_when_ollama_is_healthy(self) -> None:
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["backend_used"], "codex")
            self.assertEqual(payload["backend_status"]["policy_mode"], "codex-only")
            self.assertEqual(payload["backend_status"]["selection_reason"], "policy-codex-only")
            self.assertEqual(payload["degraded_reasons"], [])
            self.assertEqual(payload["transport"]["reason"], "policy-codex-only")

    def test_assist_run_next_step_supports_openai_backend_with_validated_response(self) -> None:
        script = self._script()

        class OpenAINextStepHandler(http.server.BaseHTTPRequestHandler):
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
                                            "action": "promote",
                                            "target_ref": "req_000_hybrid_seed",
                                            "proposed_args": {},
                                            "confidence": 0.88,
                                            "rationale": "The request is ready to become a bounded backlog item.",
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAINextStepHandler)
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["result"]["decision"]["action"], "promote")
            self.assertEqual(payload["result"]["decision"]["target_ref"], "req_000_hybrid_seed")

    def test_assist_run_next_step_uses_configured_auto_backend_when_healthy(self) -> None:
        script = self._script()

        class OpenAINextStepAutoHandler(http.server.BaseHTTPRequestHandler):
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
                                            "action": "promote",
                                            "target_ref": "req_000_hybrid_seed",
                                            "proposed_args": {},
                                            "rationale": "The request is ready for promotion.",
                                            "confidence": 0.91,
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
            request = repo / "logics" / "request" / "req_000_hybrid_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_hybrid_seed - Hybrid seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Draft",
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAINextStepAutoHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  next_step_auto_backend: openai",
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["backend_requested"], "auto")
            self.assertEqual(payload["backend_used"], "openai")
            self.assertEqual(payload["backend_status"]["selection_reason"], "config-auto-backend")
            self.assertEqual(payload["context_bundle"]["contract"]["backend_policy"]["auto_backend"], "openai")
            self.assertEqual(payload["result_status"], "ok")

    def test_assist_run_next_step_ignores_extra_new_fields_from_remote_provider(self) -> None:
        script = self._script()

        class OpenAINextStepNewHandler(http.server.BaseHTTPRequestHandler):
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
                                            "action": "new",
                                            "target_ref": None,
                                            "proposed_args": {
                                                "kind": "backlog",
                                                "title": "Demo follow-up slice",
                                                "description": "Extra helper text that should be ignored.",
                                            },
                                            "rationale": "The seeded request needs a bounded backlog follow-up.",
                                            "confidence": 0.86,
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
            request = repo / "logics" / "request" / "req_000_hybrid_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_hybrid_seed - Hybrid seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Break this draft into a bounded follow-up slice.",
                    "",
                    "# Context",
                    "- The seeded request still needs implementation framing.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The next-step decision should stay bounded.",
                ],
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAINextStepNewHandler)
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["result"]["decision"]["action"], "new")
            self.assertEqual(
                payload["result"]["decision"]["proposed_args"],
                {"kind": "backlog", "title": "Demo follow-up slice"},
            )
            self.assertNotIn("description", payload["result"]["decision"]["proposed_args"])

    def test_assist_run_next_step_auto_falls_back_when_remote_new_decision_is_incomplete(self) -> None:
        script = self._script()

        class OpenAIIncompleteNewHandler(http.server.BaseHTTPRequestHandler):
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
                                            "action": "new",
                                            "target_ref": None,
                                            "proposed_args": {"title": "Incomplete follow-up"},
                                            "rationale": "The request still needs a bounded follow-up doc.",
                                            "confidence": 0.81,
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
            request = repo / "logics" / "request" / "req_000_hybrid_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_hybrid_seed - Hybrid seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Clarify the scope and user value of the seeded request.",
                    "",
                    "# Context",
                    "- Capture the relevant context and constraints for the seeded request.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: The next-step decision should stay bounded.",
                ],
            )

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAIIncompleteNewHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  next_step_auto_backend: openai",
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["backend_requested"], "auto")
            self.assertEqual(payload["backend_used"], "codex")
            self.assertEqual(payload["backend_status"]["selection_reason"], "provider-validation-fallback")
            self.assertIn("hybrid_invalid_next_step_decision", payload["degraded_reasons"])
            self.assertEqual(payload["result"]["decision"]["action"], "promote")

    def test_assist_run_next_step_configured_auto_backend_falls_back_to_codex(self) -> None:
        script = self._script()

        class OpenAINextStepUnavailableHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    encoded = json.dumps({"error": {"message": "quota exceeded"}}).encode("utf-8")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_hybrid_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_hybrid_seed - Hybrid seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Draft",
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAINextStepUnavailableHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("OPENAI_API_KEY=test-openai\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  next_step_auto_backend: openai",
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["backend_requested"], "auto")
            self.assertEqual(payload["backend_used"], "codex")
            self.assertEqual(payload["backend_status"]["selection_reason"], "config-auto-backend-fallback")
            self.assertEqual(payload["result_status"], "degraded")
            self.assertIn("next-step-auto-backend-openai-fallback", payload["degraded_reasons"])

    def test_assist_run_next_step_supports_gemini_backend_with_validated_response(self) -> None:
        script = self._script()

        class GeminiNextStepHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1beta/models/gemini-2.0-flash?key=test-gemini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps({"name": "models/gemini-2.0-flash"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1beta/models/gemini-2.0-flash:generateContent?key=test-gemini":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(
                                                {
                                                    "action": "promote",
                                                    "target_ref": "req_000_hybrid_seed",
                                                    "proposed_args": {},
                                                    "confidence": 0.86,
                                                    "rationale": "The request can move into backlog planning.",
                                                }
                                            )
                                        }
                                    ]
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GeminiNextStepHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text("GEMINI_API_KEY=test-gemini\n", encoding="utf-8")
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    gemini:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1beta",
                            "      model: gemini-2.0-flash",
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
                        "next-step",
                        "req_000_hybrid_seed",
                        "--backend",
                        "gemini",
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
            self.assertEqual(payload["backend_used"], "gemini")
            self.assertEqual(payload["result"]["decision"]["action"], "promote")
            self.assertEqual(payload["result"]["decision"]["target_ref"], "req_000_hybrid_seed")

    def test_assist_run_next_step_explicit_remote_invalid_payload_falls_back_to_codex(self) -> None:
        script = self._script()

        class OpenAIInvalidNextStepHandler(http.server.BaseHTTPRequestHandler):
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
                                            "action": "promote",
                                            "target_ref": "req_000_hybrid_seed",
                                            "confidence": 0.42,
                                            "rationale": "Missing proposed_args should trigger bounded fallback.",
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAIInvalidNextStepHandler)
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
                        "next-step",
                        "req_000_hybrid_seed",
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
            self.assertEqual(payload["backend_used"], "codex")
            self.assertEqual(payload["backend_status"]["selection_reason"], "provider-validation-fallback")
            self.assertIn("hybrid_missing_field", payload["degraded_reasons"])
            self.assertEqual(payload["result"]["decision"]["action"], "promote")
            self.assertEqual(payload["transport"]["transport"], "fallback")

