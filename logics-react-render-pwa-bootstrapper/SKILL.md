---
name: logics-react-render-pwa-bootstrapper
description: Bootstrap a production-ready React web project with Vite, TypeScript, PWA support, Render blueprint, and CI/testing defaults aligned with the stack patterns used in electrical-plan-editor and Sentry. Use when starting a new app that should ship quickly with lint/typecheck/test/e2e gates, deploy on Render, and support either frontend-only static hosting or a fullstack frontend+Fastify+Prisma setup.
---

# React + Render + PWA Bootstrapper

## Run

Create a new project from the scaffold script:

```bash
python3 logics/skills/logics-react-render-pwa-bootstrapper/scripts/bootstrap_react_render_project.py \
  --project-name my-app \
  --out-dir ../my-app \
  --profile frontend-static-pwa \
  --pwa-mode plugin
```

## Profiles

- `frontend-static-pwa`
- React + Vite + TypeScript strict
- PWA (plugin or custom service worker mode)
- Render static blueprint (`render.yaml`)
- ESLint, Vitest, Playwright, GitHub CI, PWA quality gate

- `fullstack-render`
- Everything in frontend profile
- Adds `backend/` Fastify API starter
- Adds Prisma schema and backend scripts
- Generates multi-service Render blueprint (frontend static + backend + database)

## PWA Modes

- `plugin` (default): uses `vite-plugin-pwa` with Workbox output.
- `custom-sw`: uses a versioned handcrafted `public/sw.js` flow with explicit update activation.

## Common Commands

Dry-run to inspect what will be generated:

```bash
python3 logics/skills/logics-react-render-pwa-bootstrapper/scripts/bootstrap_react_render_project.py \
  --project-name my-app \
  --out-dir ../my-app \
  --profile fullstack-render \
  --pwa-mode custom-sw \
  --dry-run
```

Overwrite an existing target directory:

```bash
python3 logics/skills/logics-react-render-pwa-bootstrapper/scripts/bootstrap_react_render_project.py \
  --project-name my-app \
  --out-dir ../my-app \
  --force
```

## What Gets Generated

- React 19 + Vite + TypeScript strict scaffold
- ESLint 9 flat config (typed rules)
- Vitest + Testing Library + Playwright setup
- PWA runtime + manifest + icons + quality artifact check script
- `.github/workflows/ci.yml` with lint/typecheck/test/e2e/build/quality gates
- `render.yaml` aligned to selected profile

## Resources

### scripts/

- `bootstrap_react_render_project.py`: main scaffolding tool.

### references/

- `stack-profile-matrix.md`: concise mapping of stack choices to patterns reused from electrical-plan-editor and Sentry.

### assets/

- `render.static.yaml` and `render.fullstack.yaml`: Render blueprint templates.
- `sw.custom.js`: custom service worker template for `custom-sw` mode.
- `icon.svg`: default app icon copied into scaffolded projects.
