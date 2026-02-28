#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _render_api import find_repo_root, get_service, list_deploys


def _write_out(path: str | None, text: str) -> None:
    if not path or path == "-":
        print(text, end="")
        return
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")


def _fmt_commit(deploy: dict[str, object]) -> str:
    commit = deploy.get("commit")
    if not isinstance(commit, dict):
        return "-"
    commit_id = str(commit.get("id") or "")
    message = str(commit.get("message") or "").strip().replace("\n", " ")
    if message:
        return f"{commit_id} {message}"
    return commit_id or "-"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="List deploys for a Render service.")
    parser.add_argument("--service-id", required=True, help="Render service ID.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of deploys to list.")
    parser.add_argument(
        "--status",
        action="append",
        default=[],
        help="Deploy status filter (repeatable, e.g. build_failed, live, update_failed).",
    )
    parser.add_argument("--out", help="Write output to file (omit or '-' for stdout).")
    args = parser.parse_args(argv)

    find_repo_root(Path.cwd())

    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")

    service = get_service(args.service_id)
    deploys = list_deploys(
        args.service_id,
        limit=args.limit,
        statuses=args.status if args.status else None,
    )

    service_name = str(service.get("name") or args.service_id)
    lines = [f"# Render deploys – {service_name}", f"Service: {args.service_id}", f"Total: {len(deploys)}", ""]
    for deploy in deploys:
        deploy_id = str(deploy.get("id") or "")
        status = str(deploy.get("status") or "")
        trigger = str(deploy.get("trigger") or "")
        created_at = str(deploy.get("createdAt") or "")
        updated_at = str(deploy.get("updatedAt") or "")
        commit_summary = _fmt_commit(deploy)
        lines.append(
            f"- {deploy_id} [{status}] trigger={trigger} created={created_at} updated={updated_at} commit={commit_summary}"
        )

    _write_out(args.out, "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
