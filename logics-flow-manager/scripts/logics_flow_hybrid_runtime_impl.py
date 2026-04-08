#!/usr/bin/env python3
from __future__ import annotations

from logics_flow_hybrid_runtime_core import *  # noqa: F401,F403
from logics_flow_hybrid_runtime_metrics import *  # noqa: F401,F403
from logics_flow_hybrid_runtime_fallbacks import *  # noqa: F401,F403


def main(argv: list[str]) -> int:
    from logics_flow import main as flow_main

    return flow_main(argv)
