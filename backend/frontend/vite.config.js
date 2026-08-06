import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend target. Local `wrangler dev` runs on 8787; override via env
// when pointing at a deployed worker: VIDRANK_API_BACKEND=https://vidrank-backend.x.workers.dev
const target = process.env.VIDRANK_API_BACKEND || 'http://localhost:8787'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': { target, changeOrigin: true },
      '/admin': { target, changeOrigin: true },
    },
  },
})