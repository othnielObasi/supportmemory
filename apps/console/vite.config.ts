import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        product: resolve(__dirname, 'index.html'),
        workspace: resolve(__dirname, 'workspace.html'),
        knowledge: resolve(__dirname, 'knowledge.html'),
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
  },
});
