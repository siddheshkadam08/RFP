import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        // Use 127.0.0.1 (not localhost): uvicorn binds IPv4 only, but Node resolves
        // "localhost" to IPv6 ::1 first on Windows, which fails with ECONNREFUSED.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
