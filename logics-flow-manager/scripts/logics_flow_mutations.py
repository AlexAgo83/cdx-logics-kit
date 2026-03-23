#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
import difflib
from pathlib import Path


@dataclass(frozen=True)
class PlannedMutation:
    path: str
    reason: str
    before_exists: bool
    changed: bool
    diff: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_planned_mutation(path: Path, *, before: str | None, after: str, reason: str, repo_root: Path | None = None) -> PlannedMutation:
    before_text = before or ""
    before_lines = before_text.splitlines()
    after_lines = after.splitlines()
    rel_path = path.relative_to(repo_root).as_posix() if repo_root is not None else path.as_posix()
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    return PlannedMutation(
        path=rel_path,
        reason=reason,
        before_exists=before is not None,
        changed=before_text != after,
        diff=diff,
    )


def apply_mutation(path: Path, *, content: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
