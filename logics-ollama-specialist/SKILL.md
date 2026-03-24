---
name: logics-ollama-specialist
description: Install, configure, validate, and integrate Ollama for local development. Use when setting up deepseek-coder-v2 for terminal, HTTP API, Continue, or Roo Code workflows, or when wiring frontend/backends to Ollama through Vite or Express proxies and fixing CORS or 403 Origin issues.
---

# Logics Ollama Specialist

Platform scope:

- `ollama_install_macos.sh` is intentionally macOS-specific.
- `ollama_check.sh` is a POSIX-shell helper and should not be treated as a Windows workflow entrypoint.
- On Windows, follow the Ollama product's native install path first, then adapt the integration guidance in `references/`.

Normalize common user variants such as `deepseeker-coder-v2`, `deepseek coder v2`, or `deepseek-coder` to `deepseek-coder-v2`.

## Quick start

1. Clarify OS, target model, editor surface, and whether Ollama runs locally or on another host.
2. If installation is needed, ask for explicit permission before running install commands.
3. For local coding, prefer `deepseek-coder-v2:16b` unless the user explicitly asks for another tag.
4. Verify Ollama, daemon reachability, and model availability before editing editor config.
5. If the app is a frontend, prefer a same-origin proxy (`/ollama/*`) to avoid CORS.
6. If LAN URL causes `403`, remove `Origin` in the proxy or set `OLLAMA_ORIGINS`.

Do not default to `deepseek-coder-v2:236b` unless the user clearly has server-grade hardware.

## Install Ollama (macOS-only helper)

- Ask for explicit approval before running installs.
- Use the script for safe and consistent setup:

```bash
DRY_RUN=1 logics/skills/logics-ollama-specialist/scripts/ollama_install_macos.sh deepseek-coder-v2:16b
```

If approved, run again without `DRY_RUN=1`.

## DeepSeek Coder V2 workflow

Prefer the explicit 16B tag for local development:

```bash
ollama pull deepseek-coder-v2:16b
```

Validate the model path:

```bash
ollama list | grep -E '^deepseek-coder-v2'
ollama run deepseek-coder-v2:16b "Write a Python hello world"
```

Validate the local HTTP API:

```bash
curl -fsS http://127.0.0.1:11434/api/chat -d '{
  "model": "deepseek-coder-v2:16b",
  "messages": [{"role": "user", "content": "Reply with the word ready"}],
  "stream": false
}'
```

Use `deepseek-coder-v2:latest` only if the user explicitly wants the floating tag.

## Continue in VS Code

When the user wants a local VS Code coding assistant and does not name another extension, prefer Continue.

The user-level config file is:

```text
~/.continue/config.yaml
```

Minimal working model entry:

```yaml
name: Local Assistant
version: 0.0.1
schema: v1

models:
  - name: DeepSeek Coder V2
    provider: ollama
    model: deepseek-coder-v2:16b
    apiBase: http://localhost:11434
    roles:
      - chat
      - edit
      - apply
```

Rules for Continue edits:

- Patch the existing file instead of overwriting unrelated models.
- Keep `apiBase: http://localhost:11434` unless the user says Ollama is remote.
- Prefer explicit tags instead of `latest`.
- If the user wants faster inline completion, pair the main DeepSeek model with a smaller completion model instead of forcing one large model to do everything.

## Roo Code

If the user explicitly wants Roo Code, keep the same Ollama baseline and wire the editor after validation:

- API provider: `Ollama`
- Base URL: `http://localhost:11434`
- Model ID: `deepseek-coder-v2:16b`

Validate in this order:

1. `ollama --version`
2. `curl -fsS http://127.0.0.1:11434/api/tags`
3. `ollama list | grep -E '^deepseek-coder-v2'`
4. Roo Code provider, base URL, and model selection match the local setup

## Dedicated local autocomplete

If the user wants low-latency inline completion, prefer a split-model setup:

- `deepseek-coder-v2:16b` for chat, edit, and apply workflows
- a smaller local completion model such as `qwen2.5-coder:1.5b` for autocomplete

Use this pattern when:

- the main coding model is responsive enough for chat or edit work but too heavy for inline completion
- the user wants a local setup that feels closer to Copilot-style suggestions

Do not collapse these roles into a single larger model by default when responsiveness is the operator's primary concern.

## Start and stop Ollama server

- Start in foreground:

```bash
ollama serve
```

- Start as Homebrew service:

```bash
brew services start ollama
```

- Stop foreground server: `Ctrl + C`
- Stop Homebrew service:

```bash
brew services stop ollama
```

- If Ollama.app auto-restarts the server, quit the app:

```bash
osascript -e 'quit app "Ollama"'
```

- Last-resort force stop:

```bash
pkill -f 'ollama serve'
pkill -x Ollama
```

- Verify server status:

```bash
lsof -iTCP:11434 -sTCP:LISTEN -n -P
```

## Verify Ollama

Run the check script to validate prerequisites, reachability, model presence, and optional Continue config hints:

```bash
logics/skills/logics-ollama-specialist/scripts/ollama_check.sh deepseek-coder-v2:16b
```

## Integrate with a frontend (Vite/React)

1. Use a proxy to call `/ollama/*` from the browser.
2. Set `VITE_OLLAMA_HOST` to the local Ollama URL.
3. If LAN access returns `403`, remove the `Origin` header in the proxy or set `OLLAMA_ORIGINS`.

See `references/ollama-integration.md` for snippets and common pitfalls.

## Add PWA support (Vite)

Use `vite-plugin-pwa`, register the SW, and add icons or manifest fields.
See `references/pwa-vite.md`.

## Troubleshooting

Common failures and fixes:

- `ollama: command not found`
  Install Ollama first.
- `curl ... /api/tags` fails
  Start the Ollama app or run `ollama serve`.
- Model missing from `ollama list`
  Run `ollama pull deepseek-coder-v2:16b`.
- Continue or Roo Code cannot answer
  Re-check provider, model, and base URL against the local Ollama setup.
- Browser app on LAN returns `403`
  Remove `Origin` in the proxy or set `OLLAMA_ORIGINS`.
- Requests are very slow or fail under load
  The machine likely does not have enough RAM or VRAM for the chosen model; move to a smaller model or a smaller completion model where appropriate.

## Resources

### scripts/
- `ollama_check.sh`: POSIX-shell helper to verify `ollama`, curl reachability, local model availability, and optional Continue config hints.
- `ollama_install_macos.sh`: macOS-only helper to install or start Ollama with an optional model (supports `DRY_RUN=1`).

### references/
- `ollama-integration.md`: DeepSeek model notes, editor-integration notes, proxy or CORS guidance, env vars, and endpoint notes.
- `pwa-vite.md`: PWA steps for Vite or React.
