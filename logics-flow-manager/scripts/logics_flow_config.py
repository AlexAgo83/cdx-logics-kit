#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_LOGICS_CONFIG: dict[str, Any] = {
    "version": 1,
    "workflow": {
        "split": {
            "policy": "minimal-coherent",
            "max_children_without_override": 2,
        }
    },
    "mutations": {
        "mode": "transactional",
        "audit_log": "logics/mutation_audit.jsonl",
    },
    "index": {
        "enabled": True,
        "path": "logics/.cache/runtime_index.json",
    },
}


class ConfigError(SystemExit):
    pass


def _strip_comment(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith(('"', "'")) and "#" in stripped:
        stripped = stripped.split("#", 1)[0].rstrip()
    return stripped


def _coerce_scalar(value: str) -> Any:
    stripped = _strip_comment(value)
    if stripped in {"", "null", "Null", "NULL", "~"}:
        return None
    if stripped in {"true", "True"}:
        return True
    if stripped in {"false", "False"}:
        return False
    if stripped.startswith(("'", '"')) and stripped.endswith(("'", '"')) and len(stripped) >= 2:
        return stripped[1:-1]
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return stripped


def _prepared_lines(text: str) -> list[tuple[int, str]]:
    prepared: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        stripped = raw.lstrip(" ")
        if stripped.startswith("#"):
            continue
        indent = len(raw) - len(stripped)
        prepared.append((indent, stripped.rstrip()))
    return prepared


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent < indent:
        return {}, index

    if content.startswith("- "):
        items: list[Any] = []
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("- "):
                raise ConfigError(f"Invalid list indentation in logics.yaml near `{content}`.")
            item_content = content[2:].strip()
            index += 1
            if not item_content:
                if index < len(lines) and lines[index][0] > indent:
                    nested_indent = lines[index][0]
                    value, index = _parse_block(lines, index, nested_indent)
                else:
                    value = None
            elif ":" in item_content and not item_content.startswith(("'", '"')) and not item_content.endswith(":"):
                key, raw_value = item_content.split(":", 1)
                value = {key.strip(): _coerce_scalar(raw_value.strip())}
            elif item_content.endswith(":") and not item_content.startswith(("'", '"')):
                key = item_content[:-1].strip()
                if index < len(lines) and lines[index][0] > indent:
                    nested_indent = lines[index][0]
                    nested_value, index = _parse_block(lines, index, nested_indent)
                else:
                    nested_value = {}
                value = {key: nested_value}
            else:
                value = _coerce_scalar(item_content)
            items.append(value)
        return items, index

    mapping: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent:
            raise ConfigError(f"Invalid mapping indentation in logics.yaml near `{content}`.")
        if ":" not in content:
            raise ConfigError(f"Expected `key: value` in logics.yaml, got `{content}`.")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            mapping[key] = _coerce_scalar(raw_value)
            continue
        if index < len(lines) and lines[index][0] > current_indent:
            nested_indent = lines[index][0]
            value, index = _parse_block(lines, index, nested_indent)
        else:
            value = {}
        mapping[key] = value
    return mapping, index


def parse_simple_yaml(text: str) -> dict[str, Any]:
    lines = _prepared_lines(text)
    if not lines:
        return {}
    parsed, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ConfigError("Could not parse the full logics.yaml payload.")
    if not isinstance(parsed, dict):
        raise ConfigError("logics.yaml must decode to a top-level mapping.")
    return parsed


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def config_path(repo_root: Path) -> Path:
    return repo_root / "logics.yaml"


def load_repo_config(repo_root: Path) -> tuple[dict[str, Any], Path | None]:
    path = config_path(repo_root)
    if not path.is_file():
        return deepcopy(DEFAULT_LOGICS_CONFIG), None
    try:
        override = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"Failed to parse {path.relative_to(repo_root)}: {exc}") from exc
    return _deep_merge(DEFAULT_LOGICS_CONFIG, override), path


def get_config_value(config: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = config
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return default
        current = current[segment]
    return current

