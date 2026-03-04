import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class IndexerLinksTest(unittest.TestCase):
    def test_index_links_are_relative_to_output_file(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-indexer" / "scripts" / "generate_index.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)

            (repo / "logics" / "request" / "req_000_demo.md").write_text(
                "\n".join(
                    [
                        "## req_000_demo - Demo request",
                        "> From version: 1.2.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--out", "logics/INDEX.md"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            index_content = (repo / "logics" / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("(request/req_000_demo.md)", index_content)
            self.assertNotIn(str(repo).replace("\\", "/"), index_content)


if __name__ == "__main__":
    unittest.main()
