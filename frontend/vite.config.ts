import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  cacheDir: '../.vite-cache/frontend',
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          antd: ['antd'],
          map: ['ol'],
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
});
