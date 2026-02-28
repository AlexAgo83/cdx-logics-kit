#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _render_api import (
    extract_service_plan,
    extract_service_runtime,
    find_repo_root,
    list_services,
)


def _write_out(path: str | None, text: str) -> None:
    if not path or path == "-":
        print(text, end="")
        return
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="List Render services.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of services to list.")
    parser.add_argument("--owner-id", action="append", default=[], help="Optional ownerId filter (repeatable).")
    parser.add_argument(
        "--include-previews",
        choices=("yes", "no"),
        default="yes",
        help="Include preview services (default: yes)."
    )
    parser.add_argument("--out", help="Write output to file (omit or '-' for stdout).")
    args = parser.parse_args(argv)

    find_repo_root(Path.cwd())

    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    services = list_services(
        limit=args.limit,
        owner_ids=args.owner_id if args.owner_id else None,
        include_previews=args.include_previews == "yes",
    )
    services = sorted(services, key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")))

    lines = [f"# Render services", f"Total: {len(services)}", ""]
    for service in services:
        service_id = service.get("id", "")
        name = service.get("name", "")
        service_type = service.get("type", "")
        dashboard_url = service.get("dashboardUrl", "")
        suspended = service.get("suspended", "")
        runtime = extract_service_runtime(service) or "-"
        plan = extract_service_plan(service) or "-"
        lines.append(
            f"- {service_id} [{service_type}] {name} | runtime={runtime} | plan={plan} | suspended={suspended} | {dashboard_url}"
        )

    _write_out(args.out, "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
