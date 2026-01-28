---
name: logics-ollama-specialist
description: Install, configure, and integrate Ollama in local apps (macOS/Homebrew, env vars like OLLAMA_HOST/OLLAMA_ORIGINS) and wire frontend/backends to /api/chat via Vite or Express proxies. Use when building or debugging Ollama-powered UIs, fixing CORS/403 Origin issues on LAN, or setting up PWA/local dev flows that call Ollama.
---

# Logics Ollama Specialist

## Quick start

1) Clarify OS, target model, and whether Ollama should run locally or on another host.
2) If installation is needed, ask for explicit permission before running install commands.
3) If the app is a frontend, prefer a same-origin proxy (`/ollama/*`) to avoid CORS.
4) If LAN URL causes 403, remove `Origin` in the proxy or set `OLLAMA_ORIGINS`.

## Install Ollama (macOS)

- Ask for explicit approval before running installs.
- Use the script for safe/consistent setup:

```bash
DRY_RUN=1 logics/skills/ollama-specialist/scripts/ollama_install_macos.sh qwen3
```

If approved, run again without `DRY_RUN=1`.

## Verify Ollama

Run the check script to validate prerequisites and reachability:

```bash
logics/skills/ollama-specialist/scripts/ollama_check.sh qwen3
```

## Integrate with a frontend (Vite/React)

1) Use a proxy to call `/ollama/*` from the browser.
2) Set `VITE_OLLAMA_HOST` to the local Ollama URL.
3) If LAN access returns 403, remove the `Origin` header in the proxy or set `OLLAMA_ORIGINS`.

See `references/ollama-integration.md` for snippets and common pitfalls.

## Add PWA support (Vite)

Use `vite-plugin-pwa`, register the SW, and add icons/manifest fields.
See `references/pwa-vite.md`.

## Resources

### scripts/
- `ollama_check.sh`: Verify `ollama`, Node, and basic `/api/version` reachability.
- `ollama_install_macos.sh`: Install/start Ollama with an optional model (supports `DRY_RUN=1`).

### references/
- `ollama-integration.md`: Proxy/CORS/Origin fixes, env vars, and endpoint notes.
- `pwa-vite.md`: PWA steps for Vite/React apps.
