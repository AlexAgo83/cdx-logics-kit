#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _render_api import (
    RenderApiError,
    extract_service_plan,
    find_repo_root,
    get_service,
    list_services,
    now_iso_utc,
    plan_schema_for_service_type,
    read_plan_enums_from_openapi,
    render_api_base_url,
    render_openapi_url,
    update_service_plan,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path}")


def _format_markdown_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Render deployment plan snapshot",
        f"- Generated at: {snapshot.get('generatedAt', '')}",
        f"- API base URL: {snapshot.get('source', {}).get('apiBaseUrl', '')}",
        f"- OpenAPI source: {snapshot.get('source', {}).get('openApiUrl', '')}",
        "",
        "| Service ID | Name | Type | Current plan | Target plan | Suspended |",
        "|---|---|---|---|---|---|",
    ]
    services = snapshot.get("services", [])
    if isinstance(services, list):
        for service in services:
            if not isinstance(service, dict):
                continue
            lines.append(
                f"| {service.get('serviceId', '')} | {service.get('name', '')} | {service.get('type', '')} | "
                f"{service.get('currentPlan', '-') or '-'} | {service.get('targetPlan', '-') or '-'} | {service.get('suspended', '')} |"
            )
    lines.append("")
    return "\n".join(lines)


def _build_snapshot(
    *,
    limit: int,
    owner_ids: list[str] | None,
    include_previews: bool
) -> dict[str, Any]:
    services = list_services(limit=limit, owner_ids=owner_ids, include_previews=include_previews)
    services = sorted(services, key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")))

    items: list[dict[str, Any]] = []
    for service in services:
        service_id = str(service.get("id") or "")
        service_name = str(service.get("name") or "")
        service_type = str(service.get("type") or "")
        dashboard_url = str(service.get("dashboardUrl") or "")
        suspended = str(service.get("suspended") or "")
        current_plan = extract_service_plan(service)

        items.append(
            {
                "serviceId": service_id,
                "name": service_name,
                "type": service_type,
                "dashboardUrl": dashboard_url,
                "suspended": suspended,
                "currentPlan": current_plan,
                "targetPlan": current_plan,
                "notes": "",
            }
        )

    return {
        "schemaVersion": 1,
        "generatedAt": now_iso_utc(),
        "source": {
            "apiBaseUrl": render_api_base_url(),
            "openApiUrl": render_openapi_url(),
            "includePreviews": include_previews,
            "ownerIds": owner_ids or [],
        },
        "services": items,
    }


def _load_plan_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Plan file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Plan file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Plan file root must be an object.")
    services = payload.get("services")
    if not isinstance(services, list):
        raise SystemExit("Plan file must include a 'services' array.")
    return payload


def _normalize_service_entries(payload: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for index, raw in enumerate(payload.get("services", [])):
        if not isinstance(raw, dict):
            raise SystemExit(f"services[{index}] must be an object.")
        service_id = str(raw.get("serviceId") or "").strip()
        target_plan = str(raw.get("targetPlan") or "").strip()
        if not service_id:
            raise SystemExit(f"services[{index}].serviceId is required.")
        if not target_plan:
            continue
        entries.append({"serviceId": service_id, "targetPlan": target_plan})
    return entries


def _supported_plans_for_service(service: dict[str, Any], plan_enums: dict[str, list[str]]) -> list[str]:
    service_type = str(service.get("type") or "")
    schema_name = plan_schema_for_service_type(service_type)
    return plan_enums.get(schema_name) or []


def _cmd_show_plans() -> int:
    plan_enums = read_plan_enums_from_openapi()
    lines = [f"# Render plan enums", f"OpenAPI: {render_openapi_url()}", ""]
    for key in ("plan", "paidPlan", "keyValuePlan", "redisPlan", "postgresPlan"):
        values = plan_enums.get(key, [])
        lines.append(f"- {key}: {', '.join(values) if values else '(none)'}")
    print("\n".join(lines))
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")
    snapshot = _build_snapshot(
        limit=args.limit,
        owner_ids=args.owner_id if args.owner_id else None,
        include_previews=args.include_previews == "yes",
    )
    out_json = Path(args.out)
    _write_json(out_json, snapshot)
    if args.markdown_out:
        _write_text(Path(args.markdown_out), _format_markdown_snapshot(snapshot))
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    payload = _load_plan_file(Path(args.plan_file))
    entries = _normalize_service_entries(payload)
    if not entries:
        print("No target plan changes found in plan file.")
        return 0

    plan_enums = read_plan_enums_from_openapi()
    updated = 0
    unchanged = 0
    skipped = 0
    failed = 0

    for entry in entries:
        service_id = entry["serviceId"]
        target_plan = entry["targetPlan"]
        try:
            service = get_service(service_id)
            current_plan = extract_service_plan(service)
            if current_plan is None:
                print(f"[skip] {service_id}: service has no plan field.")
                skipped += 1
                continue

            allowed = _supported_plans_for_service(service, plan_enums)
            if allowed and target_plan not in allowed:
                print(f"[skip] {service_id}: target plan '{target_plan}' is not allowed (allowed: {', '.join(allowed)}).")
                skipped += 1
                continue

            if current_plan == target_plan:
                print(f"[ok]   {service_id}: unchanged ({current_plan}).")
                unchanged += 1
                continue

            if args.validate_only or args.dry_run:
                marker = "validate" if args.validate_only else "dry-run"
                print(f"[{marker}] {service_id}: {current_plan} -> {target_plan}")
                updated += 1
                continue

            patched = update_service_plan(service_id, target_plan)
            patched_plan = extract_service_plan(patched) or "?"
            print(f"[done] {service_id}: {current_plan} -> {patched_plan}")
            updated += 1
        except RenderApiError as exc:
            print(f"[fail] {service_id}: {exc}")
            failed += 1

    print("")
    print(f"Summary: updated={updated} unchanged={unchanged} skipped={skipped} failed={failed}")
    if failed > 0:
        return 1
    return 0


def main(argv: list[str]) -> int:
    find_repo_root(Path.cwd())

    parser = argparse.ArgumentParser(description="Render deployment plan manager (snapshot / show-plans / apply).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_plans = subparsers.add_parser("show-plans", help="Show supported plan enums from Render OpenAPI.")
    show_plans.set_defaults(func=lambda args: _cmd_show_plans())

    snapshot = subparsers.add_parser("snapshot", help="Create a deployment plan snapshot JSON from current services.")
    snapshot.add_argument("--out", default="logics/external/render/render_deployment_plan.snapshot.json")
    snapshot.add_argument("--markdown-out", help="Optional Markdown summary output path.")
    snapshot.add_argument("--limit", type=int, default=200)
    snapshot.add_argument("--owner-id", action="append", default=[], help="Optional ownerId filter (repeatable).")
    snapshot.add_argument("--include-previews", choices=("yes", "no"), default="yes")
    snapshot.set_defaults(func=_cmd_snapshot)

    apply = subparsers.add_parser("apply", help="Apply plan file target plans to Render services.")
    apply.add_argument("--plan-file", required=True, help="Path to a deployment plan JSON file.")
    apply.add_argument("--validate-only", action="store_true", help="Validate and report changes without applying.")
    apply.add_argument("--dry-run", action="store_true", help="Alias for no-write preview mode.")
    apply.set_defaults(func=_cmd_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
