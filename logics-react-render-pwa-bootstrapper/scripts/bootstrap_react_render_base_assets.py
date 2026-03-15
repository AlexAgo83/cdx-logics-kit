#!/usr/bin/env python3
"""Bootstrap a React + Render + PWA project scaffold.

Profiles:
- frontend-static-pwa
- fullstack-render

PWA modes:
- plugin (vite-plugin-pwa)
- custom-sw (handcrafted service worker)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VALID_PROFILES = {"frontend-static-pwa", "fullstack-render"}
VALID_PWA_MODES = {"plugin", "custom-sw"}


def normalize_kebab(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def apply_tokens(template: str, tokens: dict[str, str]) -> str:
    rendered = template
    for key, value in tokens.items():
        rendered = rendered.replace(f"__{key}__", value)
    return rendered


def ensure_writable_target(out_dir: Path, force: bool) -> None:
    if not out_dir.exists():
        return
    if not out_dir.is_dir():
        raise RuntimeError(f"Target exists and is not a directory: {out_dir}")
    entries = [entry for entry in out_dir.iterdir()]
    if entries and not force:
        raise RuntimeError(
            f"Target directory is not empty: {out_dir}. Use --force to overwrite scaffold files."
        )


def read_asset(skill_root: Path, relative_path: str) -> str:
    asset_path = skill_root / "assets" / relative_path
    if not asset_path.exists():
        raise RuntimeError(f"Missing skill asset: {asset_path}")
    return asset_path.read_text(encoding="utf-8")


def package_json(profile: str, pwa_mode: str, project_name: str) -> str:
    scripts = {
        "dev": "vite",
        "build": "tsc --noEmit && vite build",
        "preview": "vite preview",
        "typecheck": "tsc --noEmit",
        "lint": "eslint .",
        "test": "vitest",
        "test:ci": "vitest run --coverage",
        "test:e2e": "env -u NO_COLOR playwright test --reporter=line",
        "quality:pwa": "node scripts/quality/check-pwa-build-artifacts.mjs",
        "ci:local": "npm run -s lint && npm run -s typecheck && npm run -s test:ci && npm run -s test:e2e && npm run -s build && npm run -s quality:pwa",
    }
    if profile == "fullstack-render":
        scripts.update(
            {
                "backend:dev": "npm --prefix backend run dev",
                "backend:start": "npm --prefix backend run start",
                "db:generate": "npm --prefix backend run prisma:generate",
                "db:migrate": "npm --prefix backend run prisma:migrate",
            }
        )

    dev_dependencies = {
        "@eslint/js": "^9.39.1",
        "@playwright/test": "^1.56.1",
        "@testing-library/jest-dom": "^6.9.1",
        "@testing-library/react": "^16.3.0",
        "@types/node": "^24.10.0",
        "@types/react": "^19.2.2",
        "@types/react-dom": "^19.2.2",
        "@vitejs/plugin-react": "^5.1.0",
        "@vitest/coverage-v8": "^4.0.7",
        "eslint": "^9.39.1",
        "eslint-plugin-react-hooks": "^7.0.1",
        "eslint-plugin-react-refresh": "^0.4.24",
        "globals": "^16.4.0",
        "jsdom": "^27.1.0",
        "typescript": "^5.9.3",
        "typescript-eslint": "^8.46.4",
        "vite": "^7.2.0",
        "vitest": "^4.0.7",
    }
    if pwa_mode == "plugin":
        dev_dependencies["vite-plugin-pwa"] = "^1.1.0"

    payload = {
        "name": project_name,
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "engines": {"node": ">=20"},
        "scripts": scripts,
        "dependencies": {
            "react": "^19.2.0",
            "react-dom": "^19.2.0",
        },
        "devDependencies": dev_dependencies,
        "x-pwa-mode": pwa_mode,
        "x-bootstrap-profile": profile,
    }
    return json.dumps(payload, indent=2) + "\n"


def backend_package_json() -> str:
    payload = {
        "name": "backend",
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "dev": "node --watch server.js",
            "start": "node server.js",
            "prisma:generate": "prisma generate",
            "prisma:migrate": "prisma migrate dev",
        },
        "dependencies": {
            "@fastify/cors": "^11.1.0",
            "@prisma/client": "^6.18.0",
            "dotenv": "^17.2.3",
            "fastify": "^5.6.1",
        },
        "devDependencies": {
            "prisma": "^6.18.0",
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def root_env_example(profile: str) -> str:
    lines = [
        "VITE_APP_HOST=127.0.0.1",
        "VITE_APP_PORT=5173",
        "VITE_PREVIEW_PORT=4173",
        "VITE_E2E_BASE_URL=http://127.0.0.1:4173",
    ]
    if profile == "fullstack-render":
        lines.append("VITE_API_BASE=http://127.0.0.1:3000")
    return "\n".join(lines) + "\n"


def backend_env_example() -> str:
    return "\n".join(
        [
            "PORT=3000",
            "NODE_ENV=development",
            "CORS_ORIGINS=http://127.0.0.1:5173",
            "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/starter_app",
        ]
    ) + "\n"


def gitignore() -> str:
    return "\n".join(
        [
            "node_modules",
            "dist",
            "coverage",
            "playwright-report",
            "test-results",
            ".env",
            ".env.local",
            "backend/node_modules",
            "backend/.env",
            "backend/prisma/dev.db",
            "backend/prisma/dev.db-journal",
        ]
    ) + "\n"


def tsconfig() -> str:
    return """{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "types": ["vitest/globals", "node"]
  },
  "include": ["src", "tests", "vite.config.ts", "playwright.config.ts", "eslint.config.js"]
}
"""


def vite_config_plugin(app_title: str) -> str:
    template = """import { defineConfig, loadEnv } from "vite";
