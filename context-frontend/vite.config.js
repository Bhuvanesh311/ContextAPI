import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser calls /backend/* on the dev server, which forwards to FastAPI.
// Same origin in the browser, so the backend needs no CORS setup.
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/backend': {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/backend/, ''),
      },
    },
  },
})
