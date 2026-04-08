import json
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
            (repo / "logics" / "product").mkdir(parents=True)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)

            (repo / "logics" / "product" / "prod_000_checkout.md").write_text(
                "\n".join(
                    [
                        "## prod_000_checkout - Checkout framing",
                        "> Date: 2026-03-14",
                        "> Status: Proposed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

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
            self.assertIn("(product/prod_000_checkout.md)", index_content)
            self.assertIn("(request/req_000_demo.md)", index_content)
            self.assertNotIn(str(repo).replace("\\", "/"), index_content)

    def test_indexer_supports_json_output_and_reports_incremental_stats(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-indexer" / "scripts" / "generate_index.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)
            (repo / "logics" / "skills").mkdir(parents=True)

            (repo / "logics.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "index:",
                        "  enabled: true",
                        "  path: logics/.cache/runtime_index.json",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "logics" / "request" / "req_000_demo.md").write_text(
                "\n".join(
                    [
                        "## req_000_demo - Demo request",
                        "> From version: 1.2.0",
                        "> Schema version: 1.2.0",
                        "> Status: Done",
                        "> Understanding: 100%",
                        "> Confidence: 100%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            first = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertTrue(first_payload["ok"])
            self.assertGreaterEqual(first_payload["index_stats"]["cache_misses"], 1)

            second = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertGreaterEqual(second_payload["index_stats"]["cache_hits"], 1)


class RelationshipLinkerTest(unittest.TestCase):
    def test_relationship_report_includes_guardrails_for_orphans_and_missing_refs(self) -> None:
        script = Path(__file__).resolve().parents[1] / "logics-relationship-linker" / "scripts" / "link_relations.py"

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics" / "request").mkdir(parents=True)
            (repo / "logics" / "backlog").mkdir(parents=True)
            (repo / "logics" / "tasks").mkdir(parents=True)

            (repo / "logics" / "request" / "req_000_root.md").write_text(
                "\n".join(
                    [
                        "## req_000_root - Root request",
                        "> Status: Draft",
                        "Related backlog: `item_001_known`",
                        "Related task: `task_999_missing`",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "logics" / "backlog" / "item_001_known.md").write_text(
                "\n".join(
                    [
                        "## item_001_known - Known backlog",
                        "> Status: Ready",
                        "> Progress: 10%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (repo / "logics" / "tasks" / "task_001_orphan.md").write_text(
                "\n".join(
                    [
                        "## task_001_orphan - Orphan task",
                        "> Status: Ready",
                        "> Progress: 0%",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(script), "--out", "logics/RELATIONSHIPS.md"],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            report = (repo / "logics" / "RELATIONSHIPS.md").read_text(encoding="utf-8")
            self.assertIn("Orphan docs: task_001_orphan", report)
            self.assertIn("Unresolved refs:", report)
            self.assertIn("req_000_root: task_999_missing", report)
            self.assertIn("Missing refs: task_999_missing", report)
            self.assertIn("Outgoing: item_001_known", report)


if __name__ == "__main__":
    unittest.main()