import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const appHost = env.VITE_APP_HOST || "127.0.0.1";
  const appPort = Number(env.VITE_APP_PORT || 5173);
  const previewPort = Number(env.VITE_PREVIEW_PORT || 4173);
  const isCi = process.env.CI === "true";

  return {
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version)
    },
    plugins: [
      react(),
      VitePWA({
        registerType: "prompt",
        injectRegister: false,
        includeAssets: ["icon.svg", "favicon.svg"],
        manifest: {
          name: "__APP_TITLE__",
          short_name: "__APP_SHORT_NAME__",
          description: "Starter React application with PWA support and Render deployment.",
          start_url: "/",
          scope: "/",
          display: "standalone",
          background_color: "#0f2335",
          theme_color: "#17374e",
          icons: [
            {
              src: "/icon.svg",
              sizes: "any",
              type: "image/svg+xml"
            }
          ]
        },
        workbox: {
          cleanupOutdatedCaches: true,
          clientsClaim: true,
          skipWaiting: false,
          navigateFallback: "/index.html"
        }
      })
    ],
    server: {
      host: appHost,
      port: appPort
    },
    preview: {
      host: appHost,
      port: previewPort
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) {
              return "vendor-react";
            }
            if (id.includes("node_modules/workbox-window")) {
              return "vendor-pwa";
            }
            return undefined;
          }
        }
      }
    },
    test: {
      environment: "jsdom",
      setupFiles: ["src/tests/setup.ts"],
      include: ["src/tests/**/*.spec.ts", "src/tests/**/*.spec.tsx"],
      exclude: ["tests/e2e/**"],
      pool: isCi ? "forks" : undefined,
      minWorkers: isCi ? 1 : undefined,
      maxWorkers: isCi ? "50%" : undefined,
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/**/*.{ts,tsx}"]
      }
    }
  };
});
"""
    return apply_tokens(
        template,
        {
            "APP_TITLE": app_title,
            "APP_SHORT_NAME": app_title[:12] if len(app_title) > 12 else app_title,
        },
    )


def vite_config_custom() -> str:
    return """import { defineConfig, loadEnv } from "vite";
