from __future__ import annotations

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
    def test_assist_next_step_alias_routes_to_shared_runtime(self) -> None:
        script = self._script()

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

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "next-step",
                    "req_000_hybrid_seed",
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
            self.assertEqual(payload["flow"], "next-step")
            self.assertEqual(payload["result"]["decision"]["action"], "promote")
            self.assertEqual(payload["result"]["decision"]["target_ref"], "req_000_hybrid_seed")

    def test_assist_request_draft_alias_returns_validated_json_without_writing_files(self) -> None:
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
                    "Add a request draft for a lightweight offline validation recap",
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
            self.assertEqual(payload["flow"], "request-draft")
            self.assertEqual(payload["backend_used"], "codex")
            self.assertTrue(payload["result"]["needs"])
            self.assertTrue(payload["result"]["context"])
            self.assertFalse((repo / "logics" / "request").exists())

            measurement_log = repo / payload["measurement_log"]
            self.assertTrue(measurement_log.is_file())
            measurement_records = [json.loads(line) for line in measurement_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(measurement_records[-1]["flow"], "request-draft")
