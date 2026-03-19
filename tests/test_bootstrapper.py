from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BootstrapperTest(unittest.TestCase):
    def test_bootstrap_creates_product_dir_and_updated_instructions(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-bootstrapper" / "scripts" / "logics_bootstrap.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((repo / "logics" / "product" / ".gitkeep").is_file())

            instructions = (repo / "logics" / "instructions.md").read_text(encoding="utf-8")
            self.assertIn("* `logics/product`: Product briefs and product decision framing docs.", instructions)
            self.assertIn("Use the following indicators in product briefs:", instructions)
            self.assertIn("Use the following indicators in architecture docs:", instructions)
            self.assertIn("Canonical examples use `python ...`;", instructions)
            self.assertIn("`python logics/skills/logics-flow-manager/scripts/logics_flow.py`", instructions)
            self.assertNotIn("python3 logics/skills/", instructions)


if __name__ == "__main__":
    unittest.main()
