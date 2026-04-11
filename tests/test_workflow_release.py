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
    def test_assist_prepare_release_syncs_version_file_when_package_json_is_newer(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.0.2")
            (repo / "VERSION").write_text("3.0.1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "add stale VERSION"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

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
            self.assertFalse(payload["changelog_status"]["version_mismatch"])
            self.assertTrue(payload["ready"])
            self.assertIn("updated VERSION to match package.json", payload["prep_steps"])
            self.assertEqual((repo / "VERSION").read_text(encoding="utf-8"), "3.0.2\n")

    def test_assist_prepare_release_execute_bumps_next_version_when_current_is_already_tagged(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.0.3")
            subprocess.run(["git", "tag", "v3.0.3"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

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
            self.assertEqual(payload["changelog_status"]["version"], "3.0.4")
            self.assertFalse(payload["changelog_status"]["already_published"])
            self.assertIn("bumped release version to 3.0.4", payload["prep_steps"])
            self.assertTrue((repo / "changelogs" / "CHANGELOGS_3_0_4.md").is_file())
            package_payload = json.loads((repo / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(package_payload["version"], "3.0.4")
            self.assertEqual((repo / "VERSION").read_text(encoding="utf-8"), "3.0.4\n")

    def test_assist_publish_release_execute_dry_run_invokes_publish_script(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.1.0")
            publish_script = repo / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
            publish_script.parent.mkdir(parents=True, exist_ok=True)
            publish_script.write_text(
                "import sys, json\nprint(json.dumps({'dry_run': True, 'commands': []}))\nsys.exit(0)\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "add publish script"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            result = subprocess.run(
                [
                    sys.executable, str(script), "assist", "publish-release",
                    "--execution-mode", "execute",
                    "--dry-run",
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
            self.assertTrue(payload["executed"])
            self.assertIsNotNone(payload["publish_result"])
            self.assertTrue(payload["publish_result"]["ok"])

    def test_assist_publish_release_execute_blocks_when_version_is_already_tagged(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.1.1")
            publish_script = repo / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
            publish_script.parent.mkdir(parents=True, exist_ok=True)
            publish_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "add publish script"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "tag", "v3.1.1"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

            result = subprocess.run(
                [
                    sys.executable, str(script), "assist", "publish-release",
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
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["executed"])
            self.assertFalse(payload["publish_result"]["ok"])
            self.assertTrue(
                any("version already published or tagged" in entry for entry in payload["publish_result"]["blocking"])
            )

    def test_assist_publish_release_blocks_when_version_file_is_out_of_sync(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.1.2")
            publish_script = repo / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
            publish_script.parent.mkdir(parents=True, exist_ok=True)
            publish_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            (repo / "VERSION").write_text("3.1.1\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable, str(script), "assist", "publish-release",
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
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["executed"])
            self.assertFalse(payload["publish_result"]["ok"])
            self.assertTrue(
                any("VERSION is out of sync with package.json" in entry for entry in payload["publish_result"]["blocking"])
            )

    def test_assist_publish_release_suggestion_only_proposes_release_branch_update_when_stale(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "3.2.0")
            subprocess.run(["git", "branch", "release"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            (repo / "CHANGELOG_EXTRA.md").write_text("extra\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(["git", "commit", "-m", "advance current branch"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            current_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            ).stdout.strip()

            result = subprocess.run(
                [sys.executable, str(script), "assist", "publish-release", "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["release_branch"]["name"], "release")
            self.assertTrue(payload["release_branch"]["exists"])
            self.assertTrue(payload["release_branch"]["needs_update"])
            self.assertTrue(payload["release_branch"]["can_fast_forward"])
            self.assertIn(f"behind '{current_branch}'", payload["release_branch"]["suggestion"])
            self.assertIn("git switch release", payload["release_branch"]["command"])

    def test_assist_prepare_release_execute_not_ready_when_uncommitted_changes(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "4.0.0")
            (repo / "dirty.txt").write_text("untracked\n", encoding="utf-8")

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
            self.assertFalse(payload["ready"])
            self.assertNotIn("publish_result", payload)

    def test_assist_publish_release_execute_blocked_when_uncommitted_changes(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._prepare_release_repo(repo, "4.1.0")
            publish_script = repo / "logics" / "skills" / "logics-version-release-manager" / "scripts" / "publish_version_release.py"
            publish_script.parent.mkdir(parents=True, exist_ok=True)
            publish_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            (repo / "dirty.txt").write_text("untracked\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable, str(script), "assist", "publish-release",
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
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["executed"])
            self.assertFalse(payload["publish_result"]["ok"])
            self.assertIn("uncommitted changes present", payload["publish_result"]["blocking"])


if __name__ == "__main__":
    unittest.main()
