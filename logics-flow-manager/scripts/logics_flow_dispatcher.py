#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from logics_flow_models import WorkflowDocModel


DISPATCH_SCHEMA_VERSION = "1.0"
DEFAULT_DISPATCH_AUDIT_LOG = "logics/dispatcher_audit.jsonl"
DEFAULT_DISPATCH_CONTEXT_MODE = "summary-only"
DEFAULT_DISPATCH_PROFILE = "normal"
DEFAULT_DISPATCH_EXECUTION_MODE = "suggestion-only"

ALLOWED_DISPATCH_ACTIONS = ("new", "promote", "split", "finish", "sync")
SAFE_SYNC_KINDS = (
    "benchmark-skills",
    "context-pack",
    "doctor",
    "export-graph",
    "export-registry",
    "schema-status",
    "validate-skills",
)
KNOWN_ACTION_ARGUMENTS = {
    "new": {"kind", "title", "slug"},
    "promote": set(),
    "split": {"titles"},
    "finish": set(),
    "sync": {"mode", "profile", "sync_kind"},
}
TARGET_REQUIRED_ACTIONS = {"promote", "split", "finish"}
TARGET_OPTIONAL_ACTIONS = {"new", "sync"}


class DispatcherError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class DispatcherDecision:
    action: str
    target_ref: str | None
    proposed_args: dict[str, Any]
    rationale: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_ref": self.target_ref,
            "proposed_args": self.proposed_args,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


