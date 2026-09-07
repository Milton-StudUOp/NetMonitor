import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3389,
    strictPort: true,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5555',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:5555',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            // Ignore transient disconnect errors when backend reloads
          });
        },
      },
    },
  },
})
