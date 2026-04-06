"""Unit tests for pure-logic functions in Logics kit modules.

Covers dispatcher validation, config parsing, mutations, transactions,
models (ref extraction, frontmatter), and decision support signal detection.
These are the highest-risk paths identified in item_241 / Wave 2 of req_129.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


def _load_module(name: str):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "logics-flow-manager"
        / "scripts"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"{name}_test", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(module_path.parent))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.pop(0)
    return module


# ---------------------------------------------------------------------------
# Dispatcher validation
# ---------------------------------------------------------------------------
class TestExtractJsonObject(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")

    def test_plain_json(self) -> None:
        result = self.mod.extract_json_object('{"action": "new"}')
        self.assertEqual(result, {"action": "new"})

    def test_markdown_fenced_json(self) -> None:
        text = '```json\n{"action": "sync"}\n```'
        result = self.mod.extract_json_object(text)
        self.assertEqual(result["action"], "sync")

    def test_json_embedded_in_prose(self) -> None:
        text = 'Here is my answer: {"action": "finish", "target_ref": "task_001_x"} done.'
        result = self.mod.extract_json_object(text)
        self.assertEqual(result["action"], "finish")

    def test_no_json_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.extract_json_object("no json here")
        self.assertEqual(ctx.exception.code, "dispatcher_invalid_json")

    def test_malformed_json_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod.extract_json_object("{broken: true}")

    def test_json_array_not_object_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod.extract_json_object("[1, 2, 3]")


class TestNormalizeConfidence(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")

    def test_valid_float(self) -> None:
        self.assertAlmostEqual(self.mod._normalize_confidence(0.85), 0.85)

    def test_percentage_conversion(self) -> None:
        self.assertAlmostEqual(self.mod._normalize_confidence(75), 0.75)

    def test_zero_is_valid(self) -> None:
        self.assertAlmostEqual(self.mod._normalize_confidence(0), 0.0)

    def test_one_is_valid(self) -> None:
        self.assertAlmostEqual(self.mod._normalize_confidence(1.0), 1.0)

    def test_out_of_range_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_confidence(150)

    def test_negative_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_confidence(-0.5)

    def test_boolean_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_confidence(True)

    def test_string_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_confidence("0.5")


class TestNormalizeTargetRef(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")

    def test_none_allowed_for_optional_action(self) -> None:
        self.assertIsNone(self.mod._normalize_target_ref(None, action="new"))

    def test_none_rejected_for_required_action(self) -> None:
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod._normalize_target_ref(None, action="promote")
        self.assertEqual(ctx.exception.code, "dispatcher_missing_target_ref")

    def test_empty_string_treated_as_missing_for_required(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_target_ref("  ", action="finish")

    def test_empty_string_becomes_none_for_optional(self) -> None:
        self.assertIsNone(self.mod._normalize_target_ref("  ", action="sync"))

    def test_valid_ref_preserved(self) -> None:
        self.assertEqual(
            self.mod._normalize_target_ref("req_001_kickoff", action="promote"),
            "req_001_kickoff",
        )

    def test_non_string_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_target_ref(42, action="promote")


class TestNormalizeTitles(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")

    def test_valid_titles(self) -> None:
        result = self.mod._normalize_titles(["First slice", "Second slice"])
        self.assertEqual(result, ["First slice", "Second slice"])

    def test_whitespace_normalized(self) -> None:
        result = self.mod._normalize_titles(["  lots   of  spaces  "])
        self.assertEqual(result, ["lots of spaces"])

    def test_empty_list_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_titles([])

    def test_not_a_list_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_titles("not a list")

    def test_duplicate_titles_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod._normalize_titles(["Same Title", "same title"])
        self.assertEqual(ctx.exception.code, "dispatcher_duplicate_titles")

    def test_empty_string_title_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_titles(["valid", ""])

    def test_non_string_item_rejected(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._normalize_titles(["valid", 42])


class TestValidateActionArgs(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")

    def test_new_requires_kind_and_title(self) -> None:
        result = self.mod._validate_action_args("new", {"kind": "request", "title": "Test"})
        self.assertEqual(result["kind"], "request")
        self.assertEqual(result["title"], "Test")

    def test_new_invalid_kind_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("new", {"kind": "invalid", "title": "Test"})

    def test_new_missing_title_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("new", {"kind": "request"})

    def test_new_strips_unknown_keys(self) -> None:
        result = self.mod._validate_action_args("new", {"kind": "task", "title": "T", "extra": "ignored"})
        self.assertNotIn("extra", result)

    def test_new_with_optional_slug(self) -> None:
        result = self.mod._validate_action_args("new", {"kind": "backlog", "title": "T", "slug": "my-slug"})
        self.assertEqual(result["slug"], "my-slug")

    def test_split_validates_titles(self) -> None:
        result = self.mod._validate_action_args("split", {"titles": ["A", "B"]})
        self.assertEqual(result["titles"], ["A", "B"])

    def test_sync_requires_valid_sync_kind(self) -> None:
        result = self.mod._validate_action_args("sync", {"sync_kind": "doctor"})
        self.assertEqual(result["sync_kind"], "doctor")

    def test_sync_invalid_sync_kind_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("sync", {"sync_kind": "nope"})

    def test_sync_optional_mode_and_profile(self) -> None:
        result = self.mod._validate_action_args("sync", {"sync_kind": "context-pack", "mode": "full", "profile": "deep"})
        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["profile"], "deep")

    def test_sync_invalid_mode_raises(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("sync", {"sync_kind": "doctor", "mode": "invalid"})

    def test_promote_rejects_args(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("promote", {"extra": True})

    def test_finish_rejects_args(self) -> None:
        with self.assertRaises(self.mod.DispatcherError):
            self.mod._validate_action_args("finish", {"extra": True})


class TestValidateDispatcherDecision(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")
        self.models = _load_module("logics_flow_models")
        self.docs_by_ref = {
            "req_001_kickoff": self.models.WorkflowDocModel(
                kind="request", path="logics/request/req_001_kickoff.md",
                ref="req_001_kickoff", title="Kickoff", indicators={},
                sections={}, refs={}, ai_context={}, schema_version="1.0",
            ),
            "task_001_impl": self.models.WorkflowDocModel(
                kind="task", path="logics/tasks/task_001_impl.md",
                ref="task_001_impl", title="Impl", indicators={},
                sections={}, refs={}, ai_context={}, schema_version="1.0",
            ),
        }

    def _valid_payload(self, **overrides: object) -> dict:
        base = {
            "action": "new",
            "target_ref": None,
            "proposed_args": {"kind": "request", "title": "Test"},
            "rationale": "Creating a new request for testing purposes.",
            "confidence": 0.9,
        }
        base.update(overrides)
        return base

    def test_valid_new_action(self) -> None:
        decision = self.mod.validate_dispatcher_decision(self._valid_payload(), self.docs_by_ref)
        self.assertEqual(decision.action, "new")
        self.assertAlmostEqual(decision.confidence, 0.9)

    def test_missing_field_raises(self) -> None:
        payload = self._valid_payload()
        del payload["rationale"]
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_missing_required_field")

    def test_unknown_field_raises(self) -> None:
        payload = self._valid_payload(extra_field="oops")
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_unknown_field")

    def test_invalid_action_raises(self) -> None:
        payload = self._valid_payload(action="delete")
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_invalid_action")

    def test_unknown_target_ref_raises(self) -> None:
        payload = self._valid_payload(action="promote", target_ref="req_999_unknown", proposed_args={})
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_unknown_target_ref")

    def test_promote_request_succeeds(self) -> None:
        payload = self._valid_payload(action="promote", target_ref="req_001_kickoff", proposed_args={})
        decision = self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(decision.action, "promote")
        self.assertEqual(decision.target_ref, "req_001_kickoff")

    def test_finish_non_task_raises(self) -> None:
        payload = self._valid_payload(action="finish", target_ref="req_001_kickoff", proposed_args={})
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_invalid_finish_target")

    def test_finish_task_succeeds(self) -> None:
        payload = self._valid_payload(action="finish", target_ref="task_001_impl", proposed_args={})
        decision = self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(decision.action, "finish")

    def test_empty_rationale_raises(self) -> None:
        payload = self._valid_payload(rationale="")
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_invalid_rationale")

    def test_long_rationale_raises(self) -> None:
        payload = self._valid_payload(rationale="x" * 501)
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_invalid_rationale")

    def test_sync_context_pack_requires_target_ref(self) -> None:
        payload = self._valid_payload(action="sync", target_ref=None, proposed_args={"sync_kind": "context-pack"})
        with self.assertRaises(self.mod.DispatcherError) as ctx:
            self.mod.validate_dispatcher_decision(payload, self.docs_by_ref)
        self.assertEqual(ctx.exception.code, "dispatcher_missing_target_ref")


class TestMapDecisionToCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_dispatcher")
        self.models = _load_module("logics_flow_models")
        self.docs_by_ref = {
            "req_001_kickoff": self.models.WorkflowDocModel(
                kind="request", path="logics/request/req_001_kickoff.md",
                ref="req_001_kickoff", title="Kickoff", indicators={},
                sections={}, refs={}, ai_context={}, schema_version="1.0",
            ),
            "item_001_slice": self.models.WorkflowDocModel(
                kind="backlog", path="logics/backlog/item_001_slice.md",
                ref="item_001_slice", title="Slice", indicators={},
                sections={}, refs={}, ai_context={}, schema_version="1.0",
            ),
        }

    def test_new_command(self) -> None:
        decision = self.mod.DispatcherDecision(
            action="new", target_ref=None,
            proposed_args={"kind": "request", "title": "My Request"},
            rationale="test", confidence=0.9,
        )
        cmd = self.mod.map_decision_to_command(decision, self.docs_by_ref)
        self.assertEqual(cmd["argv"], ["new", "request", "--title", "My Request"])
        self.assertTrue(cmd["mutates_workflow"])

    def test_promote_request_command(self) -> None:
        decision = self.mod.DispatcherDecision(
            action="promote", target_ref="req_001_kickoff",
            proposed_args={}, rationale="test", confidence=0.8,
        )
        cmd = self.mod.map_decision_to_command(decision, self.docs_by_ref)
        self.assertIn("request-to-backlog", cmd["argv"])
        self.assertTrue(cmd["mutates_workflow"])

    def test_sync_doctor_command(self) -> None:
        decision = self.mod.DispatcherDecision(
            action="sync", target_ref=None,
            proposed_args={"sync_kind": "doctor"}, rationale="test", confidence=0.7,
        )
        cmd = self.mod.map_decision_to_command(decision, self.docs_by_ref)
        self.assertEqual(cmd["argv"], ["sync", "doctor"])
        self.assertFalse(cmd["mutates_workflow"])

    def test_split_command_includes_titles(self) -> None:
        decision = self.mod.DispatcherDecision(
            action="split", target_ref="req_001_kickoff",
            proposed_args={"titles": ["Slice A", "Slice B"]}, rationale="test", confidence=0.8,
        )
        cmd = self.mod.map_decision_to_command(decision, self.docs_by_ref)
        self.assertIn("--title", cmd["argv"])
        self.assertIn("Slice A", cmd["argv"])
        self.assertIn("Slice B", cmd["argv"])


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------
class TestCoerceScalar(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_config")

    def test_null_variants(self) -> None:
        for val in ("null", "Null", "NULL", "~", ""):
            self.assertIsNone(self.mod._coerce_scalar(val), f"Failed for {val!r}")

    def test_booleans(self) -> None:
        self.assertIs(self.mod._coerce_scalar("true"), True)
        self.assertIs(self.mod._coerce_scalar("True"), True)
        self.assertIs(self.mod._coerce_scalar("false"), False)
        self.assertIs(self.mod._coerce_scalar("False"), False)

    def test_integers(self) -> None:
        self.assertEqual(self.mod._coerce_scalar("42"), 42)
        self.assertEqual(self.mod._coerce_scalar("-1"), -1)

    def test_floats(self) -> None:
        self.assertAlmostEqual(self.mod._coerce_scalar("3.14"), 3.14)

    def test_quoted_string(self) -> None:
        self.assertEqual(self.mod._coerce_scalar('"hello"'), "hello")
        self.assertEqual(self.mod._coerce_scalar("'world'"), "world")

    def test_plain_string(self) -> None:
        self.assertEqual(self.mod._coerce_scalar("some-text"), "some-text")

    def test_inline_comment_stripped(self) -> None:
        self.assertEqual(self.mod._coerce_scalar("42 # the answer"), 42)


class TestParseSimpleYaml(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_config")

    def test_empty_string(self) -> None:
        self.assertEqual(self.mod.parse_simple_yaml(""), {})

    def test_flat_mapping(self) -> None:
        text = "key1: value1\nkey2: 42\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], 42)

    def test_nested_mapping(self) -> None:
        text = "parent:\n  child: nested\n  number: 10\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertEqual(result["parent"]["child"], "nested")
        self.assertEqual(result["parent"]["number"], 10)

    def test_list_values(self) -> None:
        text = "items:\n  - alpha\n  - beta\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertEqual(result["items"], ["alpha", "beta"])

    def test_comments_and_blanks_skipped(self) -> None:
        text = "# comment\n\nkey: value\n\n# another comment\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertEqual(result, {"key": "value"})

    def test_boolean_and_null_values(self) -> None:
        text = "enabled: true\ndisabled: false\nnothing: null\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertIs(result["enabled"], True)
        self.assertIs(result["disabled"], False)
        self.assertIsNone(result["nothing"])

    def test_deeply_nested(self) -> None:
        text = "a:\n  b:\n    c: deep\n"
        result = self.mod.parse_simple_yaml(text)
        self.assertEqual(result["a"]["b"]["c"], "deep")


class TestDeepMerge(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_config")

    def test_override_scalar(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = self.mod._deep_merge(base, override)
        self.assertEqual(result, {"a": 1, "b": 3})

    def test_nested_merge(self) -> None:
        base = {"x": {"y": 1, "z": 2}}
        override = {"x": {"z": 3}}
        result = self.mod._deep_merge(base, override)
        self.assertEqual(result["x"]["y"], 1)
        self.assertEqual(result["x"]["z"], 3)

    def test_new_keys_added(self) -> None:
        result = self.mod._deep_merge({"a": 1}, {"b": 2})
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_base_not_mutated(self) -> None:
        base = {"a": {"b": 1}}
        self.mod._deep_merge(base, {"a": {"b": 2}})
        self.assertEqual(base["a"]["b"], 1)


class TestLoadRepoConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_config")

    def test_missing_file_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, path = self.mod.load_repo_config(Path(tmp))
            self.assertIsNone(path)
            self.assertIn("workflow", config)

    def test_override_merges_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "logics.yaml").write_text("workflow:\n  split:\n    max_children_without_override: 8\n", encoding="utf-8")
            config, path = self.mod.load_repo_config(repo)
            self.assertIsNotNone(path)
            self.assertEqual(config["workflow"]["split"]["max_children_without_override"], 8)
            # default key still present
            self.assertEqual(config["workflow"]["split"]["policy"], "minimal-coherent")


class TestGetConfigValue(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_config")

    def test_nested_path(self) -> None:
        config = {"a": {"b": {"c": 42}}}
        self.assertEqual(self.mod.get_config_value(config, "a", "b", "c"), 42)

    def test_missing_path_returns_default(self) -> None:
        config = {"a": 1}
        self.assertEqual(self.mod.get_config_value(config, "x", "y", default="fallback"), "fallback")


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
class TestBuildPlannedMutation(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_mutations")

    def test_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            p = repo / "logics" / "request" / "new.md"
            mutation = self.mod.build_planned_mutation(
                p, before=None, after="# New\n", reason="create", repo_root=repo,
            )
            self.assertFalse(mutation.before_exists)
            self.assertTrue(mutation.changed)
            self.assertIn("logics/request/new.md", mutation.path)
            self.assertTrue(len(mutation.diff) > 0)

    def test_unchanged_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            p = repo / "test.md"
            mutation = self.mod.build_planned_mutation(
                p, before="same", after="same", reason="noop", repo_root=repo,
            )
            self.assertTrue(mutation.before_exists)
            self.assertFalse(mutation.changed)
            self.assertEqual(mutation.diff, [])

    def test_to_dict_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            p = repo / "f.md"
            mutation = self.mod.build_planned_mutation(
                p, before="a", after="b", reason="edit", repo_root=repo,
            )
            d = mutation.to_dict()
            json.dumps(d)  # must be JSON-serializable


class TestApplyMutation(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_mutations")

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "output.md"
            self.mod.apply_mutation(p, content="hello", dry_run=True)
            self.assertFalse(p.exists())

    def test_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sub" / "output.md"
            self.mod.apply_mutation(p, content="hello", dry_run=False)
            self.assertEqual(p.read_text(encoding="utf-8"), "hello")


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class TestApplyTransaction(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_transactions")

    def test_dry_run_records_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            audit = "audit.jsonl"
            target = repo / "doc.md"
            write = self.mod.TransactionWrite(path=target, content="hello", reason="test")
            result = self.mod.apply_transaction(
                repo, writes=[write], mode="transactional",
                audit_log=audit, dry_run=True, command_name="test",
            )
            self.assertFalse(target.exists())
            self.assertFalse(result.rolled_back)
            audit_content = (repo / audit).read_text(encoding="utf-8")
            self.assertIn('"preview"', audit_content)

    def test_successful_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            target = repo / "doc.md"
            write = self.mod.TransactionWrite(path=target, content="data", reason="create")
            result = self.mod.apply_transaction(
                repo, writes=[write], mode="transactional",
                audit_log="audit.jsonl", dry_run=False, command_name="test",
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "data")
            self.assertFalse(result.rolled_back)
            self.assertEqual(result.applied_files, ["doc.md"])

    def test_transactional_rollback_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            target = repo / "doc.md"
            target.write_text("original", encoding="utf-8")
            write = self.mod.TransactionWrite(path=target, content="modified", reason="update")
            env_backup = os.environ.get("LOGICS_MUTATION_FAIL_AFTER_WRITES")
            os.environ["LOGICS_MUTATION_FAIL_AFTER_WRITES"] = "1"
            try:
                with self.assertRaises(self.mod.TransactionError):
                    self.mod.apply_transaction(
                        repo, writes=[write], mode="transactional",
                        audit_log="audit.jsonl", dry_run=False, command_name="test",
                    )
            finally:
                if env_backup is None:
                    os.environ.pop("LOGICS_MUTATION_FAIL_AFTER_WRITES", None)
                else:
                    os.environ["LOGICS_MUTATION_FAIL_AFTER_WRITES"] = env_backup
            # file should be rolled back to original content
            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_direct_mode_does_not_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            target = repo / "doc.md"
            target.write_text("original", encoding="utf-8")
            write = self.mod.TransactionWrite(path=target, content="modified", reason="update")
            env_backup = os.environ.get("LOGICS_MUTATION_FAIL_AFTER_WRITES")
            os.environ["LOGICS_MUTATION_FAIL_AFTER_WRITES"] = "1"
            try:
                with self.assertRaises(self.mod.TransactionError):
                    self.mod.apply_transaction(
                        repo, writes=[write], mode="direct",
                        audit_log="audit.jsonl", dry_run=False, command_name="test",
                    )
            finally:
                if env_backup is None:
                    os.environ.pop("LOGICS_MUTATION_FAIL_AFTER_WRITES", None)
                else:
                    os.environ["LOGICS_MUTATION_FAIL_AFTER_WRITES"] = env_backup
            # file should keep modified content (no rollback in direct mode)
            self.assertEqual(target.read_text(encoding="utf-8"), "modified")

    def test_unknown_mode_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            target = repo / "doc.md"
            write = self.mod.TransactionWrite(path=target, content="x", reason="test")
            with self.assertRaises(self.mod.TransactionError):
                self.mod.apply_transaction(
                    repo, writes=[write], mode="bad_mode",
                    audit_log="audit.jsonl", dry_run=False, command_name="test",
                )

    def test_empty_writes_records_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            result = self.mod.apply_transaction(
                repo, writes=[], mode="transactional",
                audit_log="audit.jsonl", dry_run=False, command_name="noop",
            )
            self.assertEqual(result.applied_files, [])
            self.assertFalse(result.rolled_back)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class TestExtractRefs(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_models")

    def test_finds_refs_in_text(self) -> None:
        text = "Links: req_001_kickoff and item_002_test and task_003_impl."
        refs = self.mod._extract_refs(text)
        self.assertIn("req_001_kickoff", refs["req"])
        self.assertIn("item_002_test", refs["item"])
        self.assertIn("task_003_impl", refs["task"])

    def test_excludes_mermaid_blocks(self) -> None:
        text = (
            "Some text with req_001_real.\n"
            "```mermaid\n"
            "flowchart LR\n"
            "    A[req_002_mermaid_only]\n"
            "```\n"
            "After mermaid."
        )
        refs = self.mod._extract_refs(text)
        self.assertIn("req_001_real", refs["req"])
        self.assertNotIn("req_002_mermaid_only", refs["req"])

    def test_deduplicates_refs(self) -> None:
        text = "ref req_001_x and again req_001_x."
        refs = self.mod._extract_refs(text)
        self.assertEqual(refs["req"].count("req_001_x"), 1)


class TestParseFrontmatter(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_models")

    def test_valid_frontmatter(self) -> None:
        text = "---\nname: test-skill\ndescription: A test skill\n---\nBody content"
        fm, issues = self.mod._parse_frontmatter(text)
        self.assertEqual(fm["name"], "test-skill")
        self.assertEqual(fm["description"], "A test skill")
        self.assertEqual(issues, [])

    def test_missing_start_marker(self) -> None:
        text = "name: test\n---\nBody"
        fm, issues = self.mod._parse_frontmatter(text)
        self.assertEqual(fm, {})
        self.assertIn("missing frontmatter start marker", issues[0])

    def test_unterminated_block(self) -> None:
        text = "---\nname: test\nno end marker"
        fm, issues = self.mod._parse_frontmatter(text)
        self.assertEqual(fm, {})
        self.assertIn("unterminated", issues[0])

    def test_block_scalar_folded(self) -> None:
        text = "---\ndescription: >\n  This is a\n  folded description\n---\nBody"
        fm, issues = self.mod._parse_frontmatter(text)
        self.assertEqual(fm["description"], "This is a folded description")

    def test_block_scalar_literal(self) -> None:
        text = "---\ndescription: |\n  Line one\n  Line two\n---\nBody"
        fm, issues = self.mod._parse_frontmatter(text)
        self.assertIn("Line one", fm["description"])
        self.assertIn("Line two", fm["description"])


class TestDetectWorkflowKind(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_models")

    def test_request(self) -> None:
        self.assertEqual(self.mod._detect_workflow_kind(Path("logics/request/req_001_x.md")), "request")

    def test_backlog(self) -> None:
        self.assertEqual(self.mod._detect_workflow_kind(Path("logics/backlog/item_001_x.md")), "backlog")

    def test_task(self) -> None:
        self.assertEqual(self.mod._detect_workflow_kind(Path("logics/tasks/task_001_x.md")), "task")

    def test_unknown(self) -> None:
        self.assertEqual(self.mod._detect_workflow_kind(Path("random/path.md")), "unknown")


class TestExtractIndicators(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_models")

    def test_parses_indicators(self) -> None:
        text = "> Status: In Progress\n> Progress: 50%\n> Confidence: 80%\n"
        indicators = self.mod._extract_indicators(text)
        self.assertEqual(indicators["Status"], "In Progress")
        self.assertEqual(indicators["Progress"], "50%")

    def test_ignores_non_indicator_lines(self) -> None:
        text = "# Title\nSome text\n> Status: Done\n"
        indicators = self.mod._extract_indicators(text)
        self.assertEqual(len(indicators), 1)
        self.assertEqual(indicators["Status"], "Done")


class TestExtractTitle(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_models")

    def test_standard_format(self) -> None:
        text = "## req_001_kickoff - My Request Title\n"
        self.assertEqual(self.mod._extract_title(text, "fallback"), "My Request Title")

    def test_fallback_when_no_heading(self) -> None:
        text = "No heading here.\n"
        self.assertEqual(self.mod._extract_title(text, "my_fallback"), "my_fallback")


# ---------------------------------------------------------------------------
# Decision support
# ---------------------------------------------------------------------------
class TestDecisionSupport(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module("logics_flow_decision_support")

    def test_no_signals_detected(self) -> None:
        assessment = self.mod._assess_decision_framing("Simple refactor", "Move code around.")
        self.assertEqual(assessment.product_level, "Not needed")
        self.assertEqual(assessment.architecture_level, "Not needed")
        self.assertEqual(assessment.product_signals, ())
        self.assertEqual(assessment.architecture_signals, ())

    def test_product_signals_in_title(self) -> None:
        assessment = self.mod._assess_decision_framing("Redesign the signup onboarding flow", "")
        self.assertEqual(assessment.product_level, "Required")
        self.assertIn("conversion journey", assessment.product_signals)

    def test_architecture_signals_in_body(self) -> None:
        assessment = self.mod._assess_decision_framing(
            "Update data layer", "We need a new database schema and migration strategy."
        )
        # signal is in body only (not title), so level is "Consider" with one signal
        self.assertEqual(assessment.architecture_level, "Consider")
        self.assertIn("data model and persistence", assessment.architecture_signals)

    def test_consider_level_with_single_body_signal(self) -> None:
        assessment = self.mod._assess_decision_framing("Improve settings", "Add a settings page.")
        # "settings" triggers experience scope signal in body only
        self.assertIn(assessment.product_level, ("Consider", "Required"))

    def test_multiple_architecture_signals(self) -> None:
        assessment = self.mod._assess_decision_framing(
            "Infrastructure", "Add api contract and authentication module."
        )
        self.assertIn("contracts and integration", assessment.architecture_signals)
        self.assertIn("security and identity", assessment.architecture_signals)

    def test_decision_follow_up_required(self) -> None:
        result = self.mod._decision_follow_up("Required", "product")
        self.assertIn("product brief", result)

    def test_decision_follow_up_not_needed(self) -> None:
        result = self.mod._decision_follow_up("Not needed", "architecture")
        self.assertIn("No architecture decision", result)

    def test_signals_display_empty(self) -> None:
        self.assertEqual(self.mod._signals_display(()), "(none detected)")

    def test_signals_display_values(self) -> None:
        self.assertEqual(self.mod._signals_display(("a", "b")), "a, b")


if __name__ == "__main__":
    unittest.main()
