from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProductBriefWriterTest(unittest.TestCase):
    def test_dry_run_renders_overview_and_mermaid(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "logics-product-brief-writer"
            / "scripts"
            / "new_product_brief.py"
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics").mkdir()
            skills_dir = repo / "logics" / "skills" / "logics-product-brief-writer"
            template_dir = skills_dir / "assets" / "templates"
            template_dir.mkdir(parents=True)
            template_dir.joinpath("product_brief.md").write_text(
                (
                    Path(__file__).resolve().parents[1]
                    / "logics-product-brief-writer"
                    / "assets"
                    / "templates"
                    / "product_brief.md"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--title", "Guest checkout framing", "--dry-run"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("# Overview", completed.stdout)
            self.assertIn("```mermaid", completed.stdout)
            self.assertIn("flowchart LR", completed.stdout)
            self.assertIn("prod_000_guest_checkout_framing", completed.stdout)


if __name__ == "__main__":
    unittest.main()