import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const appHost = env.VITE_APP_HOST || "127.0.0.1";
  const appPort = Number(env.VITE_APP_PORT || 5173);
  const previewPort = Number(env.VITE_PREVIEW_PORT || 4173);
  const isCi = process.env.CI === "true";

  return {
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version)
    },
    plugins: [react()],
    server: {
      host: appHost,
      port: appPort
    },
    preview: {
      host: appHost,
      port: previewPort
    },
    build: {
      manifest: true,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) {
              return "vendor-react";
            }
            if (id.includes("node_modules")) {
              return "vendor";
            }
            return undefined;
          }
        }
      }
    },
    test: {
      environment: "jsdom",
      setupFiles: ["src/tests/setup.ts"],
      include: ["src/tests/**/*.spec.ts", "src/tests/**/*.spec.tsx"],
      exclude: ["tests/e2e/**"],
      pool: isCi ? "forks" : undefined,
      minWorkers: isCi ? 1 : undefined,
      maxWorkers: isCi ? "50%" : undefined,
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/**/*.{ts,tsx}"]
      }
    }
  };
});
"""


def eslint_config() -> str:
    return """import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  {
    ignores: ["dist", "coverage", "node_modules", "playwright-report", "test-results"]
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        ...globals.browser,
        __APP_VERSION__: "readonly"
      },
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname
      }
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "warn"
    }
  },
  {
    files: ["src/tests/**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      }
    }
  }
);
"""


def playwright_config() -> str:
    return """import { defineConfig } from "@playwright/test";
import { loadEnv } from "vite";

const env = loadEnv("development", process.cwd(), "");

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: env.VITE_E2E_BASE_URL || "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    serviceWorkers: "block"
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: env.VITE_E2E_BASE_URL || "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI
  }
});
"""


def index_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#17374e" />
    <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <title>__APP_TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""


def app_tsx() -> str:
    return """import { useEffect, useState } from "react";
import {
  applyPwaUpdate,
  listenForPwaOfflineReady,
  listenForPwaUpdate,
} from "./pwa/runtime";

type DeferredPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

