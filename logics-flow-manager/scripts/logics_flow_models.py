#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from logics_flow_registry import CURRENT_WORKFLOW_SCHEMA_VERSION, build_capability_flags


REF_PREFIXES = ("req", "item", "task", "prod", "adr", "spec")
WORKFLOW_DOC_KINDS = {
    "request": ("logics/request", "req"),
    "backlog": ("logics/backlog", "item"),
    "task": ("logics/tasks", "task"),
}


@dataclass(frozen=True)
class WorkflowDocModel:
    kind: str
    path: str
    ref: str
    title: str
    indicators: dict[str, str]
    sections: dict[str, list[str]]
    refs: dict[str, list[str]]
    ai_context: dict[str, str]
    schema_version: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SkillPackageModel:
    name: str
    path: str
    description: str
    frontmatter: dict[str, str]
    interface: dict[str, str]
    capability_flags: dict[str, bool]
    issues: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _extract_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("# "):
            current = line[2:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _extract_indicators(text: str) -> dict[str, str]:
    indicators: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*>\s*([^:]+)\s*:\s*(.+?)\s*$", line)
        if match is None:
            continue
        indicators[match.group(1).strip()] = match.group(2).strip()
    return indicators


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if not line.startswith("## "):
            continue
        match = re.match(r"^##\s+\S+\s*-\s*(.+?)\s*$", line)
        if match is not None:
            return match.group(1).strip()
        return line.removeprefix("## ").strip()
    return fallback


def _extract_refs(text: str) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {prefix: [] for prefix in REF_PREFIXES}
    stripped = re.sub(r"```mermaid\s*\n.*?\n```", "", text, flags=re.DOTALL)
    for prefix in REF_PREFIXES:
        pattern = re.compile(rf"\b{re.escape(prefix)}_\d{{3}}_[a-z0-9_]+\b")
        seen: set[str] = set()
        for match in pattern.finditer(stripped):
            value = match.group(0)
            if value in seen:
                continue
            seen.add(value)
            refs[prefix].append(value)
    return refs


def _extract_ai_context(sections: dict[str, list[str]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in sections.get("AI Context", []):
        match = re.match(r"^\s*-\s*([^:]+)\s*:\s*(.+?)\s*$", line.strip())
        if match is None:
            continue
        fields[match.group(1).strip().lower()] = match.group(2).strip()
    return fields


def parse_workflow_doc(path: Path, *, repo_root: Path | None = None) -> WorkflowDocModel:
    text = path.read_text(encoding="utf-8")
    sections = _extract_sections(text)
    indicators = _extract_indicators(text)
    return WorkflowDocModel(
        kind=_detect_workflow_kind(path),
        path=(path.relative_to(repo_root).as_posix() if repo_root is not None else path.as_posix()),
        ref=path.stem,
        title=_extract_title(text, path.stem),
        indicators=indicators,
        sections=sections,
        refs=_extract_refs(text),
        ai_context=_extract_ai_context(sections),
        schema_version=indicators.get("Schema version", CURRENT_WORKFLOW_SCHEMA_VERSION),
    )


def _detect_workflow_kind(path: Path) -> str:
    normalized = path.as_posix()
    for kind, (directory, _prefix) in WORKFLOW_DOC_KINDS.items():
        if f"/{directory}/" in f"/{normalized}":
            return kind
    return "unknown"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    issues: list[str] = []
    if not text.startswith("---\n"):
        return {}, ["missing frontmatter start marker"]
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, ["unterminated frontmatter block"]
    frontmatter = text[4:end].splitlines()
    parsed: dict[str, str] = {}
    block_key: str | None = None
    block_style: str | None = None
    block_lines: list[str] = []

    def flush_block() -> None:
        nonlocal block_key, block_style, block_lines
        if block_key is None:
            return
        if block_style and block_style.startswith(">"):
            parsed[block_key] = " ".join(line.strip() for line in block_lines if line.strip()).strip()
        else:
            parsed[block_key] = "\n".join(line.rstrip() for line in block_lines).strip()
        block_key = None
        block_style = None
        block_lines = []

    for line in frontmatter:
        if not line.strip():
            if block_key is not None:
                block_lines.append("")
            continue
        if block_key is not None:
            if line[:1].isspace():
                block_lines.append(line.lstrip())
                continue
            flush_block()
        if ":" not in line:
            issues.append(f"frontmatter line missing ':' -> {line.strip()}")
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip()
        normalized_value = value.strip()
        if normalized_key == "description" and normalized_value.startswith("[") and not normalized_value.startswith("\"["):
            issues.append("description must be a string scalar, not a YAML sequence-like literal")
        if normalized_key == "description" and ": " in normalized_value and not normalized_value.startswith(("\"", "'")):
            issues.append("description contains an unquoted colon and is likely invalid YAML")
        if normalized_value in {">", ">-", "|", "|-"}:
            block_key = normalized_key
            block_style = normalized_value
            block_lines = []
            continue
        if normalized_key == "description" and ": " in normalized_value and normalized_value.startswith(("\"", "'")):
            issues.append("description should prefer a YAML block scalar when it contains a colon for Codex CLI compatibility")
        parsed[normalized_key] = normalized_value.strip("\"'")
    flush_block()
    return parsed, issues


def _parse_openai_interface(path: Path) -> tuple[dict[str, str], list[str]]:
    if not path.is_file():
        return {}, ["missing agents/openai.yaml"]
    interface: dict[str, str] = {}
    issues: list[str] = []
    in_interface = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith("interface:"):
            in_interface = True
            continue
        if not in_interface:
            continue
        if not raw_line.startswith("  "):
            break
        line = raw_line.strip()
        if ":" not in line:
            issues.append(f"invalid interface line in {path.name}: {line}")
            continue
        key, value = line.split(":", 1)
        interface[key.strip()] = value.strip().strip("\"'")
    if not interface:
        issues.append("agents/openai.yaml is missing the interface mapping")
    return interface, issues


def parse_skill_package(skill_dir: Path, *, repo_root: Path | None = None) -> SkillPackageModel:
    skill_path = skill_dir / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8") if skill_path.is_file() else ""
    frontmatter, issues = _parse_frontmatter(text) if text else ({}, ["missing SKILL.md"])
    interface, interface_issues = _parse_openai_interface(skill_dir / "agents" / "openai.yaml")
    issues.extend(interface_issues)

    scripts_dir = skill_dir / "scripts"
    assets_dir = skill_dir / "assets"
    tests_dir = skill_dir / "tests"
    agents_dir = skill_dir / "agents"
    capability_flags = build_capability_flags(
        has_agents=agents_dir.is_dir() and any(agents_dir.glob("*.y*ml")),
        has_scripts=scripts_dir.is_dir() and any(scripts_dir.glob("*.py")),
        has_assets=assets_dir.exists(),
        has_tests=tests_dir.exists(),
    )

    name = frontmatter.get("name") or skill_dir.name
    description = frontmatter.get("description", "")
    if not description:
        issues.append("frontmatter is missing a non-empty description")
    if not name:
        issues.append("frontmatter is missing a name")

    return SkillPackageModel(
        name=name,
        path=(skill_dir.relative_to(repo_root).as_posix() if repo_root is not None else skill_dir.as_posix()),
        description=description,
        frontmatter=frontmatter,
        interface=interface,
        capability_flags=capability_flags,
        issues=issues,
    )


def iter_skill_packages(skills_root: Path, *, repo_root: Path | None = None) -> list[SkillPackageModel]:
    packages: list[SkillPackageModel] = []
    if not skills_root.is_dir():
        return packages
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        if not (skill_dir / "SKILL.md").is_file() and not (skill_dir / "agents" / "openai.yaml").is_file():
            continue
        packages.append(parse_skill_package(skill_dir, repo_root=repo_root))
    return packages