def build_dispatcher_contract() -> dict[str, Any]:
    return {
        "schema_version": DISPATCH_SCHEMA_VERSION,
        "default_execution_mode": DEFAULT_DISPATCH_EXECUTION_MODE,
        "allowed_actions": list(ALLOWED_DISPATCH_ACTIONS),
        "safe_sync_kinds": list(SAFE_SYNC_KINDS),
        "decision_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "target_ref", "proposed_args", "rationale", "confidence"],
            "properties": {
                "action": {"type": "string", "enum": list(ALLOWED_DISPATCH_ACTIONS)},
                "target_ref": {"type": ["string", "null"]},
                "proposed_args": {"type": "object", "additionalProperties": False},
                "rationale": {"type": "string", "minLength": 1, "maxLength": 500},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
    }


def build_dispatcher_messages(context_bundle: dict[str, Any]) -> list[dict[str, str]]:
    contract = context_bundle["contract"]
    system = (
        "You are a deterministic local dispatcher for the Logics workflow. "
        "Choose exactly one next action and reply with one JSON object only. "
        "Do not wrap the JSON in markdown fences. "
        "Use only the allowed actions and sync kinds supplied in the context. "
        "Prefer conservative decisions that keep workflow mutations bounded. "
        "If a write action is not clearly justified, prefer a safe `sync` action."
    )
    user = (
        "Return a JSON object with keys "
        "`action`, `target_ref`, `proposed_args`, `rationale`, and `confidence`.\n\n"
        f"Dispatcher contract:\n{json.dumps(contract, indent=2, sort_keys=True)}\n\n"
        f"Workflow context:\n{json.dumps(context_bundle, indent=2, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise DispatcherError("dispatcher_invalid_json", "Model output did not contain a JSON object.")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DispatcherError("dispatcher_invalid_json", f"Could not parse dispatcher JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DispatcherError("dispatcher_invalid_json", "Dispatcher output must decode to a JSON object.")
    return payload


def _normalize_confidence(raw_value: Any) -> float:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise DispatcherError("dispatcher_invalid_confidence", "Dispatcher confidence must be a numeric value.")
    value = float(raw_value)
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    if value < 0.0 or value > 1.0:
        raise DispatcherError("dispatcher_invalid_confidence", "Dispatcher confidence must be between 0.0 and 1.0.")
    return round(value, 4)


def _normalize_target_ref(raw_value: Any, *, action: str) -> str | None:
    if raw_value is None:
        if action in TARGET_REQUIRED_ACTIONS:
            raise DispatcherError("dispatcher_missing_target_ref", f"`target_ref` is required for action `{action}`.")
        return None
    if not isinstance(raw_value, str):
        raise DispatcherError("dispatcher_invalid_target_ref", "`target_ref` must be a string or null.")
    value = raw_value.strip()
    if not value:
        if action in TARGET_REQUIRED_ACTIONS:
            raise DispatcherError("dispatcher_missing_target_ref", f"`target_ref` is required for action `{action}`.")
        return None
    return value


def _normalize_titles(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list) or not raw_value:
        raise DispatcherError("dispatcher_invalid_titles", "`proposed_args.titles` must be a non-empty array.")
    titles: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        if not isinstance(item, str) or not item.strip():
            raise DispatcherError("dispatcher_invalid_titles", "`proposed_args.titles` must contain only non-empty strings.")
        title = " ".join(item.split())
        normalized = title.lower()
        if normalized in seen:
            raise DispatcherError("dispatcher_duplicate_titles", "`proposed_args.titles` must not contain duplicates.")
        seen.add(normalized)
        titles.append(title)
    return titles


def _validate_action_args(action: str, proposed_args: dict[str, Any]) -> dict[str, Any]:
    allowed = KNOWN_ACTION_ARGUMENTS[action]
    if action == "new":
        proposed_args = {key: value for key, value in proposed_args.items() if key in allowed}

    unknown = sorted(set(proposed_args) - allowed)
    if unknown:
        raise DispatcherError(
            "dispatcher_unknown_proposed_arg",
            f"Unknown proposed_args for action `{action}`: {', '.join(unknown)}.",
            details={"unknown_keys": unknown},
        )

    if action == "new":
        kind = proposed_args.get("kind")
        title = proposed_args.get("title")
        if kind not in {"request", "backlog", "task"}:
            raise DispatcherError("dispatcher_invalid_new_kind", "`new` requires `proposed_args.kind` in {request, backlog, task}.")
        if not isinstance(title, str) or not title.strip():
            raise DispatcherError("dispatcher_invalid_new_title", "`new` requires a non-empty `proposed_args.title`.")
        normalized = {"kind": kind, "title": " ".join(title.split())}
        slug = proposed_args.get("slug")
        if slug is not None:
            if not isinstance(slug, str) or not slug.strip():
                raise DispatcherError("dispatcher_invalid_slug", "`proposed_args.slug` must be a non-empty string when provided.")
            normalized["slug"] = slug.strip()
        return normalized

    if action == "split":
        return {"titles": _normalize_titles(proposed_args.get("titles"))}

    if action == "sync":
        sync_kind = proposed_args.get("sync_kind")
        if sync_kind not in SAFE_SYNC_KINDS:
            raise DispatcherError(
                "dispatcher_invalid_sync_kind",
                f"`sync` requires `proposed_args.sync_kind` in {{{', '.join(SAFE_SYNC_KINDS)}}}.",
            )
        normalized = {"sync_kind": sync_kind}
        mode = proposed_args.get("mode")
        if mode is not None:
            if mode not in {"summary-only", "diff-first", "full"}:
                raise DispatcherError("dispatcher_invalid_context_mode", "`proposed_args.mode` must be one of summary-only, diff-first, full.")
            normalized["mode"] = mode
        profile = proposed_args.get("profile")
        if profile is not None:
            if profile not in {"tiny", "normal", "deep"}:
                raise DispatcherError("dispatcher_invalid_context_profile", "`proposed_args.profile` must be one of tiny, normal, deep.")
            normalized["profile"] = profile
        return normalized

    if proposed_args:
        raise DispatcherError(
            "dispatcher_unexpected_args",
            f"Action `{action}` does not accept proposed_args, but values were provided.",
        )
    return {}


def validate_dispatcher_decision(raw_payload: dict[str, Any], docs_by_ref: dict[str, WorkflowDocModel]) -> DispatcherDecision:
    required = {"action", "target_ref", "proposed_args", "rationale", "confidence"}
    unknown = sorted(set(raw_payload) - required)
    missing = sorted(required - set(raw_payload))
    if missing:
        raise DispatcherError(
            "dispatcher_missing_required_field",
            f"Dispatcher payload is missing required field(s): {', '.join(missing)}.",
            details={"missing_fields": missing},
        )
    if unknown:
        raise DispatcherError(
            "dispatcher_unknown_field",
            f"Dispatcher payload contains unknown field(s): {', '.join(unknown)}.",
            details={"unknown_fields": unknown},
        )

    action = raw_payload["action"]
    if not isinstance(action, str) or action not in ALLOWED_DISPATCH_ACTIONS:
        raise DispatcherError(
            "dispatcher_invalid_action",
            f"`action` must be one of {', '.join(ALLOWED_DISPATCH_ACTIONS)}.",
        )

    target_ref = _normalize_target_ref(raw_payload["target_ref"], action=action)
    if target_ref is not None and target_ref not in docs_by_ref and action != "new":
        raise DispatcherError(
            "dispatcher_unknown_target_ref",
            f"`target_ref` `{target_ref}` does not resolve to a known workflow doc.",
        )

    proposed_args = raw_payload["proposed_args"]
    if not isinstance(proposed_args, dict):
        raise DispatcherError("dispatcher_invalid_proposed_args", "`proposed_args` must be a JSON object.")
    normalized_args = _validate_action_args(action, proposed_args)

    rationale = raw_payload["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise DispatcherError("dispatcher_invalid_rationale", "`rationale` must be a non-empty string.")
    rationale = " ".join(rationale.split())
    if len(rationale) > 500:
        raise DispatcherError("dispatcher_invalid_rationale", "`rationale` must stay under 500 characters.")

    confidence = _normalize_confidence(raw_payload["confidence"])

    if target_ref is not None:
        target_doc = docs_by_ref[target_ref]
        if action == "promote" and target_doc.kind not in {"request", "backlog"}:
            raise DispatcherError("dispatcher_invalid_promote_target", "`promote` only supports request or backlog targets.")
        if action == "split" and target_doc.kind not in {"request", "backlog"}:
            raise DispatcherError("dispatcher_invalid_split_target", "`split` only supports request or backlog targets.")
        if action == "finish" and target_doc.kind != "task":
            raise DispatcherError("dispatcher_invalid_finish_target", "`finish` only supports task targets.")
        if action == "sync":
            sync_kind = normalized_args["sync_kind"]
            if sync_kind == "context-pack" and target_doc.kind not in {"request", "backlog", "task"}:
                raise DispatcherError("dispatcher_invalid_context_pack_target", "`sync context-pack` requires a workflow target ref.")

    if action == "sync" and normalized_args["sync_kind"] == "context-pack" and target_ref is None:
        raise DispatcherError("dispatcher_missing_target_ref", "`sync context-pack` requires `target_ref`.")

    return DispatcherDecision(
        action=action,
        target_ref=target_ref,
        proposed_args=normalized_args,
        rationale=rationale,
        confidence=confidence,
    )


def map_decision_to_command(decision: DispatcherDecision, docs_by_ref: dict[str, WorkflowDocModel]) -> dict[str, Any]:
    argv: list[str]
    target_kind = None
    target_path = None
    mutates_workflow = decision.action != "sync"

    if decision.target_ref is not None and decision.target_ref in docs_by_ref:
        target_doc = docs_by_ref[decision.target_ref]
        target_kind = target_doc.kind
        target_path = target_doc.path

    if decision.action == "new":
        argv = ["new", decision.proposed_args["kind"], "--title", decision.proposed_args["title"]]
        if "slug" in decision.proposed_args:
            argv.extend(["--slug", decision.proposed_args["slug"]])
        summary = f"Create a new {decision.proposed_args['kind']} doc titled `{decision.proposed_args['title']}`."
    elif decision.action == "promote":
        if target_kind == "request":
            argv = ["promote", "request-to-backlog", target_path]
        else:
            argv = ["promote", "backlog-to-task", target_path]
        summary = f"Promote `{decision.target_ref}` from {target_kind} to the next workflow stage."
    elif decision.action == "split":
        split_kind = "request" if target_kind == "request" else "backlog"
        argv = ["split", split_kind, target_path]
        for title in decision.proposed_args["titles"]:
            argv.extend(["--title", title])
        summary = f"Split `{decision.target_ref}` into {len(decision.proposed_args['titles'])} child slice(s)."
    elif decision.action == "finish":
        argv = ["finish", "task", target_path]
        summary = f"Finish task `{decision.target_ref}` and propagate guarded closure."
    else:
        sync_kind = decision.proposed_args["sync_kind"]
        argv = ["sync", sync_kind]
        mutates_workflow = False
        if sync_kind == "context-pack":
            argv.append(decision.target_ref or "")
            argv.extend(["--mode", decision.proposed_args.get("mode", DEFAULT_DISPATCH_CONTEXT_MODE)])
            argv.extend(["--profile", decision.proposed_args.get("profile", DEFAULT_DISPATCH_PROFILE)])
        summary = f"Run non-destructive sync `{sync_kind}`."

    return {
        "argv": argv,
        "summary": summary,
        "target_kind": target_kind,
        "target_path": target_path,
        "mutates_workflow": mutates_workflow,
        "requires_explicit_execution": True,
    }


def run_ollama_dispatch(
    *,
    host: str,
    model: str,
    context_bundle: dict[str, Any],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    normalized_host = host.strip() or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if not normalized_host.startswith(("http://", "https://")):
        normalized_host = f"http://{normalized_host}"
    normalized_host = normalized_host.rstrip("/")

    messages = build_dispatcher_messages(context_bundle)
    request_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    encoded = json.dumps(request_payload).encode("utf-8")
    req = urllib_request.Request(
        f"{normalized_host}/api/chat",
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DispatcherError(
            "dispatcher_ollama_http_error",
            f"Ollama returned HTTP {exc.code}: {body or exc.reason}",
            details={"host": normalized_host, "model": model},
        ) from exc
    except urllib_error.URLError as exc:
        raise DispatcherError(
            "dispatcher_ollama_unreachable",
            f"Could not reach Ollama at {normalized_host}: {exc.reason}",
            details={"host": normalized_host, "model": model},
        ) from exc

    content = ""
    if isinstance(response_payload, dict):
        message = response_payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
    if not content:
        raise DispatcherError(
            "dispatcher_ollama_empty_response",
            "Ollama returned an empty dispatcher response.",
            details={"host": normalized_host, "model": model},
        )
    return {
        "transport": "ollama",
        "host": normalized_host,
        "model": model,
        "messages": messages,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "raw_content": content,
        "decision_payload": extract_json_object(content),
    }


def append_audit_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def build_audit_record(
    *,
    seed_ref: str,
    execution_mode: str,
    context_bundle: dict[str, Any],
    decision_payload: dict[str, Any],
    validated_decision: DispatcherDecision,
    mapped_command: dict[str, Any],
    execution_result: dict[str, Any] | None,
    transport: dict[str, Any],
) -> dict[str, Any]:
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": DISPATCH_SCHEMA_VERSION,
        "seed_ref": seed_ref,
        "execution_mode": execution_mode,
        "context_summary": {
            "profile": context_bundle["context_pack"]["profile"],
            "mode": context_bundle["context_pack"]["mode"],
            "doc_count": context_bundle["context_pack"]["estimates"]["doc_count"],
            "included_sections": sorted(key for key in context_bundle.keys() if key not in {"contract"}),
        },
        "transport": transport,
        "raw_model_output": decision_payload,
        "validated_decision": validated_decision.to_dict(),
        "mapped_command": mapped_command,
        "execution_result": execution_result,
    }
