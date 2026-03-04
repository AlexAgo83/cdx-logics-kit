import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfluenceDomainAliasTest(unittest.TestCase):
    def test_domain_alias_for_search_script(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "logics-connector-confluence"
            / "scripts"
            / "confluence_search_pages.py"
        )
        module = _load_module(script, "confluence_search_pages_test")

        with mock.patch.dict(os.environ, {"CONFLUENCE_DOMAINE": "https://legacy.example/wiki"}, clear=True):
            self.assertEqual(module._confluence_domain(), "https://legacy.example/wiki")

        with mock.patch.dict(
            os.environ,
            {
                "CONFLUENCE_DOMAIN": "https://new.example/wiki",
                "CONFLUENCE_DOMAINE": "https://legacy.example/wiki",
            },
            clear=True,
        ):
            self.assertEqual(module._confluence_domain(), "https://new.example/wiki")

    def test_domain_alias_for_import_script(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "logics-connector-confluence"
            / "scripts"
            / "confluence_to_request.py"
        )
        module = _load_module(script, "confluence_to_request_test")

        with mock.patch.dict(os.environ, {"CONFLUENCE_DOMAINE": "https://legacy.example/wiki"}, clear=True):
            self.assertEqual(module._confluence_domain(), "https://legacy.example/wiki")

        with mock.patch.dict(os.environ, {"CONFLUENCE_DOMAIN": "https://new.example/wiki"}, clear=True):
            self.assertEqual(module._confluence_domain(), "https://new.example/wiki")


if __name__ == "__main__":
    unittest.main()
