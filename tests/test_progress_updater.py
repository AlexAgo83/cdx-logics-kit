from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProgressUpdaterTest(unittest.TestCase):
    def test_product_doc_indicators_can_be_updated(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-progress-updater" / "scripts" / "update_indicators.py"

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
                [
                    sys.executable,
                    str(script),
                    str(product),
                    "--status",
                    "Active",
                    "--related-backlog",
                    "`item_000_guest_checkout`",
                    "--reminder",
                    "Keep this brief aligned with the current product direction.",
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            content = product.read_text(encoding="utf-8")
            self.assertIn("> Status: Active", content)
            self.assertIn("> Related backlog: `item_000_guest_checkout`", content)
            self.assertIn("> Reminder: Keep this brief aligned with the current product direction.", content)


if __name__ == "__main__":
    unittest.main()
