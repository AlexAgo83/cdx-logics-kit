#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from logics_codex_workspace_support import (
    all_registered_statuses,
    clean_workspace,
    doctor_workspace,
    ensure_command_payload,
    fail_if_windows_junction_requested_on_non_windows,
    print_payload,
    register_workspace,
    resolve_repo_root,
    run_workspace_command,
    status_for_repo,
    sync_workspace,
)


def cmd_register(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo)
    fail_if_windows_junction_requested_on_non_windows(args.publication_mode)
    payload = register_workspace(repo_root, sync_now=not args.no_sync, publication_mode=args.publication_mode)
    print_payload(payload, as_json=args.json)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo)
    fail_if_windows_junction_requested_on_non_windows(args.publication_mode)
    payload = sync_workspace(repo_root, publication_mode=args.publication_mode)
    print_payload(payload, as_json=args.json)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if args.all:
        payload = all_registered_statuses()
    else:
        repo_root = resolve_repo_root(args.repo)
        payload = status_for_repo(repo_root)
    print_payload(payload, as_json=args.json)
    if args.fail_on_issues:
        if isinstance(payload, list):
            return 1 if any(entry.get("issues") for entry in payload) else 0
        return 1 if payload.get("issues") else 0
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo)
    fail_if_windows_junction_requested_on_non_windows(args.publication_mode)
    payload = doctor_workspace(repo_root, fix=args.fix, publication_mode=args.publication_mode)
    print_payload(payload, as_json=args.json)
    return 1 if payload.get("issues") and args.fail_on_issues else 0


def cmd_run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo)
    fail_if_windows_junction_requested_on_non_windows(args.publication_mode)
    command = ensure_command_payload(args.command)
    return run_workspace_command(
        repo_root,
        command,
        publication_mode=args.publication_mode,
        sync_before_run=not args.no_sync,
        print_only=args.print_only,
    )


def cmd_clean(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo)
    payload = clean_workspace(repo_root)
    print_payload(payload, as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logics_codex_workspace.py",
        description="Manage legacy per-repository Codex workspace overlays for Logics skills.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_repo_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--repo", help="Repository path. Defaults to the current working directory.")
        target.add_argument("--json", action="store_true", help="Emit JSON instead of operator text.")

    def add_publication_arg(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--publication-mode",
            choices=("auto", "symlink", "junction", "copy"),
            default="auto",
            help="How overlay assets should be materialized.",
        )

    register_parser = sub.add_parser("register", help="Register a repository as a managed legacy Codex workspace overlay.")
    add_common_repo_args(register_parser)
    add_publication_arg(register_parser)
    register_parser.add_argument("--no-sync", action="store_true", help="Register without materializing the overlay immediately.")
    register_parser.set_defaults(func=cmd_register)

    sync_parser = sub.add_parser("sync", help="Materialize or refresh the legacy workspace overlay from repo-local skills.")
    add_common_repo_args(sync_parser)
    add_publication_arg(sync_parser)
    sync_parser.set_defaults(func=cmd_sync)

    status_parser = sub.add_parser("status", help="Inspect legacy overlay status for one repo or for all registered workspaces.")
    add_common_repo_args(status_parser)
    status_parser.add_argument("--all", action="store_true", help="Inspect all registered workspaces instead of the current repo.")
    status_parser.add_argument("--fail-on-issues", action="store_true", help="Exit non-zero when issues are present.")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = sub.add_parser("doctor", help="Diagnose legacy overlay health and optionally rebuild deterministic failures.")
    add_common_repo_args(doctor_parser)
    add_publication_arg(doctor_parser)
    doctor_parser.add_argument("--fix", action="store_true", help="Rebuild the overlay when deterministic repair is possible.")
    doctor_parser.add_argument("--fail-on-issues", action="store_true", help="Exit non-zero when issues remain.")
    doctor_parser.set_defaults(func=cmd_doctor)

    run_parser = sub.add_parser("run", help="Launch a command against the legacy workspace-specific CODEX_HOME.")
    add_common_repo_args(run_parser)
    add_publication_arg(run_parser)
    run_parser.add_argument("--no-sync", action="store_true", help="Skip the pre-run sync step.")
    run_parser.add_argument("--print-only", action="store_true", help="Print the resolved CODEX_HOME and command instead of running it.")
    run_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run. Defaults to `codex`.")
    run_parser.set_defaults(func=cmd_run)

    clean_parser = sub.add_parser("clean", help="Remove the legacy overlay and registry entry for the current repo.")
    add_common_repo_args(clean_parser)
    clean_parser.set_defaults(func=cmd_clean)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
