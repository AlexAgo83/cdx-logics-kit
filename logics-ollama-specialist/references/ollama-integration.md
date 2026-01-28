# Ollama integration notes

## Defaults & endpoints

- Default host: `http://127.0.0.1:11434`
- `GET /api/version` → server version (health check)
- `POST /api/chat` → chat completion (supports `stream: true/false`)

## Common env vars

- `OLLAMA_HOST`: bind address for the Ollama server (e.g., `127.0.0.1:11434` or `0.0.0.0:11434`)
- `OLLAMA_ORIGINS`: comma‑separated list of allowed Origins for browser calls

## CORS / 403 on LAN

If the UI is opened via `http://192.168.x.x:5173`, the browser sends:
`Origin: http://192.168.x.x:5173` and Ollama may respond `403`.

Fix options:
1) **Proxy in the app** (recommended): call `/ollama/*` on the same origin and forward to Ollama.
2) **Allow Origins**: set `OLLAMA_ORIGINS=http://localhost:5173,http://192.168.1.199:5173` before starting Ollama.
3) **Drop Origin in proxy**: remove the `Origin` header before forwarding.

## Vite dev proxy snippet

```ts
server: {
  proxy: {
    '/ollama': {
      target: 'http://127.0.0.1:11434',
      changeOrigin: true,
      configure: (proxy) => {
        proxy.on('proxyReq', (proxyReq) => {
          proxyReq.removeHeader('origin')
        })
      },
      rewrite: (path) => path.replace(/^\\/ollama/, ''),
    },
  },
}
```

## Express proxy snippet (production/dev server)

```js
app.use(
  '/ollama',
  createProxyMiddleware({
    target: 'http://127.0.0.1:11434',
    changeOrigin: true,
    pathRewrite: { '^/ollama': '' },
    on: {
      proxyReq(proxyReq) {
        proxyReq.removeHeader('origin')
      },
    },
  }),
)
```

## LAN vs local

- For local dev: keep `VITE_OLLAMA_HOST` on `127.0.0.1` and proxy from the app server.
- To expose Ollama directly on the network, bind `OLLAMA_HOST=0.0.0.0:11434` and secure access (firewall).
