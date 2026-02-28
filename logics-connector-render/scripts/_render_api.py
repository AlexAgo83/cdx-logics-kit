#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RENDER_API_BASE_URL = "https://api.render.com/v1"
DEFAULT_RENDER_OPENAPI_URL = "https://api-docs.render.com/openapi/render-public-api-1.json"


class RenderApiError(RuntimeError):
    pass


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    raise SystemExit("Could not locate repo root (missing 'logics/' directory). Run from inside the repo.")


def render_api_base_url() -> str:
    return os.environ.get("RENDER_API_BASE_URL", DEFAULT_RENDER_API_BASE_URL).rstrip("/")


def render_openapi_url() -> str:
    return os.environ.get("RENDER_OPENAPI_URL", DEFAULT_RENDER_OPENAPI_URL).strip()


def render_api_key() -> str:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing RENDER_API_KEY (Render API key).")
    return key


def _stringify_query_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _extract_error_message(payload: object) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return "Render API request failed"


def render_request(
    method: str,
    path: str,
    *,
    query: dict[str, object | list[object]] | None = None,
    body: dict[str, object] | None = None,
    timeout: int = 30
) -> Any:
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")

    params: list[tuple[str, str]] = []
    if query:
        for key, value in query.items():
            if isinstance(value, list):
                for item in value:
                    params.append((key, _stringify_query_value(item)))
            elif value is not None:
                params.append((key, _stringify_query_value(value)))
    query_string = urllib.parse.urlencode(params, doseq=True)
    url = f"{render_api_base_url()}{path}"
    if query_string:
        url = f"{url}?{query_string}"

    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method.upper())
    req.add_header("Authorization", f"Bearer {render_api_key()}")
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed: object
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        message = _extract_error_message(parsed)
        raise RenderApiError(f"{exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RenderApiError(f"Unable to reach Render API: {exc.reason}") from exc


def _paginate_cursor_list(
    path: str,
    *,
    item_key: str | None,
    limit: int,
    base_query: dict[str, object | list[object]] | None = None
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    results: list[dict[str, Any]] = []
    cursor: str | None = None

    while len(results) < limit:
        page_limit = min(100, limit - len(results))
        query: dict[str, object | list[object]] = {"limit": page_limit}
        if base_query:
            query.update(base_query)
        if cursor:
            query["cursor"] = cursor

        page = render_request("GET", path, query=query)
        if not isinstance(page, list) or len(page) == 0:
            break

        for row in page:
            if not isinstance(row, dict):
                continue
            if item_key and isinstance(row.get(item_key), dict):
                results.append(row[item_key])
            else:
                results.append(row)
            if len(results) >= limit:
                break

        last = page[-1] if isinstance(page[-1], dict) else None
        next_cursor = last.get("cursor") if isinstance(last, dict) else None
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return results


def list_services(
    *,
    limit: int,
    owner_ids: list[str] | None = None,
    include_previews: bool = True
) -> list[dict[str, Any]]:
    base_query: dict[str, object | list[object]] = {"includePreviews": include_previews}
    if owner_ids:
        base_query["ownerId"] = owner_ids
    return _paginate_cursor_list("/services", item_key="service", limit=limit, base_query=base_query)


def get_service(service_id: str) -> dict[str, Any]:
    payload = render_request("GET", f"/services/{service_id}")
    if not isinstance(payload, dict):
        raise RenderApiError(f"Unexpected service payload for {service_id}")
    return payload


def list_deploys(
    service_id: str,
    *,
    limit: int,
    statuses: list[str] | None = None
) -> list[dict[str, Any]]:
    base_query: dict[str, object | list[object]] = {}
    if statuses:
        base_query["status"] = statuses
    return _paginate_cursor_list(
        f"/services/{service_id}/deploys",
        item_key="deploy",
        limit=limit,
        base_query=base_query if base_query else None
    )


def list_blueprints(*, limit: int, owner_ids: list[str] | None = None) -> list[dict[str, Any]]:
    base_query: dict[str, object | list[object]] = {}
    if owner_ids:
        base_query["ownerId"] = owner_ids
    return _paginate_cursor_list("/blueprints", item_key="blueprint", limit=limit, base_query=base_query if base_query else None)


def extract_service_plan(service: dict[str, Any]) -> str | None:
    details = service.get("serviceDetails")
    if not isinstance(details, dict):
        return None
    plan = details.get("plan")
    if isinstance(plan, str) and plan.strip():
        return plan
    return None


def extract_service_runtime(service: dict[str, Any]) -> str | None:
    details = service.get("serviceDetails")
    if not isinstance(details, dict):
        return None
    runtime = details.get("runtime")
    if isinstance(runtime, str) and runtime.strip():
        return runtime
    return None


def update_service_plan(service_id: str, target_plan: str) -> dict[str, Any]:
    payload = render_request("PATCH", f"/services/{service_id}", body={"serviceDetails": {"plan": target_plan}})
    if not isinstance(payload, dict):
        raise RenderApiError(f"Unexpected patch payload for {service_id}")
    return payload


def read_plan_enums_from_openapi() -> dict[str, list[str]]:
    req = urllib.request.Request(render_openapi_url(), method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RenderApiError(f"Unable to reach Render OpenAPI spec: {exc.reason}") from exc

    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RenderApiError("Render OpenAPI response is not valid JSON.") from exc

    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    postgres = schemas.get("postgres") or {}
    postgres_plan_enum = (
        (((postgres.get("properties") or {}).get("plan") or {}).get("enum")) or []
    )

    plans: dict[str, list[str]] = {
        "plan": list((schemas.get("plan") or {}).get("enum") or []),
        "paidPlan": list((schemas.get("paidPlan") or {}).get("enum") or []),
        "keyValuePlan": list((schemas.get("keyValuePlan") or {}).get("enum") or []),
        "redisPlan": list((schemas.get("redisPlan") or {}).get("enum") or []),
        "postgresPlan": list(postgres_plan_enum),
    }
    return plans


def plan_schema_for_service_type(service_type: str) -> str:
    if service_type == "web_service":
        return "plan"
    if service_type in {"private_service", "background_worker", "cron_job"}:
        return "paidPlan"
    # For unknown future types, keep a permissive baseline.
    return "plan"
