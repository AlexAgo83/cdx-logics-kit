"""Sandbox lifecycle tests for the Logics kit.

Covers fresh bootstrap, idempotent re-run, doctor convergence,
schema migration, and update behavior in deterministic sandbox
repositories. All tests use tempfile-based repos — no network
or remote assumptions.

Wave 4 of task_113 / item_242 / req_129.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class KitLifecycleTest(unittest.TestCase):
    """Deterministic sandbox lifecycle tests for the Logics kit CLI."""

    def _cli_script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics.py"

    def _flow_script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_flow.py"

    def _run(self, script: Path, args: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script)] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env or os.environ,
            check=False,
        )

    def _run_json(self, script: Path, args: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> dict:
        result = self._run(script, args + ["--format", "json"], cwd, env=env)
        self.assertEqual(result.returncode, 0, f"Command failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return json.loads(result.stdout)

    def _write_doc(self, path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Fresh bootstrap ───────────────────────────────────────────────────

    def test_fresh_bootstrap_creates_expected_structure(self) -> None:
        """Bootstrap from an empty directory creates logics.yaml, env files, and required directories."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = self._run_json(self._cli_script(), ["bootstrap"], repo)
            self.assertTrue(payload["ok"])

            # Core workflow directories (bootstrap creates these; logics/skills is user-managed)
            for directory in ("logics/request", "logics/backlog", "logics/tasks"):
                self.assertTrue((repo / directory).is_dir(), f"Missing directory: {directory}")

            # Config files
            self.assertTrue((repo / "logics.yaml").is_file())
            self.assertTrue((repo / ".env.local").is_file())

            # logics.yaml has valid content
            config_text = (repo / "logics.yaml").read_text(encoding="utf-8")
            self.assertIn("version:", config_text)

            # .env.local has provider placeholders
            env_text = (repo / ".env.local").read_text(encoding="utf-8")
            self.assertIn("OPENAI_API_KEY=", env_text)
            self.assertIn("GEMINI_API_KEY=", env_text)

    # ── Idempotent re-run ─────────────────────────────────────────────────

    def test_bootstrap_idempotent_rerun_succeeds(self) -> None:
        """Running bootstrap twice on the same repo succeeds without error and does not duplicate content."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            # First run
            payload1 = self._run_json(self._cli_script(), ["bootstrap"], repo)
            self.assertTrue(payload1["ok"])
            yaml_after_first = (repo / "logics.yaml").read_text(encoding="utf-8")

            # Second run
            payload2 = self._run_json(self._cli_script(), ["bootstrap"], repo)
            self.assertTrue(payload2["ok"])
            yaml_after_second = (repo / "logics.yaml").read_text(encoding="utf-8")

            # logics.yaml should not grow with duplicate content
            self.assertEqual(yaml_after_first, yaml_after_second)

    # ── Doctor convergence ────────────────────────────────────────────────

    def test_doctor_reports_issues_on_incomplete_repo(self) -> None:
        """Doctor detects missing directories in a repo with minimal logics structure."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            # Create logics.yaml and a logics/ dir so _find_repo_root succeeds,
            # but omit required subdirectories
            (repo / "logics.yaml").write_text("version: 1\n", encoding="utf-8")
            (repo / "logics" / "request").mkdir(parents=True, exist_ok=True)

            payload = self._run_json(self._flow_script(), ["sync", "doctor"], repo)
            self.assertFalse(payload["ok"])
            self.assertGreater(len(payload["issues"]), 0)

            # At least one issue should mention a missing directory
            codes = [issue["code"] for issue in payload["issues"]]
            self.assertIn("missing_directory", codes)

    def test_doctor_convergence_after_bootstrap_and_fix(self) -> None:
        """Doctor reports missing_directory for logics/skills after bootstrap; creating it resolves the issue."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._run_json(self._cli_script(), ["bootstrap"], repo)

            # Doctor should flag logics/skills as missing (bootstrap doesn't create it)
            payload_before = self._run_json(self._flow_script(), ["sync", "doctor"], repo)
            dir_issues_before = [i for i in payload_before["issues"] if i["code"] == "missing_directory"]
            self.assertGreater(len(dir_issues_before), 0)

            # Fix: create the missing directory
            (repo / "logics" / "skills").mkdir(parents=True, exist_ok=True)

            # Doctor should now report no structural directory issues
            payload_after = self._run_json(self._flow_script(), ["sync", "doctor"], repo)
            dir_issues_after = [i for i in payload_after["issues"] if i["code"] == "missing_directory"]
            self.assertEqual(len(dir_issues_after), 0, f"Still has issues: {dir_issues_after}")

    # ── Schema migration ──────────────────────────────────────────────────

    def test_migrate_schema_adds_version_to_docs_without_it(self) -> None:
        """migrate-schema adds Schema version to docs that lack it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / "logics.yaml").write_text("version: 1\nmutations:\n  mode: transactional\n  audit_log: logics/mutation_audit.jsonl\n", encoding="utf-8")

            # Create a doc without Schema version
            self._write_doc(
                repo / "logics" / "request" / "req_000_test.md",
                [
                    "## req_000_test - Test request",
                    "> From version: 1.0.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                ],
            )

            payload = self._run_json(self._flow_script(), ["sync", "migrate-schema"], repo)
            self.assertEqual(len(payload["modified_files"]), 1)

            # Verify the doc now has a Schema version
            updated = (repo / "logics" / "request" / "req_000_test.md").read_text(encoding="utf-8")
            self.assertIn("> Schema version:", updated)

    def test_migrate_schema_idempotent(self) -> None:
        """Running migrate-schema twice: second run modifies nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / "logics.yaml").write_text("version: 1\nmutations:\n  mode: transactional\n  audit_log: logics/mutation_audit.jsonl\n", encoding="utf-8")

            self._write_doc(
                repo / "logics" / "request" / "req_000_test.md",
                [
                    "## req_000_test - Test",
                    "> From version: 1.0.0",
                    "> Status: Draft",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                ],
            )

            # First run migrates
            payload1 = self._run_json(self._flow_script(), ["sync", "migrate-schema"], repo)
            self.assertEqual(len(payload1["modified_files"]), 1)

            # Second run: nothing to migrate
            payload2 = self._run_json(self._flow_script(), ["sync", "migrate-schema"], repo)
            self.assertEqual(len(payload2["modified_files"]), 0)

    # ── Schema status ─────────────────────────────────────────────────────

    def test_schema_status_counts_versions(self) -> None:
        """schema-status reports accurate counts of docs by schema version."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / "logics.yaml").write_text("version: 1\n", encoding="utf-8")

            self._write_doc(
                repo / "logics" / "request" / "req_000_a.md",
                [
                    "## req_000_a - A",
                    "> From version: 1.0.0",
                    "> Schema version: 1.0",
                    "> Status: Draft",
                ],
            )
            self._write_doc(
                repo / "logics" / "backlog" / "item_000_b.md",
                [
                    "## item_000_b - B",
                    "> From version: 1.0.0",
                    "> Status: Draft",
                ],
            )

            payload = self._run_json(self._flow_script(), ["sync", "schema-status"], repo)
            self.assertEqual(payload["doc_count"], 2)
            self.assertIn("1.0", payload["counts"])

    # ── Config show after bootstrap ───────────────────────────────────────

    def test_config_show_after_bootstrap_has_expected_defaults(self) -> None:
        """config show after bootstrap reports expected default values."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._run_json(self._cli_script(), ["bootstrap"], repo)

            payload = self._run_json(self._cli_script(), ["config", "show"], repo)
            config = payload["config"]
            self.assertEqual(config["workflow"]["split"]["policy"], "minimal-coherent")
            self.assertEqual(config["mutations"]["mode"], "transactional")
            self.assertEqual(config["hybrid_assist"]["default_backend"], "auto")

    # ── New doc after bootstrap (convergence) ─────────────────────────────

    def test_new_request_after_bootstrap_creates_valid_doc(self) -> None:
        """Creating a new request doc after bootstrap produces a valid workflow doc."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._run_json(self._cli_script(), ["bootstrap"], repo)

            # Install templates required for new doc creation
            self._install_flow_templates(repo)

            payload = self._run_json(
                self._flow_script(),
                ["new", "request", "--title", "Lifecycle test request"],
                repo,
            )
            self.assertEqual(payload["kind"], "request")
            created_path = repo / payload["path"]
            self.assertTrue(created_path.is_file())

            content = created_path.read_text(encoding="utf-8")
            self.assertIn("Lifecycle test request", content)
            self.assertIn("> Schema version:", content)
            self.assertIn("> Status:", content)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _install_flow_templates(self, repo: Path) -> None:
        source_root = Path(__file__).resolve().parents[1] / "logics-flow-manager"
        target_root = repo / "logics" / "skills" / "logics-flow-manager"
        for template_name in ("request.md", "backlog.md", "task.md"):
            source = source_root / "assets" / "templates" / template_name
            target = target_root / "assets" / "templates" / template_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
