# Ollama integration notes

## Defaults and endpoints

- Default host: `http://127.0.0.1:11434`
- `GET /api/version` -> server version and basic health check
- `GET /api/tags` -> installed local models
- `POST /api/chat` -> chat completion, supports `stream: true/false`

## DeepSeek Coder V2 model notes

- Preferred local coding tag: `deepseek-coder-v2:16b`
- Floating tag: `deepseek-coder-v2:latest`
- Avoid defaulting to the larger `236b` class unless the user clearly has hardware for it
- Normalize common user variants such as `deepseeker-coder-v2` to `deepseek-coder-v2`

Basic commands:

- Pull the preferred model:
  - `ollama pull deepseek-coder-v2:16b`
- List installed variants:
  - `ollama list | grep -E '^deepseek-coder-v2'`
- Run a quick CLI test:
  - `ollama run deepseek-coder-v2:16b`
- Remove a local variant:
  - `ollama rm deepseek-coder-v2:16b`

## Continue in VS Code

Minimal config shape:

```yaml
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

Guidance:

- Config path: `~/.continue/config.yaml`
- Patch the existing file instead of overwriting unrelated models
- Prefer explicit model tags over `latest`
- If autocomplete should be faster than chat or edit, use a smaller dedicated completion model

## Roo Code

Expected local settings:

- API provider: `Ollama`
- Base URL: `http://localhost:11434`
- Model ID: `deepseek-coder-v2:16b`

Validate Ollama first, then editor settings.

## Dedicated local autocomplete

Recommended split:

- Main coding model: `deepseek-coder-v2:16b`
- Completion model: a smaller coder model such as `qwen2.5-coder:1.5b`

Use the split-model approach when low-latency inline completion matters more than using a single model everywhere.

## Server lifecycle

- Start server in foreground:
  - `ollama serve`
- Start as service on macOS with Homebrew:
  - `brew services start ollama`
- Stop service:
  - `brew services stop ollama`
- If launched by Ollama.app and it restarts, quit the app too:
  - `osascript -e 'quit app "Ollama"'`
- Force stop as fallback:
  - `pkill -f 'ollama serve'`
  - `pkill -x Ollama`
- Check if server is running:
  - `lsof -iTCP:11434 -sTCP:LISTEN -n -P`
  - `ps aux | grep -i '[o]llama'`

## Common env vars

- `OLLAMA_HOST`: bind address for the Ollama server, for example `127.0.0.1:11434` or `0.0.0.0:11434`
- `OLLAMA_ORIGINS`: comma-separated list of allowed origins for browser calls

## CORS and 403 on LAN

If the UI is opened via `http://192.168.x.x:5173`, the browser sends an `Origin` header and Ollama may return `403`.

Fix options:

1. Proxy in the app, recommended: call `/ollama/*` on the same origin and forward to Ollama
2. Allow origins: set `OLLAMA_ORIGINS=http://localhost:5173,http://192.168.1.199:5173` before starting Ollama
3. Drop `Origin` in the proxy before forwarding

## Vite dev proxy snippet

```ts
server: {
  proxy: {
    "/ollama": {
      target: "http://127.0.0.1:11434",
      changeOrigin: true,
      configure: (proxy) => {
        proxy.on("proxyReq", (proxyReq) => {
          proxyReq.removeHeader("origin")
        })
      },
      rewrite: (path) => path.replace(/^\/ollama/, ""),
    },
  },
}
```

## Express proxy snippet

```js
app.use(
  "/ollama",
  createProxyMiddleware({
    target: "http://127.0.0.1:11434",
    changeOrigin: true,
    pathRewrite: { "^/ollama": "" },
    on: {
      proxyReq(proxyReq) {
        proxyReq.removeHeader("origin")
      },
    },
  }),
)
```

## LAN vs local

- For local dev, keep `VITE_OLLAMA_HOST` on `127.0.0.1` and proxy from the app server
- To expose Ollama directly on the network, bind `OLLAMA_HOST=0.0.0.0:11434` and secure access with the firewall
