import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load environment variables for dev or production
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000' // fallback for local dev

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(process.cwd(), 'src'),
      },
    },
    // Dev server configuration only
    server: mode === 'development' ? {
      port: 3001,
      proxy: {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
        },
      },
    } : undefined,
  }
})
