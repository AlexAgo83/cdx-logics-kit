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
    def test_assist_handoff_and_split_aliases_return_targeted_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            request = repo / "logics" / "request" / "req_000_handoff_seed.md"
            self._write_doc(
                request,
                [
                    "## req_000_handoff_seed - Handoff seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Ready",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "",
                    "# Needs",
                    "- Prepare a compact handoff packet.",
                    "- Keep the split to the minimum coherent slices.",
                    "",
                    "# Acceptance criteria",
                    "- AC1: Generate a reusable handoff.",
                    "- AC2: Suggest a bounded split.",
                ],
            )

            handoff = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "handoff",
                    "req_000_handoff_seed",
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
            split = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "suggest-split",
                    "req_000_handoff_seed",
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

            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            self.assertEqual(split.returncode, 0, split.stderr)
            handoff_payload = json.loads(handoff.stdout)
            split_payload = json.loads(split.stdout)
            self.assertEqual(handoff_payload["result"]["target_ref"], "req_000_handoff_seed")
            self.assertTrue(handoff_payload["result"]["files_of_interest"])
            self.assertEqual(split_payload["result"]["target_ref"], "req_000_handoff_seed")
            self.assertGreaterEqual(len(split_payload["result"]["suggested_titles"]), 2)

    def test_assist_validation_and_consistency_aliases_return_structured_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True, exist_ok=True)
            validation = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-validation",
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
            consistency = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "doc-consistency",
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

            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertEqual(consistency.returncode, 0, consistency.stderr)
            validation_payload = json.loads(validation.stdout)
            consistency_payload = json.loads(consistency.stdout)
            self.assertIn(validation_payload["result"]["overall"], {"pass", "warning", "fail"})
            self.assertTrue(validation_payload["result"]["commands"])
            self.assertIn(consistency_payload["result"]["overall"], {"clean", "issues-found"})
            self.assertTrue(consistency_payload["result"]["issues"])

    def test_assist_summary_and_closure_aliases_return_structured_outputs(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = repo / "logics" / "tasks" / "task_000_summary_seed.md"
            self._write_doc(
                task,
                [
                    "## task_000_summary_seed - Summary seed",
                    "> From version: 1.12.1",
                    "> Schema version: 1.0",
                    "> Status: Done",
                    "> Understanding: 100%",
                    "> Confidence: 100%",
                    "> Progress: 100%",
                    "",
                    "# Context",
                    "- Summarize this delivery.",
                    "",
                    "# Validation",
                    "- python logics/skills/logics.py lint",
                ],
            )

            pr_summary = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-pr",
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
            changelog = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "summarize-changelog",
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
            closure = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "closure-summary",
                    "task_000_summary_seed",
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

            self.assertEqual(pr_summary.returncode, 0, pr_summary.stderr)
            self.assertEqual(changelog.returncode, 0, changelog.stderr)
            self.assertEqual(closure.returncode, 0, closure.stderr)
            pr_payload = json.loads(pr_summary.stdout)
            changelog_payload = json.loads(changelog.stdout)
            closure_payload = json.loads(closure.stdout)
            self.assertTrue(pr_payload["result"]["highlights"])
            self.assertTrue(changelog_payload["result"]["entries"])
            self.assertEqual(closure_payload["result"]["target_ref"], "task_000_summary_seed")
            self.assertTrue(closure_payload["result"]["delivered"])

    def test_assist_validation_checklist_alias_responds_to_plugin_and_runtime_changes(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (repo / "src").mkdir(parents=True, exist_ok=True)
            (repo / "src" / "feature.ts").write_text("export const x = 1;\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "validation-checklist",
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
            self.assertTrue(payload["result"]["checks"])
            self.assertIn(payload["result"]["profile"], {"docs-only", "runtime", "plugin", "mixed"})

    def test_assist_commit_all_execute_commits_simple_repo(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            readme = repo / "README.md"
            readme.write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            readme.write_text("demo\nmore\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "commit-all",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
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
            self.assertTrue(payload["executed"])
            self.assertEqual(len(payload["execution_result"]["steps"]), 1)
            log = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(log.returncode, 0, log.stderr)
            self.assertEqual(log.stdout.strip(), payload["execution_result"]["steps"][0]["message"])

    def test_assist_commit_all_skips_clean_submodule_and_commits_parent_pointer(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submodule_source = root / "skills-source"
            parent_repo = root / "parent"

            submodule_source.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=submodule_source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=submodule_source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=submodule_source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (submodule_source / "README.md").write_text("skills\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=submodule_source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init submodule"], cwd=submodule_source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            parent_repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=parent_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=parent_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=parent_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(
                ["git", "-c", "protocol.file.allow=always", "submodule", "add", str(submodule_source.resolve()), "logics/skills"],
                cwd=parent_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            subprocess.run(["git", "commit", "-am", "init parent"], cwd=parent_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            nested_submodule = parent_repo / "logics" / "skills"
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=nested_submodule, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=nested_submodule, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (nested_submodule / "README.md").write_text("skills\nupdated\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=nested_submodule, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "update submodule"], cwd=nested_submodule, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            submodule_head_before = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=nested_submodule,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(submodule_head_before.returncode, 0, submodule_head_before.stderr)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "assist",
                    "commit-all",
                    "--backend",
                    "codex",
                    "--execution-mode",
                    "execute",
                    "--format",
                    "json",
                ],
                cwd=parent_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["executed"])
            self.assertEqual(payload["plan"]["strategy"], "single")
            self.assertEqual(len(payload["execution_result"]["steps"]), 1)
            self.assertEqual(payload["execution_result"]["steps"][0]["scope"], "root")

            submodule_head_after = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=nested_submodule,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(submodule_head_after.returncode, 0, submodule_head_after.stderr)
            self.assertEqual(submodule_head_before.stdout.strip(), submodule_head_after.stdout.strip())

            parent_log = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=parent_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(parent_log.returncode, 0, parent_log.stderr)
            self.assertEqual(parent_log.stdout.strip(), payload["execution_result"]["steps"][0]["message"])

            parent_status = subprocess.run(
                ["git", "status", "--short"],
                cwd=parent_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(parent_status.returncode, 0, parent_status.stderr)
            self.assertEqual(parent_status.stdout.strip(), "")


    def _prepare_release_repo(self, repo: Path, version: str) -> None:
        """Set up a minimal clean git repo for prepare-release tests."""
        (repo / "logics").mkdir(parents=True, exist_ok=True)
        (repo / "logics" / ".gitkeep").write_text("", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        (repo / "package.json").write_text(json.dumps({"name": "test-pkg", "version": version}), encoding="utf-8")
        changelogs_dir = repo / "changelogs"
        changelogs_dir.mkdir(parents=True, exist_ok=True)
        (changelogs_dir / f"CHANGELOGS_{version.replace('.', '_')}.md").write_text("# Changelog\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_assist_prepare_release_suggestion_only_reports_readiness(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "1.2.3")

            result = subprocess.run(
                [sys.executable, str(script), "assist", "prepare-release", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["assist_kind"], "prepare-release")
            self.assertTrue(payload["changelog_status"]["exists"])
            self.assertTrue(payload["ready"])
            self.assertIn("prep_steps", payload)
            self.assertNotIn("publish_result", payload)

    def test_assist_prepare_release_not_ready_when_changelog_missing(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir(parents=True, exist_ok=True)
            (repo / "logics" / ".gitkeep").write_text("", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (repo / "package.json").write_text(json.dumps({"name": "test-pkg", "version": "2.0.0"}), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            result = subprocess.run(
                [sys.executable, str(script), "assist", "prepare-release", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["changelog_status"]["exists"])
            self.assertFalse(payload["ready"])

    def test_assist_prepare_release_execute_reports_ready_when_already_prepared(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.0.0")

            result = subprocess.run(
                [
                    sys.executable, str(script), "assist", "prepare-release",
                    "--execution-mode", "execute",
                    "--format", "json",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["prep_steps"], [])
            self.assertNotIn("publish_result", payload)

    def test_assist_prepare_release_not_ready_when_version_is_already_tagged(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.0.1")
            subprocess.run(["git", "tag", "v3.0.1"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            result = subprocess.run(
                [sys.executable, str(script), "assist", "prepare-release", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["changelog_status"]["exists"])
            self.assertTrue(payload["changelog_status"]["already_published"])
            self.assertTrue(payload["changelog_status"]["tag_exists_local"])
            self.assertFalse(payload["ready"])
            self.assertIn("already tagged or published", payload["changelog_status"]["summary"])
