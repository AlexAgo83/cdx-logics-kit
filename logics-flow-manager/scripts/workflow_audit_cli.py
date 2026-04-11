from __future__ import annotations

from pathlib import Path

_source_path = Path(__file__).resolve().parent / 'audit/workflow_audit_cli.py'
__file__ = str(_source_path)
exec(compile(_source_path.read_text(encoding="utf-8"), str(_source_path), "exec"), globals())
