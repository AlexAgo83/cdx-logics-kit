from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.pop(0)
    return module


class MermaidGeneratorTest(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-mermaid-generator" / "scripts" / "generate_mermaid.py"

    def test_standalone_script_renders_request_block(self) -> None:
        payload = {
            "NEEDS_PLACEHOLDER": "- Reduce operator work",
            "CONTEXT_PLACEHOLDER": "- Shared runtime already exists",
            "ACCEPTANCE_PLACEHOLDER": "- AC1: Generate a valid Mermaid block",
        }
        completed = subprocess.run(
            [
                sys.executable,
                str(self._script()),
                "--kind",
                "request",
                "--title",
                "Demo request",
                "--backend",
                "codex",
                "--values-json",
                json.dumps(payload),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn("```mermaid", completed.stdout)
        self.assertIn("%% logics-kind: request", completed.stdout)
        self.assertIn("flowchart TD", completed.stdout)

    def test_flow_support_reexports_mermaid_generator_renderer(self) -> None:
        generator_module = _load_module("mermaid_generator_test", self._script())
        flow_support_path = Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_flow_support.py"
        flow_support_module = _load_module("flow_support_mermaid_test", flow_support_path)

        values = {
            "PROBLEM_PLACEHOLDER": "- Operators need a reusable diagram generator",
            "REQUEST_LINK_PLACEHOLDER": "`req_128_demo_request`",
            "ACCEPTANCE_BLOCK": "- AC1: Diagram stays deterministic",
            "TASK_LINK_PLACEHOLDER": "`task_236_demo_delivery`",
        }
        expected = generator_module._render_workflow_mermaid("backlog", "Demo backlog", values)
        actual = flow_support_module._render_workflow_mermaid("backlog", "Demo backlog", values)
        self.assertEqual(actual, expected)

    def test_hybrid_generation_records_measurement_when_provider_payload_is_valid(self) -> None:
        module = _load_module("mermaid_generator_hybrid_ok", self._script())
        repo = Path(tempfile.mkdtemp(prefix="mermaid-hybrid-"))
        self.addCleanup(lambda: shutil.rmtree(repo, ignore_errors=True))
        (repo / "logics" / ".cache").mkdir(parents=True, exist_ok=True)
        valid_block = module._render_workflow_mermaid(
            "request",
            "Hybrid request",
            {
                "NEEDS_PLACEHOLDER": "- Hybrid generation",
                "CONTEXT_PLACEHOLDER": "- Provider healthy",
                "ACCEPTANCE_PLACEHOLDER": "- AC1: Return a valid Mermaid block",
            },
        )

        backend_status = mock.Mock(
            selected_backend="ollama",
            requested_backend="auto",
            host="http://127.0.0.1:11434",
            model_profile="deepseek-coder",
            model_family="deepseek",
            configured_model="deepseek-coder-v2:16b",
            model="deepseek-coder-v2:16b",
            healthy=True,
            reasons=[],
            to_dict=mock.Mock(return_value={"requested_backend": "auto", "selected_backend": "ollama", "healthy": True, "reasons": []}),
        )

        with mock.patch.object(module, "probe_ollama_backend", return_value=backend_status), \
            mock.patch.object(module, "build_hybrid_provider_registry", return_value={}), \
            mock.patch.object(
                module,
                "run_ollama_hybrid",
                return_value={
                    "result_payload": {"mermaid": valid_block, "confidence": 0.84, "rationale": "Provider payload valid."},
                    "raw_content": valid_block,
                    "response_payload": {},
                    "transport": "ollama",
                },
            ):
            payload = module.generate_mermaid(
                repo_root=repo,
                kind_name="request",
                title="Hybrid request",
                values={
                    "NEEDS_PLACEHOLDER": "- Hybrid generation",
                    "CONTEXT_PLACEHOLDER": "- Provider healthy",
                    "ACCEPTANCE_PLACEHOLDER": "- AC1: Return a valid Mermaid block",
                },
            )

        self.assertEqual(payload["backend_used"], "ollama")
        self.assertEqual(payload["result_status"], "ok")
        self.assertEqual(payload["mermaid"], valid_block)
        measurement_log = Path(payload["measurement_log"])
        self.assertTrue(measurement_log.is_file())
        self.assertIn("mermaid-generator", measurement_log.read_text(encoding="utf-8"))

    def test_unicode_mermaid_label_is_rejected_and_falls_back_silently(self) -> None:
        module = _load_module("mermaid_generator_hybrid_reject", self._script())
        repo = Path(tempfile.mkdtemp(prefix="mermaid-hybrid-"))
        self.addCleanup(lambda: shutil.rmtree(repo, ignore_errors=True))
        (repo / "logics" / ".cache").mkdir(parents=True, exist_ok=True)
        expected_fallback = module._render_workflow_mermaid(
            "request",
            "Rejected request",
            {
                "NEEDS_PLACEHOLDER": "- Fallback still valid",
                "CONTEXT_PLACEHOLDER": "- Safety validator active",
                "ACCEPTANCE_PLACEHOLDER": "- AC1: Reject unsafe Mermaid",
            },
        )

        backend_status = mock.Mock(
            selected_backend="ollama",
            requested_backend="auto",
            host="http://127.0.0.1:11434",
            model_profile="deepseek-coder",
            model_family="deepseek",
            configured_model="deepseek-coder-v2:16b",
            model="deepseek-coder-v2:16b",
            healthy=True,
            reasons=[],
            to_dict=mock.Mock(return_value={"requested_backend": "auto", "selected_backend": "ollama", "healthy": True, "reasons": []}),
        )
        unsafe_block = "\n".join(
            [
                "```mermaid",
                "%% logics-kind: request",
                "%% logics-signature: request|unsafe",
                "flowchart TD",
                "    Trigger[Demande élargie] --> Need[Unsafe label]",
                "```",
            ]
        )

        with mock.patch.object(module, "probe_ollama_backend", return_value=backend_status), \
            mock.patch.object(module, "build_hybrid_provider_registry", return_value={}), \
            mock.patch.object(
                module,
                "run_ollama_hybrid",
                return_value={
                    "result_payload": {"mermaid": unsafe_block, "confidence": 0.81, "rationale": "Unsafe payload."},
                    "raw_content": unsafe_block,
                    "response_payload": {},
                    "transport": "ollama",
                },
            ):
            payload = module.generate_mermaid(
                repo_root=repo,
                kind_name="request",
                title="Rejected request",
                values={
                    "NEEDS_PLACEHOLDER": "- Fallback still valid",
                    "CONTEXT_PLACEHOLDER": "- Safety validator active",
                    "ACCEPTANCE_PLACEHOLDER": "- AC1: Reject unsafe Mermaid",
                },
            )

        self.assertEqual(payload["result_status"], "degraded")
        self.assertIn("mermaid-non-ascii-label", payload["degraded_reasons"])
        self.assertEqual(payload["mermaid"], expected_fallback)
        audit_log = Path(payload["audit_log"])
        self.assertTrue(audit_log.is_file())
        self.assertIn("mermaid-non-ascii-label", audit_log.read_text(encoding="utf-8"))

    def test_auto_backend_uses_remote_provider_when_repo_config_enables_it(self) -> None:
        module = _load_module("mermaid_generator_remote_auto", self._script())
        repo = Path(tempfile.mkdtemp(prefix="mermaid-hybrid-"))
        self.addCleanup(lambda: shutil.rmtree(repo, ignore_errors=True))
        (repo / "logics" / ".cache").mkdir(parents=True, exist_ok=True)

        unhealthy_ollama = mock.Mock(
            selected_backend="codex",
            requested_backend="auto",
            host="http://127.0.0.1:11434",
            model_profile="deepseek-coder",
            model_family="deepseek",
            configured_model="deepseek-coder-v2:16b",
            model="deepseek-coder-v2:16b",
            healthy=False,
            reasons=["ollama-unreachable"],
            to_dict=mock.Mock(
                return_value={"requested_backend": "auto", "selected_backend": "codex", "healthy": False, "reasons": ["ollama-unreachable"]}
            ),
        )
        healthy_openai = mock.Mock(
            selected_backend="openai",
            requested_backend="auto",
            host="https://api.openai.com/v1",
            model_profile="openai",
            model_family="openai",
            configured_model="gpt-4.1-mini",
            model="gpt-4.1-mini",
            healthy=True,
            reasons=[],
            to_dict=mock.Mock(return_value={"requested_backend": "auto", "selected_backend": "openai", "healthy": True, "reasons": []}),
        )
        valid_block = module._render_workflow_mermaid(
            "request",
            "Remote provider request",
            {
                "NEEDS_PLACEHOLDER": "- Remote provider path",
                "CONTEXT_PLACEHOLDER": "- Ollama unavailable",
                "ACCEPTANCE_PLACEHOLDER": "- AC1: Use OpenAI fallback",
            },
        )

        def fake_provider_registry(**kwargs):
            self.assertIsInstance(kwargs.get("config"), dict)
            openai_provider = mock.Mock()
            openai_provider.name = "openai"
            openai_provider.enabled = True
            openai_provider.credential_present = True
            openai_provider.credential_value = "test-key"
            openai_provider.endpoint = "https://api.openai.com/v1"
            openai_provider.model_profile = "openai"
            openai_provider.model_family = "openai"
            openai_provider.configured_model = "gpt-4.1-mini"
            openai_provider.model = "gpt-4.1-mini"
            return {"openai": openai_provider}

        with mock.patch.object(
            module,
            "load_repo_config",
            return_value=(
                {
                    "hybrid_assist": {
                        "providers": {
                            "openai": {
                                "enabled": True,
                                "base_url": "https://api.openai.com/v1",
                                "model": "gpt-4.1-mini",
                            }
                        }
                    }
                },
                repo / "logics.yaml",
            ),
        ), mock.patch.object(module, "probe_ollama_backend", return_value=unhealthy_ollama), mock.patch.object(
            module,
            "build_hybrid_provider_registry",
            side_effect=fake_provider_registry,
        ), mock.patch.object(module, "probe_remote_provider", return_value=healthy_openai), mock.patch.object(
            module,
            "run_openai_hybrid",
            return_value={
                "result_payload": {"mermaid": valid_block, "confidence": 0.88, "rationale": "Remote provider valid."},
                "raw_content": valid_block,
                "response_payload": {},
                "transport": "openai",
            },
        ):
            payload = module.generate_mermaid(
                repo_root=repo,
                kind_name="request",
                title="Remote provider request",
                values={
                    "NEEDS_PLACEHOLDER": "- Remote provider path",
                    "CONTEXT_PLACEHOLDER": "- Ollama unavailable",
                    "ACCEPTANCE_PLACEHOLDER": "- AC1: Use OpenAI fallback",
                },
            )

        self.assertEqual(payload["backend_requested"], "auto")
        self.assertEqual(payload["backend_used"], "openai")
        self.assertEqual(payload["result_status"], "ok")
        self.assertEqual(payload["mermaid"], valid_block)

    def test_raw_flowchart_response_is_normalized_into_managed_mermaid_block(self) -> None:
        module = _load_module("mermaid_generator_remote_normalize", self._script())
        repo = Path(tempfile.mkdtemp(prefix="mermaid-hybrid-"))
        self.addCleanup(lambda: shutil.rmtree(repo, ignore_errors=True))
        (repo / "logics" / ".cache").mkdir(parents=True, exist_ok=True)

        backend_status = mock.Mock(
            selected_backend="openai",
            requested_backend="auto",
            host="https://api.openai.com/v1",
            model_profile="openai",
            model_family="openai",
            configured_model="gpt-4.1-mini",
            model="gpt-4.1-mini",
            healthy=True,
            reasons=[],
            to_dict=mock.Mock(return_value={"requested_backend": "auto", "selected_backend": "openai", "healthy": True, "reasons": []}),
        )
        raw_flowchart = "\n".join(
            [
                "flowchart TD",
                "    Trigger[Normalized request] --> Need[Remote path]",
                "    Need --> Outcome[Acceptance target]",
                "    Outcome --> Backlog[Backlog slice]",
            ]
        )

        with mock.patch.object(module, "probe_ollama_backend", return_value=backend_status), \
            mock.patch.object(module, "build_hybrid_provider_registry", return_value={"openai": mock.Mock()}), \
            mock.patch.object(module, "probe_remote_provider", return_value=backend_status), \
            mock.patch.object(
                module,
                "run_openai_hybrid",
                return_value={
                    "result_payload": {"mermaid": raw_flowchart, "confidence": 0.9, "rationale": "Raw flowchart response."},
                    "raw_content": raw_flowchart,
                    "response_payload": {},
                    "transport": "openai",
                },
            ):
            payload = module.generate_mermaid(
                repo_root=repo,
                kind_name="request",
                title="Normalized request",
                values={
                    "NEEDS_PLACEHOLDER": "- Remote path",
                    "CONTEXT_PLACEHOLDER": "- Provider returned raw flowchart",
                    "ACCEPTANCE_PLACEHOLDER": "- AC1: Normalize the managed Mermaid block",
                },
            )

        self.assertEqual(payload["backend_used"], "openai")
        self.assertEqual(payload["result_status"], "ok")
        self.assertTrue(payload["mermaid"].startswith("```mermaid\n%% logics-kind: request\n%% logics-signature: "))
        self.assertIn("flowchart TD", payload["mermaid"])


if __name__ == "__main__":
    unittest.main()
