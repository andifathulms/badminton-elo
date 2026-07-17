import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During dev, proxy /api to the Django server so there are no CORS surprises.
// In Docker/prod, set VITE_API_BASE to the API origin at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
