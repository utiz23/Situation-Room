import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // In dev, Vite proxies /api/* to the Go server so the browser
      // doesn't run into CORS issues (same origin from the browser's POV).
      '/api': 'http://localhost:8080',

      // WebSocket proxy — Vite forwards the WS upgrade to Go.
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
      },
    },
  },
})
