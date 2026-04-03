import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "logics-changelog-curator" / "scripts" / "curate_changelog.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("changelog_curator", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ChangelogCuratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)
        (self.repo_root / "logics").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, rel_path: str, content: str) -> None:
        path = self.repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_curated_changelog_rewrites_repo_absolute_links_to_relative_targets(self) -> None:
        self.write(
            "logics/RELEASE_NOTES.md",
            "\n".join(
                [
                    "# Release notes",
                    "",
                    "- Update [README](/Users/alexandreagostini/Documents/cdx-logics-vscode/README.md) guidance.",
                    "- Refresh [flow skill](/Users/alexandreagostini/Documents/cdx-logics-vscode/logics/skills/logics-flow-manager/SKILL.md#L1).",
                    "",
                ]
            ),
        )

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.repo_root)
            exit_code = self.module.main([])
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(exit_code, 0)
        content = (self.repo_root / "logics/CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("[README](README.md)", content)
        self.assertIn("[flow skill](logics/skills/logics-flow-manager/SKILL.md)", content)
        self.assertNotIn("/Users/alexandreagostini/Documents", content)