export default function App() {
  const [installPrompt, setInstallPrompt] = useState<DeferredPrompt | null>(null);
  const [updateReady, setUpdateReady] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const [apiStatus, setApiStatus] = useState<"idle" | "ok" | "error">("idle");

  useEffect(() => {
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as DeferredPrompt);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    };
  }, []);

  useEffect(() => {
    const unlistenUpdate = listenForPwaUpdate(() => setUpdateReady(true));
    const unlistenOffline = listenForPwaOfflineReady(() => setOfflineReady(true));
    return () => {
      unlistenUpdate();
      unlistenOffline();
    };
  }, []);

  useEffect(() => {
    const apiBase = import.meta.env.VITE_API_BASE?.trim();
    if (!apiBase) {
      return;
    }

    let isMounted = true;
    fetch(`${apiBase}/health`)
      .then((response) => {
        if (!isMounted) {
          return;
        }
        setApiStatus(response.ok ? "ok" : "error");
      })
      .catch(() => {
        if (isMounted) {
          setApiStatus("error");
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const triggerInstall = async () => {
    if (!installPrompt) {
      return;
    }
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  };

  const triggerUpdate = async () => {
    await applyPwaUpdate();
    setUpdateReady(false);
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>__APP_TITLE__</h1>
        <p>React + Render + PWA starter ready.</p>
      </header>

      <section className="app-actions">
        {installPrompt && (
          <button type="button" onClick={triggerInstall}>
            Install app
          </button>
        )}
        {updateReady && (
          <button type="button" onClick={triggerUpdate}>
            Update ready
          </button>
        )}
      </section>

      {offlineReady && <p className="status-chip">Offline cache ready</p>}

      {import.meta.env.VITE_API_BASE && (
        <p className="status-chip" data-testid="backend-status">
          Backend health: {apiStatus}
        </p>
      )}
    </main>
  );
}
"""


def styles_css() -> str:
    return """* {
  box-sizing: border-box;
}

:root {
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  color: #e9f0f6;
  background: radial-gradient(circle at top left, #1f4e70, #0c1622 62%);
}

body {
  margin: 0;
  min-height: 100vh;
}

#root {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem;
}

.app-shell {
  width: min(760px, 100%);
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(8, 19, 29, 0.72);
  backdrop-filter: blur(10px);
  border-radius: 18px;
  padding: 1.5rem;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}

.app-header h1 {
  margin: 0;
  font-size: clamp(1.6rem, 3vw, 2.25rem);
}

.app-header p {
  margin-top: 0.5rem;
  color: rgba(233, 240, 246, 0.84);
}

.app-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin: 1rem 0;
}

button {
  appearance: none;
  border: 0;
  border-radius: 999px;
  padding: 0.6rem 1rem;
  font-weight: 600;
  color: #091521;
  background: linear-gradient(90deg, #ffd166, #ff9f1c);
  cursor: pointer;
}

.status-chip {
  display: inline-block;
  margin: 0.25rem 0.5rem 0.25rem 0;
  padding: 0.25rem 0.7rem;
  border-radius: 999px;
  background: rgba(78, 185, 255, 0.18);
  border: 1px solid rgba(78, 185, 255, 0.4);
}
"""


def main_tsx() -> str:
    return """import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import { registerPwa } from "./pwa/runtime";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

registerPwa().catch((error) => {
  console.warn("[pwa] registration failed", error);
});
"""


def pwa_runtime_plugin() -> str:
    return """const PWA_UPDATE_EVENT = "app:pwa-update-available";
const PWA_OFFLINE_READY_EVENT = "app:pwa-offline-ready";

let applyUpdateAction: ((reloadPage?: boolean) => Promise<void>) | null = null;

const dispatchPwaEvent = (name: string) => {
  window.dispatchEvent(new Event(name));
};

export const listenForPwaUpdate = (handler: EventListener) => {
  window.addEventListener(PWA_UPDATE_EVENT, handler);
  return () => window.removeEventListener(PWA_UPDATE_EVENT, handler);
};

export const listenForPwaOfflineReady = (handler: EventListener) => {
  window.addEventListener(PWA_OFFLINE_READY_EVENT, handler);
  return () => window.removeEventListener(PWA_OFFLINE_READY_EVENT, handler);
};

export const registerPwa = async () => {
  if (!import.meta.env.PROD || typeof window === "undefined") {
    return;
  }

  const { registerSW } = await import("virtual:pwa-register");

  applyUpdateAction = registerSW({
    immediate: false,
    onNeedRefresh: () => dispatchPwaEvent(PWA_UPDATE_EVENT),
    onOfflineReady: () => dispatchPwaEvent(PWA_OFFLINE_READY_EVENT),
    onRegisterError: (error) => {
      console.warn("[pwa] register error", error);
    },
  });
};

export const applyPwaUpdate = async () => {
  if (!applyUpdateAction) {
    return;
  }
  await applyUpdateAction(true);
};
"""


def pwa_runtime_custom() -> str:
    return """const PWA_UPDATE_EVENT = "app:pwa-update-available";
const PWA_OFFLINE_READY_EVENT = "app:pwa-offline-ready";

let registrationRef: ServiceWorkerRegistration | null = null;

const dispatchPwaEvent = (name: string) => {
  window.dispatchEvent(new Event(name));
};

const notifyIfWaiting = () => {
  if (registrationRef?.waiting && navigator.serviceWorker.controller) {
    dispatchPwaEvent(PWA_UPDATE_EVENT);
  }
};

export const listenForPwaUpdate = (handler: EventListener) => {
  window.addEventListener(PWA_UPDATE_EVENT, handler);
  return () => window.removeEventListener(PWA_UPDATE_EVENT, handler);
};

export const listenForPwaOfflineReady = (handler: EventListener) => {
  window.addEventListener(PWA_OFFLINE_READY_EVENT, handler);
  return () => window.removeEventListener(PWA_OFFLINE_READY_EVENT, handler);
};

export const registerPwa = async () => {
  if (
    !import.meta.env.PROD
    || typeof window === "undefined"
    || typeof navigator === "undefined"
    || !("serviceWorker" in navigator)
  ) {
    return;
  }

  const version = typeof __APP_VERSION__ === "string" && __APP_VERSION__.trim().length > 0
    ? __APP_VERSION__
    : "dev";

  registrationRef = await navigator.serviceWorker.register(`/sw.js?v=${version}`);
  dispatchPwaEvent(PWA_OFFLINE_READY_EVENT);
  notifyIfWaiting();

  registrationRef.addEventListener("updatefound", () => {
    const installing = registrationRef?.installing;
    if (!installing) {
      return;
    }
    installing.addEventListener("statechange", () => {
      if (installing.state === "installed") {
        notifyIfWaiting();
      }
    });
  });
};

export const applyPwaUpdate = async () => {
  if (!registrationRef) {
    return;
  }

  if (registrationRef.waiting) {
    registrationRef.waiting.postMessage({ type: "SKIP_WAITING" });
    window.location.reload();
    return;
  }

  window.location.reload();
};
"""


def vite_env_declarations(include_plugin_client_ref: bool) -> str:
    head = "/// <reference types=\"vite/client\" />\n"
    if include_plugin_client_ref:
        head += "/// <reference types=\"vite-plugin-pwa/client\" />\n"
    return (
        head
        + "\n"
        + "declare const __APP_VERSION__: string;\n"
        + "\n"
        + "interface ImportMetaEnv {\n"
        + "  readonly VITE_APP_HOST?: string;\n"
        + "  readonly VITE_APP_PORT?: string;\n"
        + "  readonly VITE_PREVIEW_PORT?: string;\n"
        + "  readonly VITE_E2E_BASE_URL?: string;\n"
        + "  readonly VITE_API_BASE?: string;\n"
        + "}\n"
        + "\n"
        + "interface ImportMeta {\n"
        + "  readonly env: ImportMetaEnv;\n"
        + "}\n"
    )


def manifest_webmanifest(app_title: str) -> str:
    short_name = app_title[:12] if len(app_title) > 12 else app_title
    template = """{
  "name": "__APP_TITLE__",
  "short_name": "__APP_SHORT_NAME__",
  "description": "Starter React application with PWA support and Render deployment.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0f2335",
  "theme_color": "#17374e",
  "icons": [
    {
      "src": "/icon.svg",
      "sizes": "any",
      "type": "image/svg+xml"
    }
  ]
}
"""
    return apply_tokens(template, {"APP_TITLE": app_title, "APP_SHORT_NAME": short_name})


def pwa_quality_gate() -> str:
    return """import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const distDir = join(process.cwd(), "dist");
const manifestPath = join(distDir, "manifest.webmanifest");
const serviceWorkerPath = join(distDir, "sw.js");

if (!existsSync(distDir)) {
  throw new Error("dist directory not found. Run `npm run build` before `npm run quality:pwa`.");
}

if (!existsSync(manifestPath)) {
  throw new Error("dist/manifest.webmanifest is missing.");
}

if (!existsSync(serviceWorkerPath)) {
  throw new Error("dist/sw.js is missing.");
}

const packageJson = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8"));
const pwaMode = packageJson["x-pwa-mode"];

if (pwaMode === "plugin") {
  const workboxFile = readdirSync(distDir).find((name) => /^workbox-.*\.js$/.test(name));
  if (workboxFile === undefined) {
    throw new Error("No workbox runtime artifact found in dist (expected workbox-*.js).");
  }
  console.log(`PWA artifact quality gate passed (plugin mode). Found ${workboxFile}.`);
} else {
  console.log("PWA artifact quality gate passed (custom-sw mode).");
}
"""


def workflow_ci() -> str:
    return """name: CI

on:
  push:
    branches:
      - main
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright browser
        run: npx playwright install --with-deps chromium

      - name: ESLint
        run: npm run lint

      - name: Typecheck
        run: npm run typecheck

      - name: Vitest (coverage)
        run: npm run test:ci

      - name: E2E smoke
        run: npm run test:e2e

      - name: Production build
        run: npm run build

      - name: PWA build artifact quality gate
        run: npm run quality:pwa
"""


