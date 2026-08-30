import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      // Optional: uncomment to proxy API calls through Vite dev server
      // '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
