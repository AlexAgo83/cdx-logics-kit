# Stack Profile Matrix

Use this matrix to choose defaults while scaffolding.

## Shared Core (both profiles)

- React 19 + React DOM 19
- Vite + TypeScript strict mode
- ESLint flat config with `typescript-eslint` + React Hooks
- Vitest + Testing Library for unit/integration tests
- Playwright for E2E smoke
- PWA manifest and registration runtime
- Render blueprint (`render.yaml`)
- CI workflow with lint/typecheck/test/e2e/build/PWA quality gate

## frontend-static-pwa

Aligns primarily with `electrical-plan-editor`:

- Static hosting on Render (`runtime: static`)
- SPA rewrite route to `/index.html`
- Static cache headers for assets + no-cache for SW/manifest/index
- PWA plugin mode available (`vite-plugin-pwa` + Workbox)
- PWA quality artifact checker script (`scripts/quality/check-pwa-build-artifacts.mjs`)

## fullstack-render

Aligns with Sentry production topology patterns:

- Frontend static app + backend Node web service
- Backend starter on Fastify
- Prisma schema scaffold included in `backend/prisma`
- Render blueprint includes frontend service, backend service, and database block
- CORS origin env contract included for cross-origin frontend/backend deployment

## PWA strategy choice

- `plugin` mode:
- Fast setup, Workbox generated, minimal manual service-worker code.

- `custom-sw` mode:
- Explicit versioned SW lifecycle control inspired by Sentry style.
- Better when you need tighter update/reload behavior ownership.
