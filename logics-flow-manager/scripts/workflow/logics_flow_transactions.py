#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class TransactionWrite:
    path: Path
    content: str
    reason: str

    def to_dict(self, repo_root: Path) -> dict[str, str]:
        payload = asdict(self)
        payload["path"] = self.path.relative_to(repo_root).as_posix()
        return payload


@dataclass(frozen=True)
class AppliedTransaction:
    mode: str
    applied_files: list[str]
    rolled_back: bool
    audit_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TransactionError(RuntimeError):
    pass


def _failure_threshold() -> int | None:
    raw = os.environ.get("LOGICS_MUTATION_FAIL_AFTER_WRITES", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise TransactionError("LOGICS_MUTATION_FAIL_AFTER_WRITES must be an integer.") from exc
    return value if value > 0 else None


def _append_audit_record(audit_path: Path, record: dict[str, object]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def apply_transaction(
    repo_root: Path,
    *,
    writes: list[TransactionWrite],
    mode: str,
    audit_log: str,
    dry_run: bool,
    command_name: str,
) -> AppliedTransaction:
    audit_path = (repo_root / audit_log).resolve()
    planned_files = [write.path.relative_to(repo_root).as_posix() for write in writes]
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command_name,
        "mode": mode,
        "planned_files": planned_files,
        "write_count": len(writes),
        "rolled_back": False,
        "status": "preview" if dry_run else "pending",
    }
    if dry_run or not writes:
        _append_audit_record(audit_path, record)
        return AppliedTransaction(mode=mode, applied_files=planned_files, rolled_back=False, audit_path=audit_path.relative_to(repo_root).as_posix())

    if mode not in {"direct", "transactional"}:
        raise TransactionError(f"Unknown mutation mode `{mode}`.")

    fail_after = _failure_threshold()
    backups: list[tuple[Path, str | None]] = []
    applied: list[str] = []

    try:
        for index, write in enumerate(writes, start=1):
            before = write.path.read_text(encoding="utf-8") if write.path.exists() else None
            backups.append((write.path, before))
            write.path.parent.mkdir(parents=True, exist_ok=True)
            write.path.write_text(write.content, encoding="utf-8")
            applied.append(write.path.relative_to(repo_root).as_posix())
            if fail_after is not None and index >= fail_after:
                raise TransactionError(f"Simulated transaction failure after {index} write(s).")
    except Exception as exc:
        if mode == "transactional":
            for path, before in reversed(backups):
                if before is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(before, encoding="utf-8")
            record["rolled_back"] = True
            record["status"] = "rolled_back"
            record["error"] = str(exc)
            record["applied_files"] = applied
            _append_audit_record(audit_path, record)
        else:
            record["status"] = "failed"
            record["error"] = str(exc)
            record["applied_files"] = applied
            _append_audit_record(audit_path, record)
        raise

    record["status"] = "applied"
    record["applied_files"] = applied
    _append_audit_record(audit_path, record)
    return AppliedTransaction(mode=mode, applied_files=applied, rolled_back=False, audit_path=audit_path.relative_to(repo_root).as_posix())

