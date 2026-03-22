from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CodexWorkspaceOverlayTest(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_codex_workspace.py"

    def _env(self, global_home: Path, workspaces_home: Path) -> dict[str, str]:
        env = dict(os.environ)
        env["LOGICS_CODEX_GLOBAL_HOME"] = str(global_home)
        env["LOGICS_CODEX_WORKSPACES_HOME"] = str(workspaces_home)
        return env

    def _write_skill(self, skills_root: Path, name: str, body: str) -> None:
        skill_dir = skills_root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")

    def _init_repo(self, repo: Path, skill_body: str, skill_name: str = "logics-demo-skill") -> None:
        self._write_skill(repo / "logics" / "skills", skill_name, skill_body)

    def test_sync_materializes_overlay_and_shadows_global_skill_name(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo-a"
            repo.mkdir()
            self._init_repo(repo, "# repo skill\n")

            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"
            self._write_skill(global_home / "skills", "logics-demo-skill", "# global skill\n")
            self._write_skill(global_home / "skills", "global-extra", "# extra skill\n")
            (global_home / "skills" / ".system").mkdir(parents=True)
            (global_home / "auth.json").write_text('{"ok":true}\n', encoding="utf-8")
            (global_home / "config.toml").write_text("model = 'gpt-5'\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo), "--json"],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            overlay_root = Path(payload["overlay_root"])
            skills_root = overlay_root / "skills"
            self.assertTrue((skills_root / "logics-demo-skill").exists())
            self.assertTrue((skills_root / "global-extra").exists())
            self.assertFalse((skills_root / "missing").exists())
            self.assertIn("logics-demo-skill", payload["shadowed_global_skills"])
            self.assertTrue((overlay_root / "auth.json").exists())
            self.assertTrue((overlay_root / "config.toml").exists())

            status = subprocess.run(
                [sys.executable, str(script), "status", "--repo", str(repo), "--json", "--fail-on-issues"],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["status"], "healthy")

    def test_run_sets_codex_home_for_the_child_process(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo-run"
            repo.mkdir()
            self._init_repo(repo, "# repo skill\n")
            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "run",
                    "--repo",
                    str(repo),
                    "--",
                    sys.executable,
                    "-c",
                    "import json, os; print(json.dumps({'codex_home': os.environ.get('CODEX_HOME')}))",
                ],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip())
            self.assertIn("codex-workspaces", payload["codex_home"])
            self.assertIn("repo-run", payload["codex_home"])

    def test_doctor_fix_rebuilds_missing_overlay(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo-doctor"
            repo.mkdir()
            self._init_repo(repo, "# repo skill\n")
            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"

            subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo)],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            overlay_roots = list(workspaces_home.glob("*"))
            self.assertEqual(len(overlay_roots), 1)
            overlay_root = overlay_roots[0]
            manifest = overlay_root / "logics-codex-overlay.json"
            manifest.unlink()

            before = subprocess.run(
                [sys.executable, str(script), "status", "--repo", str(repo), "--json"],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            before_payload = json.loads(before.stdout)
            self.assertEqual(before_payload["status"], "broken")

            repaired = subprocess.run(
                [sys.executable, str(script), "doctor", "--repo", str(repo), "--fix", "--json"],
                cwd=repo,
                env=self._env(global_home, workspaces_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            repaired_payload = json.loads(repaired.stdout)
            self.assertEqual(repaired_payload["status"], "healthy")
            self.assertEqual(repaired_payload["repair_result"], "Overlay rebuilt from repository state.")

    def test_two_repositories_keep_same_named_skills_isolated(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo_a = tmp_root / "repo-a"
            repo_b = tmp_root / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            self._init_repo(repo_a, "# repo a skill\n", skill_name="shared-skill")
            self._init_repo(repo_b, "# repo b skill\n", skill_name="shared-skill")

            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"
            env = self._env(global_home, workspaces_home)

            sync_a = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo_a), "--json"],
                cwd=repo_a,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            sync_b = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo_b), "--json"],
                cwd=repo_b,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(sync_a.returncode, 0, sync_a.stderr)
            self.assertEqual(sync_b.returncode, 0, sync_b.stderr)
            payload_a = json.loads(sync_a.stdout)
            payload_b = json.loads(sync_b.stdout)
            self.assertNotEqual(payload_a["workspace_id"], payload_b["workspace_id"])

            skill_a = Path(payload_a["overlay_root"]) / "skills" / "shared-skill" / "SKILL.md"
            skill_b = Path(payload_b["overlay_root"]) / "skills" / "shared-skill" / "SKILL.md"
            self.assertEqual(skill_a.read_text(encoding="utf-8"), "# repo a skill\n")
            self.assertEqual(skill_b.read_text(encoding="utf-8"), "# repo b skill\n")

    def test_copy_mode_reports_stale_overlay_when_repo_skill_changes(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo-copy"
            repo.mkdir()
            self._init_repo(repo, "# first copy\n", skill_name="copy-skill")
            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"
            env = self._env(global_home, workspaces_home)

            synced = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo), "--publication-mode", "copy", "--json"],
                cwd=repo,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(synced.returncode, 0, synced.stderr)
            payload = json.loads(synced.stdout)
            self.assertEqual(payload["publication_mode"], "copy")

            skill_path = repo / "logics" / "skills" / "copy-skill" / "SKILL.md"
            skill_path.write_text("# updated copy\n", encoding="utf-8")

            status = subprocess.run(
                [sys.executable, str(script), "status", "--repo", str(repo), "--json"],
                cwd=repo,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["status"], "stale")
            self.assertTrue(any("stale" in issue.lower() for issue in status_payload["issues"]))

    def test_status_all_reports_stale_registry_entry_after_repo_move(self) -> None:
        script = self._script()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo-move"
            repo.mkdir()
            self._init_repo(repo, "# move skill\n", skill_name="move-skill")
            global_home = tmp_root / "codex-home"
            workspaces_home = tmp_root / "codex-workspaces"
            env = self._env(global_home, workspaces_home)

            synced = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(repo), "--json"],
                cwd=repo,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(synced.returncode, 0, synced.stderr)
            payload = json.loads(synced.stdout)
            old_workspace_id = payload["workspace_id"]

            moved_repo = tmp_root / "repo-move-renamed"
            repo.rename(moved_repo)

            all_status = subprocess.run(
                [sys.executable, str(script), "status", "--all", "--json"],
                cwd=tmp_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(all_status.returncode, 0, all_status.stderr)
            statuses = json.loads(all_status.stdout)
            stale_entry = next(entry for entry in statuses if entry["workspace_id"] == old_workspace_id)
            self.assertEqual(stale_entry["status"], "stale")
            self.assertTrue(any("no longer exists" in issue.lower() for issue in stale_entry["issues"]))

            resynced = subprocess.run(
                [sys.executable, str(script), "sync", "--repo", str(moved_repo), "--json"],
                cwd=moved_repo,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(resynced.returncode, 0, resynced.stderr)
            new_payload = json.loads(resynced.stdout)
            self.assertNotEqual(old_workspace_id, new_payload["workspace_id"])


if __name__ == "__main__":
    unittest.main()
