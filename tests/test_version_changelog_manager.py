import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "logics-version-changelog-manager" / "scripts" / "generate_version_changelog.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("version_changelog_manager", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


class VersionChangelogManagerTest(unittest.TestCase):
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

    def test_generates_versioned_changelog_from_git_history(self) -> None:
        self.write("VERSION", "1.0.0\n")
        self.write("README.md", "# Kit\n")
        self.commit("Initial release state")
        git(self.repo_root, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")

        self.write(".github/workflows/ci.yml", "name: CI\n")
        self.commit("Add CI workflow")
        self.write("logics-version-release-manager/SKILL.md", "---\n")
        self.commit("Add release automation skill")

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.repo_root)
            exit_code = self.module.main(["--version", "1.0.1", "--previous-tag", "v1.0.0"])
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(exit_code, 0)
        output_path = self.repo_root / "changelogs" / "CHANGELOGS_1_0_1.md"
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("# Changelog (`1.0.0 -> 1.0.1`)", content)
        self.assertIn("Add CI workflow", content)
        self.assertIn("Add release automation skill", content)

    def test_normalize_version_rejects_invalid_values(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.normalize_version("1.0")

    def test_resolve_version_prefers_package_json_when_version_file_is_stale(self) -> None:
        self.write("VERSION", "1.0.0\n")
        self.write("package.json", '{"name":"demo","version":"1.0.2"}\n')

        self.assertEqual(self.module.resolve_version(self.repo_root), "1.0.2")
