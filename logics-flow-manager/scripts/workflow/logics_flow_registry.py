#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


CURRENT_WORKFLOW_SCHEMA_VERSION = "1.0"

WORKFLOW_CONVENTIONS = {
    "statuses": ["Draft", "Ready", "In progress", "Blocked", "Done", "Archived"],
    "complexities": ["Low", "Medium", "High"],
    "doc_prefixes": {
        "request": "req",
        "backlog": "item",
        "task": "task",
        "product": "prod",
        "architecture": "adr",
    },
    "workflow_sections": {
        "request": ["Needs", "Context", "Acceptance criteria", "Definition of Ready (DoR)", "Companion docs", "AI Context", "Backlog"],
        "backlog": ["Problem", "Scope", "Acceptance criteria", "AC Traceability", "Decision framing", "Links", "AI Context", "Priority", "Notes"],
        "task": ["Context", "Plan", "Delivery checkpoints", "AC Traceability", "Decision framing", "Links", "AI Context", "Validation", "Definition of Done (DoD)", "Report"],
    },
}


GOVERNANCE_PROFILES = {
    "relaxed": {
        "stale_days": 0,
        "require_gates": False,
        "require_ac_traceability": False,
        "token_hygiene": False,
    },
    "standard": {
        "stale_days": 45,
        "require_gates": True,
        "require_ac_traceability": True,
        "token_hygiene": False,
    },
    "strict": {
        "stale_days": 30,
        "require_gates": True,
        "require_ac_traceability": True,
        "token_hygiene": True,
    },
}


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    path: str
    change_count: int


def normalize_semver_filename(path: Path) -> str | None:
    match = re.match(r"^CHANGELOGS_(\d+)_(\d+)_(\d+)\.md$", path.name)
    if match is None:
        return None
    return ".".join(match.groups())


def build_release_metadata(skills_root: Path) -> list[ReleaseMetadata]:
    changelog_dir = skills_root / "changelogs"
    releases: list[ReleaseMetadata] = []
    if not changelog_dir.is_dir():
        return releases

    for path in sorted(changelog_dir.glob("CHANGELOGS_*.md")):
        version = normalize_semver_filename(path)
        if version is None:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        change_count = sum(1 for line in lines if line.strip().startswith("- "))
        releases.append(
            ReleaseMetadata(
                version=version,
                path=path.relative_to(skills_root).as_posix(),
                change_count=change_count,
            )
        )
    return releases


def build_capability_flags(*, has_agents: bool, has_scripts: bool, has_assets: bool, has_tests: bool) -> dict[str, bool]:
    return {
        "agents": has_agents,
        "scripts": has_scripts,
        "assets": has_assets,
        "tests": has_tests,
        "machine_readable": has_scripts or has_agents,
        "validated": has_tests,
    }
