---
name: logics-connector-render
description: "Connect Render (Public API) to the Logics workflow: list services/deploys, snapshot/apply deployment plan changes, and import a Render service context into `logics/backlog/`."
---

# Render connector

## Environment variables
- `RENDER_API_KEY` (required, Render API key; sent as `Authorization: Bearer <token>`).
- `RENDER_API_BASE_URL` (optional, default `https://api.render.com/v1`).
- `RENDER_OPENAPI_URL` (optional, default `https://api-docs.render.com/openapi/render-public-api-1.json`).

## List services
```bash
python3 logics/skills/logics-connector-render/scripts/render_list_services.py \
  --limit 100 --include-previews yes
```

## List deploys for one service
```bash
python3 logics/skills/logics-connector-render/scripts/render_list_deploys.py \
  --service-id srv-xxxxxxxx --limit 20
```

## Manage deployment plans

Show supported plan enums from Render OpenAPI:
```bash
python3 logics/skills/logics-connector-render/scripts/render_manage_deployment_plans.py show-plans
```

Create a deployment plan snapshot file:
```bash
python3 logics/skills/logics-connector-render/scripts/render_manage_deployment_plans.py snapshot \
  --out logics/external/render/render_deployment_plan.snapshot.json \
  --markdown-out logics/external/render/render_deployment_plan.snapshot.md \
  --limit 200
```

Apply target plan changes from a plan file:
```bash
python3 logics/skills/logics-connector-render/scripts/render_manage_deployment_plans.py apply \
  --plan-file logics/external/render/render_deployment_plan.snapshot.json
```

Validate changes without applying:
```bash
python3 logics/skills/logics-connector-render/scripts/render_manage_deployment_plans.py apply \
  --plan-file logics/external/render/render_deployment_plan.snapshot.json \
  --validate-only
```

## Import a Render service into Logics backlog
```bash
python3 logics/skills/logics-connector-render/scripts/render_to_backlog.py \
  --service-id srv-xxxxxxxx --deploy-limit 10
```

Notes:
- `render_to_backlog.py` creates a new `item_###_*.md` in `logics/backlog/` using the kit template.
- Deployment plan apply only updates `serviceDetails.plan` and validates target plans against Render OpenAPI enums.
