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
    def test_assist_runtime_status_reports_remote_provider_availability_from_config_and_dotenv(self) -> None:
        script = self._script()

        class RemoteProviderStatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/v1/models/gpt-4.1-mini":
                    payload = {"id": "gpt-4.1-mini"}
                elif self.path == "/v1beta/models/gemini-2.0-flash?key=test-gemini":
                    payload = {"name": "models/gemini-2.0-flash"}
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RemoteProviderStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text(
                    "OPENAI_API_KEY=test-openai\nGEMINI_API_KEY=test-gemini\n",
                    encoding="utf-8",
                )
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
                        "runtime-status",
                        "--backend",
                        "auto",
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
            self.assertEqual(payload["backend"]["selected_backend"], "openai")
            self.assertTrue(payload["providers"]["openai"]["healthy"])
            self.assertTrue(payload["providers"]["openai"]["credential_present"])
            self.assertTrue(payload["providers"]["gemini"]["healthy"])
            self.assertTrue(payload["providers"]["gemini"]["credential_present"])

    def test_assist_runtime_status_reads_provider_credentials_from_env_local_fallback(self) -> None:
        script = self._script()

        class RemoteProviderStatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/v1/models/gpt-4.1-mini":
                    payload = {"id": "gpt-4.1-mini"}
                elif self.path == "/v1beta/models/gemini-2.0-flash?key=test-gemini":
                    payload = {"name": "models/gemini-2.0-flash"}
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RemoteProviderStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env.local").write_text(
                    "OPENAI_API_KEY=test-openai\nGEMINI_API_KEY=test-gemini\n",
                    encoding="utf-8",
                )
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
                        "runtime-status",
                        "--backend",
                        "auto",
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
            self.assertEqual(payload["backend"]["selected_backend"], "openai")
            self.assertTrue(payload["providers"]["openai"]["credential_present"])
            self.assertTrue(payload["providers"]["gemini"]["credential_present"])

    def test_assist_runtime_status_keeps_env_credentials_when_env_local_placeholders_are_blank(self) -> None:
        script = self._script()

        class RemoteProviderStatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/v1/models/gpt-4.1-mini":
                    payload = {"id": "gpt-4.1-mini"}
                elif self.path == "/v1beta/models/gemini-2.0-flash?key=test-gemini":
                    payload = {"name": "models/gemini-2.0-flash"}
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RemoteProviderStatusHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text(
                    "OPENAI_API_KEY=test-openai\nGEMINI_API_KEY=test-gemini\n",
                    encoding="utf-8",
                )
                (repo / ".env.local").write_text(
                    "OPENAI_API_KEY=\nGEMINI_API_KEY=\n",
                    encoding="utf-8",
                )
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
                        "runtime-status",
                        "--backend",
                        "auto",
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
            self.assertEqual(payload["backend"]["selected_backend"], "openai")
            self.assertTrue(payload["providers"]["openai"]["credential_present"])
            self.assertTrue(payload["providers"]["gemini"]["credential_present"])

    def test_assist_run_commit_message_supports_openai_backend_with_dotenv_credentials(self) -> None:
        script = self._script()

        class OpenAICommitMessageHandler(http.server.BaseHTTPRequestHandler):
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
                                            "subject": "Route bounded summaries through OpenAI",
                                            "body": "Use the remote provider path while keeping the shared contract validation in place.",
                                            "scope": "root",
                                            "confidence": 0.88,
                                            "rationale": "The runtime now supports an explicit OpenAI transport.",
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

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OpenAICommitMessageHandler)
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
                        "run",
                        "commit-message",
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
            self.assertEqual(payload["result"]["subject"], "Route bounded summaries through OpenAI")

    def test_assist_run_commit_message_supports_gemini_backend_with_dotenv_credentials(self) -> None:
        script = self._script()

        class GeminiCommitMessageHandler(http.server.BaseHTTPRequestHandler):
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
                                                    "subject": "Add Gemini bounded transport support",
                                                    "body": "Support generateContent while preserving the shared contract validator.",
                                                    "scope": "root",
                                                    "confidence": 0.84,
                                                    "rationale": "Gemini can now satisfy the same bounded hybrid assist contract.",
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
            (repo / "logics").mkdir(parents=True)

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GeminiCommitMessageHandler)
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
                        "run",
                        "commit-message",
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
            self.assertEqual(payload["result"]["subject"], "Add Gemini bounded transport support")

    def test_assist_run_openai_reports_missing_credentials_clearly(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "hybrid_assist:",
                        "  providers:",
                        "    openai:",
                        "      enabled: true",
                        "      base_url: https://api.openai.invalid/v1",
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
                    "run",
                    "commit-message",
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

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "hybrid_provider_unavailable")
            self.assertIn("openai-missing-credentials", payload["details"]["reasons"])

    def test_assist_run_auto_skips_remote_provider_during_cooldown_after_failed_probe(self) -> None:
        script = self._script()

        class CoolingOpenAIHandler(http.server.BaseHTTPRequestHandler):
            probe_count = 0

            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/models/gpt-4.1-mini":
                    self.send_response(404)
                    self.end_headers()
                    return
                CoolingOpenAIHandler.probe_count += 1
                encoded = json.dumps({"error": "temporarily unavailable"}).encode("utf-8")
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CoolingOpenAIHandler)
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
                            "    readiness_cooldown_seconds: 300",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/v1",
                            "      model: gpt-4.1-mini",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                first = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "commit-message",
                        "--backend",
                        "auto",
                        "--format",
                        "json",
                    ],
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                second = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "commit-message",
                        "--backend",
                        "auto",
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

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)
            self.assertIn("openai-http-503", first_payload["degraded_reasons"])
            self.assertIn("openai-cooldown-active", second_payload["degraded_reasons"])
            self.assertEqual(CoolingOpenAIHandler.probe_count, 1)
            self.assertTrue((repo / "logics" / ".cache" / "provider_health.json").is_file())

    def test_assist_run_commit_message_auto_falls_through_openai_to_gemini(self) -> None:
        script = self._script()

        class OrderedRemoteFallbackHandler(http.server.BaseHTTPRequestHandler):
            openai_probe_count = 0
            gemini_probe_count = 0
            gemini_generate_count = 0

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/openai/v1/models/gpt-4.1-mini":
                    OrderedRemoteFallbackHandler.openai_probe_count += 1
                    encoded = json.dumps({"error": "temporarily unavailable"}).encode("utf-8")
                    self.send_response(503)
                elif self.path == "/gemini/v1beta/models/gemini-2.0-flash?key=test-gemini":
                    OrderedRemoteFallbackHandler.gemini_probe_count += 1
                    encoded = json.dumps({"name": "models/gemini-2.0-flash"}).encode("utf-8")
                    self.send_response(200)
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/gemini/v1beta/models/gemini-2.0-flash:generateContent?key=test-gemini":
                    self.send_response(404)
                    self.end_headers()
                    return
                OrderedRemoteFallbackHandler.gemini_generate_count += 1
                encoded = json.dumps(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(
                                                {
                                                    "subject": "Route fallback from OpenAI to Gemini",
                                                    "body": "Keep ordered remote fallback bounded and provider-aware.",
                                                    "scope": "root",
                                                    "confidence": 0.81,
                                                    "rationale": "Gemini should satisfy the same contract when OpenAI is temporarily unavailable.",
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
            (repo / "logics").mkdir(parents=True)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OrderedRemoteFallbackHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                (repo / ".env").write_text(
                    "OPENAI_API_KEY=test-openai\nGEMINI_API_KEY=test-gemini\n",
                    encoding="utf-8",
                )
                (repo / "logics.yaml").write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "hybrid_assist:",
                            "  providers:",
                            "    ollama:",
                            "      enabled: false",
                            "    openai:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/openai/v1",
                            "      model: gpt-4.1-mini",
                            "    gemini:",
                            "      enabled: true",
                            f"      base_url: http://127.0.0.1:{server.server_port}/gemini/v1beta",
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
                        "run",
                        "commit-message",
                        "--backend",
                        "auto",
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
            self.assertEqual(payload["result"]["subject"], "Route fallback from OpenAI to Gemini")
            self.assertEqual(payload["degraded_reasons"], [])
            self.assertEqual(OrderedRemoteFallbackHandler.openai_probe_count, 1)
            self.assertEqual(OrderedRemoteFallbackHandler.gemini_probe_count, 1)
            self.assertEqual(OrderedRemoteFallbackHandler.gemini_generate_count, 1)

    def test_assist_run_commit_message_falls_back_after_invalid_openai_payload(self) -> None:
        script = self._script()

        class InvalidOpenAIContractHandler(http.server.BaseHTTPRequestHandler):
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
                                            "subject": "Remote payload misses required keys",
                                            "body": "The shared validator should reject this and fall back safely.",
                                            "confidence": 0.41,
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
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), InvalidOpenAIContractHandler)
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
                            "    ollama:",
                            "      enabled: false",
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
                        "run",
                        "commit-message",
                        "--backend",
                        "auto",
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
            self.assertEqual(payload["result_status"], "degraded")
            self.assertIn("hybrid_missing_field", payload["degraded_reasons"])
            self.assertIsInstance(payload["raw_result"], dict)
            self.assertEqual(payload["raw_result"]["subject"], "Remote payload misses required keys")
            self.assertEqual(payload["transport"]["diagnostic"]["error_code"], "hybrid_missing_field")
            self.assertEqual(payload["transport"]["upstream_transport"], "openai")

    def test_assist_run_changed_surface_summary_uses_deterministic_backend(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / "README.md").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Tests"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (repo / "README.md").write_text("seed\nchanged\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "changed-surface-summary",
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
            self.assertEqual(payload["backend_used"], "deterministic")
            self.assertEqual(payload["transport"]["transport"], "deterministic")
            self.assertIn("README.md", payload["result"]["changed_paths"])
            self.assertTrue(payload["result"]["categories"])
