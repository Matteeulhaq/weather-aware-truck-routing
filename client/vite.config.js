import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Production: Django serves the built app under /static/ (WhiteNoise).
  base: '/static/',
  server: {
    // Same-origin API in dev — the production deployment serves both from
    // one Django process, so no CORS configuration is needed anywhere.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
