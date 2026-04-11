from __future__ import annotations

import sys

from _compat_export import export_module

export_module("audit.workflow_audit", globals())

if __name__ == "__main__":
    raise SystemExit(globals()["main"](sys.argv[1:]))
