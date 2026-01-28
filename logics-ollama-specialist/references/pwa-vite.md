# PWA for Vite (React)

## Steps

1) Add dependency:

```bash
npm install -D vite-plugin-pwa
```

2) Configure `vite.config.ts`:

```ts
import { VitePWA } from 'vite-plugin-pwa'

plugins: [
  react(),
  VitePWA({
    registerType: 'autoUpdate',
    includeAssets: ['apple-touch-icon.png', 'pwa-192x192.png', 'pwa-512x512.png'],
    manifest: {
      name: 'App Name',
      short_name: 'App',
      theme_color: '#0b0f17',
      background_color: '#0b0f17',
      display: 'standalone',
      start_url: '/',
      icons: [
        { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
      ],
    },
  }),
]
```

3) Register the service worker in `src/main.tsx`:

```ts
import { registerSW } from 'virtual:pwa-register'
registerSW({ immediate: true })
```

4) Add icons in `public/` and set `theme-color` in `index.html`.

## Notes

- Service workers require a secure context: OK on `http://localhost` / `http://127.0.0.1`, not on plain `http://192.168.x.x`.
