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
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
from logics_flow_test_base import LogicsFlowTestBase

class LogicsFlowTest(LogicsFlowTestBase):
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
            self.assertTrue((repo / ".env.local").is_file())
            self.assertIn("OPENAI_API_KEY=", (repo / ".env.local").read_text(encoding="utf-8"))
            self.assertIn("GEMINI_API_KEY=", (repo / ".env.local").read_text(encoding="utf-8"))

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

    def test_assist_runtime_status_does_not_degrade_when_claude_bridge_is_missing(self) -> None:
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
            self.assertFalse(payload["claude_bridge_available"])
            self.assertFalse(payload["degraded"])
            self.assertEqual(payload["degraded_reasons"], [])
            self.assertEqual(payload["claude_bridge"]["detected_variants"], [])

    def test_assist_runtime_status_accepts_hybrid_assist_claude_bridge_variant(self) -> None:
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
            (repo / ".claude" / "commands" / "logics-assist.md").write_text("bridge\n", encoding="utf-8")
            (repo / ".claude" / "agents" / "logics-hybrid-delivery-assistant.md").write_text("bridge\n", encoding="utf-8")

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
            self.assertTrue(payload["claude_bridge_available"])
            self.assertEqual(payload["claude_bridge"]["preferred_variant"], "hybrid-assist")
            self.assertIn("hybrid-assist", payload["claude_bridge"]["detected_variants"])

    def test_assist_runtime_status_exposes_per_flow_backend_policies(self) -> None:
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
            self.assertEqual(payload["flow_backend_policies"]["diff-risk"]["mode"], "ollama-first")
            self.assertEqual(payload["flow_backend_policies"]["next-step"]["mode"], "codex-only")
            self.assertEqual(payload["flow_backend_policies"]["next-step"]["auto_backend"], "codex")
            self.assertEqual(payload["flow_backend_policies"]["next-step"]["provider_order"], ["codex"])
            self.assertEqual(payload["flow_backend_policies"]["next-step"]["allowed_backends"], ["openai", "gemini", "codex"])
            self.assertEqual(payload["flow_backend_policies"]["changed-surface-summary"]["mode"], "deterministic")
            self.assertEqual(payload["flow_backend_policies"]["changed-surface-summary"]["auto_backend"], "deterministic")
            self.assertEqual(payload["flow_backend_policies"]["windows-compat-risk"]["mode"], "ollama-first")

    def test_build_flow_backend_policy_exposes_provider_order_and_allowed_backends(self) -> None:
        hybrid = self._hybrid_module()

        next_step_policy = hybrid.build_flow_backend_policy("next-step")
        self.assertEqual(next_step_policy["provider_order"], ["codex"])
        self.assertEqual(next_step_policy["allowed_backends"], ["openai", "gemini", "codex"])

        request_draft_policy = hybrid.build_flow_backend_policy("request-draft")
        self.assertEqual(request_draft_policy["provider_order"], ["ollama", "openai", "gemini", "codex"])
        self.assertEqual(request_draft_policy["allowed_backends"], ["ollama", "openai", "gemini", "codex"])

        spec_first_pass_policy = hybrid.build_flow_backend_policy("spec-first-pass")
        self.assertEqual(spec_first_pass_policy["provider_order"], ["ollama", "openai", "gemini", "codex"])
        self.assertEqual(spec_first_pass_policy["allowed_backends"], ["ollama", "openai", "gemini", "codex"])

        backlog_groom_policy = hybrid.build_flow_backend_policy("backlog-groom")
        self.assertEqual(backlog_groom_policy["provider_order"], ["ollama", "openai", "gemini", "codex"])
        self.assertEqual(backlog_groom_policy["allowed_backends"], ["ollama", "openai", "gemini", "codex"])

        commit_message_policy = hybrid.build_flow_backend_policy("commit-message")
        self.assertEqual(commit_message_policy["provider_order"], ["ollama", "openai", "gemini", "codex"])
        self.assertEqual(commit_message_policy["allowed_backends"], ["ollama", "openai", "gemini", "codex"])

        deterministic_policy = hybrid.build_flow_backend_policy("changed-surface-summary")
        self.assertEqual(deterministic_policy["provider_order"], ["deterministic"])
        self.assertEqual(deterministic_policy["allowed_backends"], ["deterministic"])

    def test_select_hybrid_backend_rejects_explicit_backend_outside_flow_policy(self) -> None:
        hybrid = self._hybrid_module()

        with self.assertRaises(hybrid.HybridAssistError) as context:
            hybrid.select_hybrid_backend(
                requested_backend="ollama",
                flow_name="next-step",
                host="127.0.0.1:11434",
                model="deepseek-coder-v2:16b",
            )

        self.assertEqual(context.exception.code, "hybrid_backend_policy_violation")

    def test_build_hybrid_result_cache_key_ignores_noisy_lockfile_paths(self) -> None:
        core = self._core_module()

        model_selection = {
            "name": "deepseek-coder",
            "resolved_model": "deepseek-coder-v2:16b",
        }
        clean_context_bundle = {
            "seed_ref": "req_001_seed",
            "context_profile": {"mode": "diff-first", "profile": "tiny"},
            "git_snapshot": {
                "changed_paths": ["src/feature.ts"],
                "unstaged_diff_stat": [" src/feature.ts | 1 +"],
                "staged_diff_stat": [],
            },
            "context_pack": {"mode": "diff-first", "profile": "tiny"},
        }
        noisy_context_bundle = {
            "seed_ref": "req_001_seed",
            "context_profile": {"mode": "diff-first", "profile": "tiny"},
            "git_snapshot": {
                "changed_paths": ["src/feature.ts", "package-lock.json"],
                "unstaged_diff_stat": [" src/feature.ts | 1 +", " package-lock.json | 3 ++-"],
                "staged_diff_stat": [" package-lock.json | Bin 0 -> 0 bytes"],
            },
            "context_pack": {"mode": "diff-first", "profile": "tiny"},
        }

        clean_key, clean_fingerprint = core._build_hybrid_result_cache_key(
            flow_name="commit-message",
            requested_backend="auto",
            model_selection=model_selection,
            context_bundle=clean_context_bundle,
        )
        noisy_key, noisy_fingerprint = core._build_hybrid_result_cache_key(
            flow_name="commit-message",
            requested_backend="auto",
            model_selection=model_selection,
            context_bundle=noisy_context_bundle,
        )

        self.assertEqual(noisy_key, clean_key)
        self.assertEqual(noisy_fingerprint, clean_fingerprint)

    def test_build_context_pack_reuses_cached_pack_between_calls(self) -> None:
        core = self._core_module()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True)
            (repo / "logics.yaml").write_text("version: 1\n", encoding="utf-8")
            request = repo / "logics" / "request" / "req_001_seed.md"
            self._write_doc(
                request,
                [
                    "## req_001_seed - Seed request",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "### Needs",
                    "- Keep the pack stable",
                ],
            )

            core._CONTEXT_PACK_CACHE.clear()
            with mock.patch.object(core, "_context_pack_doc_entry", wraps=core._context_pack_doc_entry) as wrapped_entry:
                first = core._build_context_pack(
                    repo,
                    "req_001_seed",
                    mode="summary-only",
                    profile="tiny",
                    config={"version": 1},
                )
                second = core._build_context_pack(
                    repo,
                    "req_001_seed",
                    mode="summary-only",
                    profile="tiny",
                    config={"version": 1},
                )

            self.assertEqual(first, second)
            self.assertEqual(wrapped_entry.call_count, 1)
