#!/usr/bin/env python3
from __future__ import annotations

import sys

from logics_flow_hybrid_runtime_impl import *  # noqa: F401,F403

if __name__ == "__main__":
    from logics_flow_hybrid_runtime_impl import main as runtime_main

    raise SystemExit(runtime_main(sys.argv[1:]))
