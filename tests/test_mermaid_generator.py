from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
