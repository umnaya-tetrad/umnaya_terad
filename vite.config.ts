import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  const apiProxy = {
    '/api': {
      target: env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
      changeOrigin: true
    }
  }

  return {
    plugins: [react()],
    server: {
      // Compose uses backend:8000; local dev and built preview use the host API.
      proxy: apiProxy
    },
    preview: { proxy: apiProxy },
    test: {
      environment: 'node'
    }
  }
})
