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


class LogicsFlowTestBase(unittest.TestCase):
    def _script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager" / "scripts" / "logics_flow.py"

    def _cli_script(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics.py"

    def _flow_manager_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "logics-flow-manager"

    def _hybrid_module(self):
        module_path = self._flow_manager_root() / "scripts" / "logics_flow_hybrid.py"
        spec = importlib.util.spec_from_file_location("logics_flow_hybrid_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(module_path.parent))
        try:
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
            sys.path.pop(0)
        return module

    def _flow_module(self):
        module_path = self._flow_manager_root() / "scripts" / "logics_flow.py"
        spec = importlib.util.spec_from_file_location("logics_flow_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(module_path.parent))
        try:
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
            sys.path.pop(0)
        return module

    def _core_module(self):
        module_path = self._flow_manager_root() / "scripts" / "logics_flow_core.py"
        spec = importlib.util.spec_from_file_location("logics_flow_core_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(module_path.parent))
        try:
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
            sys.path.pop(0)
        return module

    def _fixtures_root(self) -> Path:
        return Path(__file__).resolve().parent / "fixtures"

    def _write_doc(self, path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _install_flow_templates(self, repo: Path) -> None:
        source_root = self._flow_manager_root()
        target_root = repo / "logics" / "skills" / "logics-flow-manager"
        for template_name in ("request.md", "backlog.md", "task.md"):
            source = source_root / "assets" / "templates" / template_name
            target = target_root / "assets" / "templates" / template_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def _install_skill_fixture(self, repo: Path, fixture_name: str, skill_name: str) -> Path:
        source = self._fixtures_root() / fixture_name
        target = repo / "logics" / "skills" / skill_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return target

    def _status(self, path: Path) -> str | None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("> Status:"):
                return line.split(":", 1)[1].strip()
        return None

    def _progress(self, path: Path) -> str | None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("> Progress:"):
                return line.split(":", 1)[1].strip()
        return None

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
