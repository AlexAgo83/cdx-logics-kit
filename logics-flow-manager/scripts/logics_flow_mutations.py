from __future__ import annotations

from pathlib import Path

_source_path = Path(__file__).resolve().parent / 'workflow/logics_flow_mutations.py'
__file__ = str(_source_path)
exec(compile(_source_path.read_text(encoding="utf-8"), str(_source_path), "exec"), globals())
