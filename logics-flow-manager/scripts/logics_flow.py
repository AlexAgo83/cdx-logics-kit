#!/usr/bin/env python3
from __future__ import annotations

import sys

from logics_flow_cli_commands import *  # noqa: F401,F403

if __name__ == "__main__":
    from logics_flow_cli_commands import main as cli_main

    raise SystemExit(cli_main(sys.argv[1:]))
