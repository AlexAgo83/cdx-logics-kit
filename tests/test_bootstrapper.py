from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BootstrapperTest(unittest.TestCase):
    def test_bootstrap_creates_product_dir_and_updated_instructions(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-bootstrapper" / "scripts" / "logics_bootstrap.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((repo / "logics" / "product" / ".gitkeep").is_file())

            instructions = (repo / "logics" / "instructions.md").read_text(encoding="utf-8")
            self.assertIn("* `logics/product`: Product briefs and product decision framing docs.", instructions)
            self.assertIn("Use the following indicators in product briefs:", instructions)
            self.assertIn("Use the following indicators in architecture docs:", instructions)
            self.assertIn("Canonical examples use `python ...`;", instructions)
            self.assertIn("`python logics/skills/logics.py flow ...`", instructions)
            self.assertNotIn("python3 logics/skills/", instructions)
            config_text = (repo / "logics.yaml").read_text(encoding="utf-8")
            self.assertIn("policy: minimal-coherent", config_text)
            self.assertIn("mode: transactional", config_text)
            self.assertIn("audit_log: logics/.cache/hybrid_assist_audit.jsonl", config_text)
            self.assertIn("measurement_log: logics/.cache/hybrid_assist_measurements.jsonl", config_text)
            gitignore_text = (repo / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("# Generated Logics runtime artifacts", gitignore_text)
            self.assertIn("logics/.cache/", gitignore_text)
            self.assertIn("logics/mutation_audit.jsonl", gitignore_text)

    def test_bootstrap_supports_json_output(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-bootstrapper" / "scripts" / "logics_bootstrap.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"])
            created_paths = {entry["path"] for entry in payload["actions_needed"]}
            self.assertIn("logics.yaml", created_paths)
            self.assertIn(".gitignore", created_paths)
            self.assertTrue((repo / "logics.yaml").is_file())

    def test_bootstrap_appends_missing_runtime_ignores_without_clobbering_existing_gitignore(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-bootstrapper" / "scripts" / "logics_bootstrap.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            gitignore_path = repo / ".gitignore"
            gitignore_path.write_text("node_modules/\n*.vsix\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            gitignore_text = gitignore_path.read_text(encoding="utf-8")
            self.assertIn("node_modules/\n*.vsix\n", gitignore_text)
            self.assertEqual(gitignore_text.count("# Generated Logics runtime artifacts"), 1)
            self.assertIn("logics/.cache/", gitignore_text)
            self.assertIn("logics/mutation_audit.jsonl", gitignore_text)

            rerun = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertEqual(gitignore_text, gitignore_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
