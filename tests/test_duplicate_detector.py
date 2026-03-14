from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DuplicateDetectorTest(unittest.TestCase):
    def test_product_and_architecture_docs_are_scanned(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-duplicate-detector" / "scripts" / "find_duplicates.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "product").mkdir(parents=True)
            (repo / "logics" / "architecture").mkdir(parents=True)

            (repo / "logics" / "product" / "prod_000_guest_checkout.md").write_text(
                "\n".join(
                    [
                        "## prod_000_guest_checkout - Guest checkout framing",
                        "",
                        "# Overview",
                        "Guest checkout should reduce purchase friction and improve first conversion.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            (repo / "logics" / "architecture" / "adr_000_guest_checkout.md").write_text(
                "\n".join(
                    [
                        "## adr_000_guest_checkout - Guest checkout framing",
                        "",
                        "# Overview",
                        "Guest checkout should reduce purchase friction and improve first conversion.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--min-score", "0.8", "--include-related"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("prod_000_guest_checkout", completed.stdout)
            self.assertIn("adr_000_guest_checkout", completed.stdout)


if __name__ == "__main__":
    unittest.main()
