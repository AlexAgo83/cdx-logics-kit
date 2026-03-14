from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConfidenceBoosterTest(unittest.TestCase):
    def test_product_doc_gets_clarifications_and_status_update(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-confidence-booster" / "scripts" / "boost_confidence.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            product = repo / "logics" / "product" / "prod_000_guest_checkout.md"
            product.parent.mkdir(parents=True)
            product.write_text(
                "\n".join(
                    [
                        "## prod_000_guest_checkout - Guest checkout",
                        "> Date: 2026-03-14",
                        "> Status: Proposed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), str(product), "--apply-defaults", "--status", "Active"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            content = product.read_text(encoding="utf-8")
            self.assertIn("> Status: Active", content)
            self.assertIn("# Clarifications", content)
            self.assertIn("Define the primary user problem", content)


if __name__ == "__main__":
    unittest.main()
