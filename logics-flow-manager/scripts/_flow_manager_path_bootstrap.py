from __future__ import annotations

import sys
from pathlib import Path


def ensure_flow_manager_paths() -> None:
    scripts_root = Path(__file__).resolve().parent
    for subdir in ("workflow", "hybrid", "transport", "audit"):
        path = scripts_root / subdir
        if path.is_dir():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

