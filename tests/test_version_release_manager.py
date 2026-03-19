import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "logics-version-release-manager" / "scripts" / "publish_version_release.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("version_release_manager", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


class VersionReleaseManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)
        git(self.repo_root, "init")
        git(self.repo_root, "config", "user.name", "Test User")
        git(self.repo_root, "config", "user.email", "test@example.com")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, rel_path: str, content: str) -> None:
        path = self.repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.repo_root, "add", ".")
        git(self.repo_root, "commit", "-m", message)

    def test_build_release_commands(self) -> None:
        commands = self.module.build_release_commands(
            version="1.0.1",
            notes_file=Path("changelogs/CHANGELOGS_1_0_1.md"),
            title="Stable v1.0.1",
            create_tag=True,
            push=True,
            draft=True,
        )
        self.assertEqual(commands[0][:3], ["git", "tag", "-a"])
        self.assertEqual(commands[1], ["git", "push", "origin", "main"])
        self.assertIn("--draft", commands[-1])

    def test_dry_run_prints_release_commands(self) -> None:
        self.write("VERSION", "1.0.1\n")
        self.write("changelogs/CHANGELOGS_1_0_1.md", "# Changelog\n")
        self.commit("Prepare release files")

        stdout = io.StringIO()
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.repo_root)
            with contextlib.redirect_stdout(stdout):
                exit_code = self.module.main(["--dry-run"])
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("gh release create v1.0.1", output)

    def test_non_dry_run_requires_clean_git(self) -> None:
        self.write("VERSION", "1.0.1\n")
        self.write("changelogs/CHANGELOGS_1_0_1.md", "# Changelog\n")
        self.write("README.md", "# Dirty\n")

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.repo_root)
            with self.assertRaises(SystemExit):
                self.module.main([])
        finally:
            os.chdir(previous_cwd)
