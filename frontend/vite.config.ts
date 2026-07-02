import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

const repoRoot = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  plugins: [react()],
  cacheDir: '../.vite-cache/frontend',
  resolve: {
    alias: [
      {
        find: /^@ant-design\/icons-svg\/es\/asn\/(.+)$/,
        replacement: '@ant-design/icons-svg/lib/asn/$1',
      },
    ],
  },
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
    fs: {
      allow: [repoRoot],
    },
  },
});
