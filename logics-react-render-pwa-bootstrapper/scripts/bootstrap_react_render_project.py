#!/usr/bin/env python3
"""Bootstrap a React + Render + PWA project scaffold."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bootstrap_react_render_base_assets import *  # noqa: F401,F403
from bootstrap_react_render_qa_assets import *  # noqa: F401,F403

def main_files(skill_root: Path, profile: str, pwa_mode: str, project_name: str, app_title: str) -> dict[str, str]:
    frontend_service_name = project_name
    backend_service_name = f"{project_name}-backend"
    database_name = normalize_kebab(f"{project_name}-db")

    render_template_name = "render.static.yaml" if profile == "frontend-static-pwa" else "render.fullstack.yaml"
    render_template = read_asset(skill_root, render_template_name)

    icon_svg = read_asset(skill_root, "icon.svg")

    files: dict[str, str] = {
        ".nvmrc": "20\n",
        ".gitignore": gitignore(),
        ".env.example": root_env_example(profile),
        "package.json": package_json(profile, pwa_mode, project_name),
        "tsconfig.json": tsconfig(),
        "vite.config.ts": vite_config_plugin(app_title) if pwa_mode == "plugin" else vite_config_custom(),
        "eslint.config.js": eslint_config(),
        "playwright.config.ts": playwright_config(),
        "index.html": apply_tokens(index_html(), {"APP_TITLE": app_title}),
        "README.md": readme(profile, pwa_mode, app_title),
        "render.yaml": apply_tokens(
            render_template,
            {
                "FRONTEND_SERVICE_NAME": frontend_service_name,
                "BACKEND_SERVICE_NAME": backend_service_name,
                "DATABASE_NAME": database_name,
            },
        ),
        "src/main.tsx": main_tsx(),
        "src/App.tsx": apply_tokens(app_tsx(), {"APP_TITLE": app_title}),
        "src/styles.css": styles_css(),
        "src/vite-env.d.ts": vite_env_declarations(include_plugin_client_ref=pwa_mode == "plugin"),
        "src/tests/setup.ts": test_setup(),
        "src/tests/app.spec.tsx": app_test(),
        "src/tests/pwa.registration.spec.ts": pwa_registration_test(),
        "src/pwa/runtime.ts": pwa_runtime_plugin() if pwa_mode == "plugin" else pwa_runtime_custom(),
        "public/manifest.webmanifest": manifest_webmanifest(app_title),
        "public/icon.svg": icon_svg,
        "public/favicon.svg": icon_svg,
        "scripts/quality/check-pwa-build-artifacts.mjs": pwa_quality_gate(),
        ".github/workflows/ci.yml": workflow_ci(),
        "tests/e2e/smoke.spec.ts": e2e_smoke_test(app_title),
    }

    if pwa_mode == "custom-sw":
        files["public/sw.js"] = read_asset(skill_root, "sw.custom.js")

    if profile == "fullstack-render":
        files.update(
            {
                "backend/package.json": backend_package_json(),
                "backend/.env.example": backend_env_example(),
                "backend/server.js": backend_server_js(),
                "backend/prisma/schema.prisma": prisma_schema(),
            }
        )

    return files


def backend_server_js() -> str:
    return """const fastify = require("fastify");
const cors = require("@fastify/cors");
require("dotenv").config();

const app = fastify({ logger: true });

const corsOrigins = String(process.env.CORS_ORIGINS || "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const isOriginAllowed = (origin) => {
  if (!origin) {
    return true;
  }
  if (process.env.NODE_ENV !== "production") {
    return true;
  }
  return corsOrigins.includes(origin);
};

app.register(cors, {
  origin: (origin, cb) => cb(null, isOriginAllowed(origin)),
  credentials: true,
});

app.get("/health", async () => {
  return { ok: true };
});

app.get("/api/ping", async () => {
  return { ok: true, time: Date.now() };
});

const start = async () => {
  const port = Number(process.env.PORT || 3000);
  try {
    await app.listen({ host: "0.0.0.0", port });
  } catch (error) {
    app.log.error(error);
    process.exit(1);
  }
};

start();
"""


def prisma_schema() -> str:
    return """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model HealthCheck {
  id        String   @id @default(cuid())
  createdAt DateTime @default(now())
}
"""


def write_files(out_dir: Path, files: dict[str, str], dry_run: bool) -> tuple[int, int]:
    created = 0
    overwritten = 0

    for relative_path, content in sorted(files.items()):
        target = out_dir / relative_path
        exists = target.exists()
        if dry_run:
            state = "overwrite" if exists else "create"
            print(f"[dry-run] {state:9s} {relative_path}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        normalized_content = content if content.endswith("\n") else content + "\n"
        target.write_text(normalized_content, encoding="utf-8")
        if exists:
            overwritten += 1
            print(f"[overwrite] {relative_path}")
        else:
            created += 1
            print(f"[create]    {relative_path}")

    return created, overwritten


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap a React + Render + PWA project scaffold.")
    parser.add_argument("--profile", default="frontend-static-pwa", choices=sorted(VALID_PROFILES))
    parser.add_argument("--pwa-mode", default="plugin", choices=sorted(VALID_PWA_MODES))
    parser.add_argument("--project-name", required=True, help="Project name in kebab-case.")
    parser.add_argument("--app-title", default="", help="Human-readable app title (defaults to project name in Title Case).")
    parser.add_argument("--out-dir", required=True, help="Target directory for generated project files.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting scaffold files in a non-empty target directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned file writes without changing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    normalized_project_name = normalize_kebab(args.project_name)
    if not normalized_project_name:
        print("[error] --project-name must include letters or digits.")
        return 1
    if normalized_project_name != args.project_name:
        print(f"[info] normalized project name: {normalized_project_name}")

    app_title = args.app_title.strip() or title_from_slug(normalized_project_name)
    out_dir = Path(args.out_dir).resolve()

    skill_root = Path(__file__).resolve().parent.parent

    try:
        ensure_writable_target(out_dir, force=args.force)
    except RuntimeError as error:
        print(f"[error] {error}")
        return 1

    files = main_files(
        skill_root=skill_root,
        profile=args.profile,
        pwa_mode=args.pwa_mode,
        project_name=normalized_project_name,
        app_title=app_title,
    )

