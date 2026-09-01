import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8010',
      '/ws': {
        target: 'ws://localhost:8010',
        ws: true,
      },
    },
  },
})