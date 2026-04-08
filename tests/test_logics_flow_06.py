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
    def test_assist_run_release_changelog_status_resolves_curated_file_deterministically(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / "changelogs").mkdir(parents=True)
            (repo / "package.json").write_text(
                json.dumps({"name": "demo", "version": "1.2.3"}),
                encoding="utf-8",
            )
            (repo / "changelogs" / "CHANGELOGS_1_2_3.md").write_text("# Demo\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "release-changelog-status",
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
            self.assertTrue(payload["result"]["exists"])
            self.assertEqual(payload["result"]["tag"], "v1.2.3")
            self.assertEqual(payload["result"]["relative_path"], "changelogs/CHANGELOGS_1_2_3.md")

    def test_assist_run_commit_message_uses_hardened_prompt_and_stays_on_ollama_for_valid_payload(self) -> None:
        script = self._script()

        class OllamaCommitMessageHandler(http.server.BaseHTTPRequestHandler):
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

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                request_payload = json.loads(self.rfile.read(length).decode("utf-8"))
                content = json.dumps(
                    {
                        "subject": "Align hybrid runtime diagnostics",
                        "body": "Preserve bounded local failure details and keep the prompt instance-oriented.",
                        "scope": "root",
                        "confidence": 0.86,
                        "rationale": "The diff centers on shared hybrid runtime behavior.",
                    }
                )
                response_payload = {
                    "message": {"role": "assistant", "content": content},
                    "request_echo": request_payload,
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
            (repo / "logics").mkdir(parents=True)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaCommitMessageHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "commit-message",
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
            self.assertEqual(payload["backend_used"], "ollama")
            self.assertEqual(payload["result_status"], "ok")
            self.assertEqual(payload["result"]["subject"], "Align hybrid runtime diagnostics")
            messages = payload["transport"]["messages"]
            self.assertIn("The contract block below describes the required answer shape. It is not the answer itself.", messages[1]["content"])
            self.assertIn("Do not echo the contract or copy metadata field names into the answer.", messages[1]["content"])
            self.assertIn("Return exactly one JSON object with only these top-level keys: subject, body, scope, confidence, rationale.", messages[1]["content"])

    def test_assist_run_commit_message_normalizes_textual_confidence_without_fallback(self) -> None:
        script = self._script()

        class OllamaCommitMessageTextConfidenceHandler(http.server.BaseHTTPRequestHandler):
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

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                content = json.dumps(
                    {
                        "subject": "Normalize local confidence values",
                        "body": "Accept common textual confidence labels without falling back unnecessarily.",
                        "scope": "root",
                        "confidence": "medium",
                        "rationale": "The local model can still satisfy the contract semantically even when confidence is phrased textually.",
                    }
                )
                encoded = json.dumps({"message": {"role": "assistant", "content": content}}).encode("utf-8")
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
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaCommitMessageTextConfidenceHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "commit-message",
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
            self.assertEqual(payload["backend_used"], "ollama")
            self.assertEqual(payload["result_status"], "ok")
            self.assertEqual(payload["result"]["subject"], "Normalize local confidence values")
            self.assertEqual(payload["result"]["confidence"], 0.65)
            self.assertEqual(payload["degraded_reasons"], [])

    def test_assist_run_commit_message_preserves_invalid_local_payload_diagnostics_on_fallback(self) -> None:
        script = self._script()

        class OllamaEchoContractHandler(http.server.BaseHTTPRequestHandler):
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

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                content = json.dumps(
                    {
                        "flow": "commit-message",
                        "summary": "Generate a bounded commit message proposal from the current git diff.",
                        "required_keys": ["subject", "body", "scope", "confidence", "rationale"],
                        "scope_enum": ["single", "root", "submodule"],
                    }
                )
                encoded = json.dumps({"message": {"role": "assistant", "content": content}}).encode("utf-8")
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
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaEchoContractHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "commit-message",
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
            self.assertEqual(payload["result_status"], "degraded")
            self.assertIn("hybrid_missing_field", payload["degraded_reasons"])
            self.assertIsInstance(payload["raw_result"], dict)
            self.assertEqual(payload["raw_result"]["flow"], "commit-message")
            self.assertIn("required_keys", payload["raw_result"])
            self.assertEqual(payload["transport"]["diagnostic"]["error_code"], "hybrid_missing_field")
            self.assertEqual(payload["transport"]["upstream_transport"], "ollama")

    def test_validate_hybrid_result_rejects_generic_commit_subject(self) -> None:
        hybrid = self._hybrid_module()

        with self.assertRaises(hybrid.HybridAssistError) as context:
            hybrid.validate_hybrid_result(
                "commit-message",
                {
                    "subject": "Update plugin hybrid assist surfaces",
                    "body": "Changes touch `src/logicsWebviewHtml.ts`.",
                    "scope": "root",
                    "confidence": 0.72,
                    "rationale": "Generic fallback",
                },
                {},
                context_bundle={
                    "git_snapshot": {
                        "changed_paths": [
                            "src/logicsWebviewHtml.ts",
                            "media/toolsPanelLayout.js",
                            "tests/webview.harness-core.test.ts",
                        ]
                    }
                },
            )

        self.assertEqual(context.exception.code, "hybrid_generic_subject")

    def test_build_fallback_result_prefers_specific_tools_panel_subject(self) -> None:
        hybrid = self._hybrid_module()

        result = hybrid.build_fallback_result(
            "commit-message",
            context_bundle={
                "repo_root": ".",
                "git_snapshot": {
                    "changed_paths": [
                        "media/css/toolbar.css",
                        "media/toolsPanelLayout.js",
                        "src/logicsWebviewHtml.ts",
                        "tests/webview.harness-core.test.ts",
                    ],
                    "touches_plugin": True,
                    "touches_runtime": False,
                    "touches_tests": True,
                    "doc_only": False,
                },
            },
            docs_by_ref={},
        )

        self.assertEqual(result["subject"], "Refine tools panel navigation and test coverage")

    def test_assist_run_commit_message_distinguishes_transport_unavailability_from_semantic_failure(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "run",
                    "commit-message",
                    "--backend",
                    "auto",
                    "--model",
                    "deepseek-coder-v2:16b",
                    "--ollama-host",
                    "http://127.0.0.1:9",
                    "--timeout",
                    "0.2",
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
            self.assertEqual(payload["result_status"], "degraded")
            self.assertIn("ollama-unreachable", payload["degraded_reasons"])
            self.assertIsNone(payload["raw_result"])

    def test_assist_roi_report_aggregates_measured_derived_and_estimated_sections(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            logics_dir = repo / "logics"
            logics_dir.mkdir(parents=True)
            cache_dir = logics_dir / ".cache"
            cache_dir.mkdir(parents=True)
            audit_log = cache_dir / "hybrid_assist_audit.jsonl"
            measurement_log = cache_dir / "hybrid_assist_measurements.jsonl"

            measurement_records = [
                {
                    "recorded_at": "2026-03-20T10:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "summarize-validation",
                    "backend_requested": "auto",
                    "backend_used": "ollama",
                    "result_status": "ok",
                    "confidence": 0.91,
                    "degraded_reasons": [],
                    "review_recommended": False,
                },
                {
                    "recorded_at": "2026-03-21T11:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "next-step",
                    "backend_requested": "auto",
                    "backend_used": "codex",
                    "result_status": "degraded",
                    "confidence": 0.62,
                    "degraded_reasons": ["ollama-unreachable"],
                    "review_recommended": True,
                },
                {
                    "recorded_at": "2026-03-22T12:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "triage",
                    "backend_requested": "codex",
                    "backend_used": "ollama",
                    "result_status": "ok",
                    "confidence": 0.74,
                    "degraded_reasons": [],
                    "review_recommended": False,
                },
            ]
            audit_records = [
                {
                    "recorded_at": "2026-03-20T10:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "summarize-validation",
                    "result_status": "ok",
                    "backend": {
                        "requested_backend": "auto",
                        "selected_backend": "ollama",
                        "reasons": [],
                    },
                    "safety_class": "proposal-only",
                    "context_summary": {"seed_ref": None},
                    "validated_payload": {"overall": "pass", "summary": "Validation surfaces are green.", "confidence": 0.91},
                    "transport": {"transport": "ollama", "selected_backend": "ollama"},
                    "degraded_reasons": [],
                    "execution_result": None,
                },
                {
                    "recorded_at": "2026-03-21T11:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "next-step",
                    "result_status": "degraded",
                    "backend": {
                        "requested_backend": "auto",
                        "selected_backend": "codex",
                        "reasons": ["ollama-unreachable"],
                    },
                    "safety_class": "deterministic-runner",
                    "context_summary": {"seed_ref": "req_000_seed"},
                    "validated_payload": {
                        "decision": {"action": "promote", "target_ref": "req_000_seed", "confidence": 0.62}
                    },
                    "transport": {"transport": "fallback", "reason": "ollama-unreachable", "selected_backend": "codex"},
                    "degraded_reasons": ["ollama-unreachable"],
                    "execution_result": None,
                },
                {
                    "recorded_at": "2026-03-22T12:00:00+00:00",
                    "schema_version": "1.0",
                    "flow": "triage",
                    "result_status": "ok",
                    "backend": {
                        "requested_backend": "codex",
                        "selected_backend": "ollama",
                        "reasons": [],
                    },
                    "safety_class": "proposal-only",
                    "context_summary": {"seed_ref": "req_001_seed"},
                    "validated_payload": {
                        "target_ref": "req_001_seed",
                        "classification": "ready",
                        "summary": "The request is ready for backlog promotion.",
                        "confidence": 0.74,
                    },
                    "transport": {"transport": "ollama", "selected_backend": "ollama"},
                    "degraded_reasons": [],
                    "execution_result": None,
                },
            ]

            audit_log.write_text("\n".join(json.dumps(record) for record in audit_records) + "\n", encoding="utf-8")
            measurement_log.write_text("\n".join(json.dumps(record) for record in measurement_records) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "roi-report",
                    "--recent-limit",
                    "2",
                    "--window-days",
                    "30",
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
            self.assertEqual(payload["assist_kind"], "roi-report")
            self.assertEqual(payload["report_kind"], "hybrid-assist-roi-report")
            self.assertEqual(payload["measured"]["totals"]["runs"], 3)
            self.assertEqual(payload["measured"]["totals"]["fallback_runs"], 1)
            self.assertEqual(payload["measured"]["totals"]["degraded_runs"], 1)
            self.assertEqual(payload["measured"]["totals"]["review_recommended_runs"], 1)
            self.assertEqual(payload["measured"]["totals"]["local_runs"], 2)
            self.assertEqual(payload["measured"]["runs_by_flow"]["next-step"], 1)
            self.assertEqual(payload["derived"]["rates"]["fallback_rate"], 0.3333)
            self.assertEqual(payload["derived"]["rates"]["local_offload_rate"], 0.6667)
            self.assertEqual(payload["estimated"]["proxies"]["estimated_remote_dispatches_avoided"], 2)
            self.assertEqual(payload["estimated"]["proxies"]["estimated_remote_token_avoidance"], 2400)
            self.assertEqual(len(payload["recent_runs"]), 2)
            self.assertEqual(payload["recent_runs"][-1]["flow"], "triage")
            self.assertEqual(payload["recent_runs"][0]["backend_used"], "codex")
            self.assertTrue(payload["derived"]["top_fallback_reasons"])

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
            self.assertTrue((repo / "logics" / ".cache" / "hybrid_assist_audit.jsonl").is_file())
            self.assertTrue((repo / "logics" / ".cache" / "hybrid_assist_measurements.jsonl").is_file())

    def test_assist_run_diff_risk_prefers_ollama_when_policy_allows_it(self) -> None:
        script = self._script()

        class OllamaDiffRiskHandler(http.server.BaseHTTPRequestHandler):
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

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "risk": "medium",
                                    "summary": "Runtime and plugin surfaces both changed in this diff.",
                                    "drivers": ["Diff spans shared runtime and extension files."],
                                    "confidence": 0.83,
                                    "rationale": "The shared contract still keeps the risk report bounded and reviewable.",
                                }
                            ),
                        }
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
            changed = repo / "README.md"
            changed.parent.mkdir(parents=True, exist_ok=True)
            changed.write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "add", "README.md"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            changed.write_text("demo\nchange\n", encoding="utf-8")

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaDiffRiskHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "assist",
                        "run",
                        "diff-risk",
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
            self.assertEqual(payload["backend_used"], "ollama")
            self.assertEqual(payload["backend_status"]["policy_mode"], "ollama-first")
            self.assertEqual(payload["backend_status"]["selection_reason"], "auto-healthy-ollama")
            self.assertEqual(payload["result"]["risk"], "medium")
