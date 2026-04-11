from __future__ import annotations

from pathlib import Path

_source_path = Path(__file__).resolve().parent / 'hybrid/logics_flow_hybrid_runtime_fallbacks.py'
__file__ = str(_source_path)
exec(compile(_source_path.read_text(encoding="utf-8"), str(_source_path), "exec"), globals())
