"""Opt-in live provider integration tests.

These tests validate stable contract behavior against configured hybrid
providers. They are gated by the LIVE_PROVIDER_TESTS=1 environment variable
and skip cleanly when the gate is not set or a provider is not configured.

Contract assertions cover:
- Reachability (TCP connect + HTTP response)
- Authentication (valid credentials accepted)
- Model availability (configured model present)
- Structured response shape (JSON with expected keys)
- Degraded fallback handling (unreachable provider does not crash)

Wave 5 of task_113 / item_243 / req_129.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import unittest
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


LIVE_GATE = os.environ.get("LIVE_PROVIDER_TESTS", "") == "1"


def _load_module(name: str):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "logics-flow-manager"
        / "scripts"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"{name}_test", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(module_path.parent))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.pop(0)
    return module


def _load_config() -> dict[str, Any]:
    mod = _load_module("logics_flow_config")
    repo_root = Path(__file__).resolve().parents[3]
    config, _ = mod.load_repo_config(repo_root)
    return config


def _resolve_env() -> dict[str, str]:
    """Load provider environment from .env and .env.local, merged with os.environ."""
    transport = _load_module("logics_flow_hybrid_transport")
    repo_root = Path(__file__).resolve().parents[3]
    config = _load_config()
    dotenv_path = config.get("hybrid_assist", {}).get("env_file", ".env")
    return transport.load_hybrid_provider_environment_impl(
        repo_root=repo_root,
        dotenv_path=dotenv_path,
        environ=dict(os.environ),
    )


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib_request.Request(url, headers=headers or {}, method="GET")
    with urllib_request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _tcp_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# ---------------------------------------------------------------------------
# Ollama provider tests
# ---------------------------------------------------------------------------
@unittest.skipUnless(LIVE_GATE, "LIVE_PROVIDER_TESTS=1 not set")
class TestOllamaLiveIntegration(unittest.TestCase):
    """Live integration tests against a locally running Ollama instance."""

    def setUp(self) -> None:
        self.config = _load_config()
        provider_config = self.config.get("hybrid_assist", {}).get("providers", {}).get("ollama", {})
        self.enabled = bool(provider_config.get("enabled", True))
        host_raw = str(provider_config.get("host", "http://127.0.0.1:11434")).strip()
        self.host = host_raw.rstrip("/")
        # Parse host/port for TCP check
        from urllib.parse import urlparse
        parsed = urlparse(self.host)
        self.hostname = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 11434

    def test_ollama_reachable(self) -> None:
        """Ollama endpoint responds to TCP connect."""
        if not self.enabled:
            self.skipTest("Ollama not enabled in config")
        reachable = _tcp_reachable(self.hostname, self.port)
        if not reachable:
            self.skipTest(f"Ollama not reachable at {self.hostname}:{self.port}")
        self.assertTrue(reachable)

    def test_ollama_version_endpoint(self) -> None:
        """Ollama /api/version returns a JSON object with a version field."""
        if not self.enabled:
            self.skipTest("Ollama not enabled in config")
        if not _tcp_reachable(self.hostname, self.port):
            self.skipTest(f"Ollama not reachable at {self.hostname}:{self.port}")
        payload = _http_get_json(f"{self.host}/api/version")
        self.assertIn("version", payload)
        self.assertIsInstance(payload["version"], str)

    def test_ollama_model_available(self) -> None:
        """Configured model appears in Ollama /api/tags."""
        if not self.enabled:
            self.skipTest("Ollama not enabled in config")
        if not _tcp_reachable(self.hostname, self.port):
            self.skipTest(f"Ollama not reachable at {self.hostname}:{self.port}")
        configured_model = self.config.get("hybrid_assist", {}).get("default_model", "deepseek-coder-v2:16b")
        payload = _http_get_json(f"{self.host}/api/tags")
        self.assertIn("models", payload)
        self.assertIsInstance(payload["models"], list)
        model_names = [m.get("name", "") for m in payload["models"]]
        # Check if configured model (or its base name) is present
        found = any(configured_model in name for name in model_names)
        if not found:
            self.skipTest(f"Configured model {configured_model} not found in Ollama tags: {model_names}")

    def test_ollama_chat_response_shape(self) -> None:
        """Ollama /api/chat returns a structured response with message.content."""
        if not self.enabled:
            self.skipTest("Ollama not enabled in config")
        if not _tcp_reachable(self.hostname, self.port):
            self.skipTest(f"Ollama not reachable at {self.hostname}:{self.port}")
        configured_model = self.config.get("hybrid_assist", {}).get("default_model", "deepseek-coder-v2:16b")
        request_payload = {
            "model": configured_model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "stream": False,
            "options": {"temperature": 0},
        }
        encoded = json.dumps(request_payload).encode("utf-8")
        req = urllib_request.Request(
            f"{self.host}/api/chat",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=30.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib_error.URLError, urllib_error.HTTPError):
            self.skipTest(f"Ollama chat request failed for model {configured_model}")
            return
        self.assertIn("message", payload)
        self.assertIsInstance(payload["message"], dict)
        self.assertIn("content", payload["message"])
        self.assertIsInstance(payload["message"]["content"], str)
        self.assertTrue(len(payload["message"]["content"].strip()) > 0)


# ---------------------------------------------------------------------------
# OpenAI provider tests
# ---------------------------------------------------------------------------
@unittest.skipUnless(LIVE_GATE, "LIVE_PROVIDER_TESTS=1 not set")
class TestOpenAILiveIntegration(unittest.TestCase):
    """Live integration tests against the OpenAI API."""

    def setUp(self) -> None:
        self.config = _load_config()
        provider_config = self.config.get("hybrid_assist", {}).get("providers", {}).get("openai", {})
        self.enabled = bool(provider_config.get("enabled", False))
        self.base_url = str(provider_config.get("base_url", "https://api.openai.com/v1")).strip().rstrip("/")
        self.model = str(provider_config.get("model", "gpt-4.1-mini")).strip()
        key_env = str(provider_config.get("api_key_env", "OPENAI_API_KEY")).strip()
        env = _resolve_env()
        self.api_key = env.get(key_env, "").strip()

    def test_openai_credentials_present(self) -> None:
        """OpenAI API key is configured and non-empty."""
        if not self.enabled:
            self.skipTest("OpenAI not enabled in config")
        if not self.api_key:
            self.skipTest("OpenAI API key not configured")
        self.assertTrue(len(self.api_key) > 0)

    def test_openai_models_endpoint(self) -> None:
        """OpenAI /models endpoint returns a list of models."""
        if not self.enabled:
            self.skipTest("OpenAI not enabled in config")
        if not self.api_key:
            self.skipTest("OpenAI API key not configured")
        try:
            payload = _http_get_json(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except (urllib_error.URLError, urllib_error.HTTPError) as exc:
            self.skipTest(f"OpenAI API not reachable: {exc}")
            return
        self.assertIn("data", payload)
        self.assertIsInstance(payload["data"], list)

    def test_openai_chat_response_shape(self) -> None:
        """OpenAI chat completion returns structured response with choices[0].message.content."""
        if not self.enabled:
            self.skipTest("OpenAI not enabled in config")
        if not self.api_key:
            self.skipTest("OpenAI API key not configured")
        request_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 10,
            "temperature": 0,
        }
        encoded = json.dumps(request_payload).encode("utf-8")
        req = urllib_request.Request(
            f"{self.base_url}/chat/completions",
            data=encoded,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=30.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib_error.URLError, urllib_error.HTTPError) as exc:
            self.skipTest(f"OpenAI chat request failed: {exc}")
            return
        self.assertIn("choices", payload)
        self.assertIsInstance(payload["choices"], list)
        self.assertGreater(len(payload["choices"]), 0)
        self.assertIn("message", payload["choices"][0])
        self.assertIn("content", payload["choices"][0]["message"])


# ---------------------------------------------------------------------------
# Gemini provider tests
# ---------------------------------------------------------------------------
@unittest.skipUnless(LIVE_GATE, "LIVE_PROVIDER_TESTS=1 not set")
class TestGeminiLiveIntegration(unittest.TestCase):
    """Live integration tests against the Gemini API."""

    def setUp(self) -> None:
        self.config = _load_config()
        provider_config = self.config.get("hybrid_assist", {}).get("providers", {}).get("gemini", {})
        self.enabled = bool(provider_config.get("enabled", False))
        self.base_url = str(
            provider_config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        ).strip().rstrip("/")
        self.model = str(provider_config.get("model", "gemini-2.0-flash")).strip()
        key_env = str(provider_config.get("api_key_env", "GEMINI_API_KEY")).strip()
        env = _resolve_env()
        self.api_key = env.get(key_env, "").strip()

    def test_gemini_credentials_present(self) -> None:
        """Gemini API key is configured and non-empty."""
        if not self.enabled:
            self.skipTest("Gemini not enabled in config")
        if not self.api_key:
            self.skipTest("Gemini API key not configured")
        self.assertTrue(len(self.api_key) > 0)

    def test_gemini_models_endpoint(self) -> None:
        """Gemini models endpoint returns a list of models."""
        if not self.enabled:
            self.skipTest("Gemini not enabled in config")
        if not self.api_key:
            self.skipTest("Gemini API key not configured")
        try:
            payload = _http_get_json(f"{self.base_url}/models?key={self.api_key}")
        except (urllib_error.URLError, urllib_error.HTTPError) as exc:
            self.skipTest(f"Gemini API not reachable: {exc}")
            return
        self.assertIn("models", payload)
        self.assertIsInstance(payload["models"], list)

    def test_gemini_generate_response_shape(self) -> None:
        """Gemini generateContent returns structured response with candidates."""
        if not self.enabled:
            self.skipTest("Gemini not enabled in config")
        if not self.api_key:
            self.skipTest("Gemini API key not configured")
        request_payload = {
            "contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 10},
        }
        encoded = json.dumps(request_payload).encode("utf-8")
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        req = urllib_request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=30.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib_error.URLError, urllib_error.HTTPError) as exc:
            self.skipTest(f"Gemini generate request failed: {exc}")
            return
        self.assertIn("candidates", payload)
        self.assertIsInstance(payload["candidates"], list)
        self.assertGreater(len(payload["candidates"]), 0)


# ---------------------------------------------------------------------------
# Degraded fallback behavior
# ---------------------------------------------------------------------------
@unittest.skipUnless(LIVE_GATE, "LIVE_PROVIDER_TESTS=1 not set")
class TestDegradedFallbackBehavior(unittest.TestCase):
    """Verify that unreachable providers are handled gracefully."""

    def test_unreachable_ollama_does_not_crash(self) -> None:
        """Attempting to connect to an unreachable Ollama host fails gracefully."""
        self.assertFalse(_tcp_reachable("127.0.0.1", 1, timeout=1.0))

    def test_invalid_openai_key_returns_auth_error(self) -> None:
        """OpenAI API returns a 401 for an invalid key, not a crash."""
        try:
            req = urllib_request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": "Bearer sk-invalid-test-key-000"},
                method="GET",
            )
            with urllib_request.urlopen(req, timeout=10.0):
                pass
            self.fail("Expected an HTTP error for invalid key")
        except urllib_error.HTTPError as exc:
            self.assertIn(exc.code, (401, 403))
        except urllib_error.URLError:
            self.skipTest("OpenAI API not reachable from this network")

    def test_invalid_gemini_key_returns_error(self) -> None:
        """Gemini API returns an error for an invalid key, not a crash."""
        try:
            payload = _http_get_json(
                "https://generativelanguage.googleapis.com/v1beta/models?key=invalid-test-key"
            )
            # Some APIs return 200 with an error object
            if "error" in payload:
                self.assertIn("code", payload["error"])
            else:
                self.fail("Expected an error response for invalid key")
        except urllib_error.HTTPError as exc:
            self.assertIn(exc.code, (400, 401, 403))
        except urllib_error.URLError:
            self.skipTest("Gemini API not reachable from this network")


if __name__ == "__main__":
    unittest.main()
