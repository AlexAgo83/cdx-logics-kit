from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DocFixerTest(unittest.TestCase):
    def test_product_and_architecture_docs_get_required_indicators_and_refs(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-doc-fixer" / "scripts" / "fix_logics_docs.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "product").mkdir(parents=True)
            (repo / "logics" / "architecture").mkdir(parents=True)

            (repo / "logics" / "request" / "req_000_guest_checkout.md").write_text(
                "## req_000_guest_checkout - Guest checkout\n",
                encoding="utf-8",
            )
            (repo / "logics" / "backlog" / "item_000_guest_checkout.md").write_text(
                "## item_000_guest_checkout - Guest checkout\n",
                encoding="utf-8",
            )
            product = repo / "logics" / "product" / "prod_000_guest_checkout.md"
            architecture = repo / "logics" / "architecture" / "adr_000_guest_checkout.md"
            product.write_text("## prod_000_guest_checkout - Guest checkout\n", encoding="utf-8")
            architecture.write_text("## adr_000_guest_checkout - Guest checkout\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(script), "--write"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)

            product_text = product.read_text(encoding="utf-8")
            architecture_text = architecture.read_text(encoding="utf-8")
            request_text = (repo / "logics" / "request" / "req_000_guest_checkout.md").read_text(encoding="utf-8")

            self.assertIn("# Companion docs", request_text)
            self.assertIn("- Product brief(s): `prod_000_guest_checkout`", request_text)
            self.assertIn("- Architecture decision(s): `adr_000_guest_checkout`", request_text)
            self.assertIn("> Date: YYYY-MM-DD", product_text)
            self.assertIn("> Status: Proposed", product_text)
            self.assertIn("> Related request: `req_000_guest_checkout`", product_text)
            self.assertIn("> Related backlog: `item_000_guest_checkout`", product_text)
            self.assertIn("> Reminder: Update this doc when the framing changes.", product_text)
            self.assertIn("# Product problem", product_text)
            self.assertIn("# References", product_text)
            self.assertIn("- `logics/request/req_000_guest_checkout.md`", product_text)
            self.assertIn("- `logics/backlog/item_000_guest_checkout.md`", product_text)

            self.assertIn("> Date: YYYY-MM-DD", architecture_text)
            self.assertIn("> Status: Proposed", architecture_text)
            self.assertIn("> Drivers: List the main architectural drivers.", architecture_text)
            self.assertIn("> Related request: `req_000_guest_checkout`", architecture_text)
            self.assertIn("> Related backlog: `item_000_guest_checkout`", architecture_text)
            self.assertIn("> Reminder: Update this doc when the framing changes.", architecture_text)
            self.assertIn("# Decision", architecture_text)
            self.assertIn("# References", architecture_text)
            self.assertIn("- `logics/request/req_000_guest_checkout.md`", architecture_text)
            self.assertIn("- `logics/backlog/item_000_guest_checkout.md`", architecture_text)


if __name__ == "__main__":
    unittest.main()
