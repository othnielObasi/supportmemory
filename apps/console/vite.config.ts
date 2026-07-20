import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        product: resolve(__dirname, 'index.html'),
        capabilities: resolve(__dirname, 'capabilities.html'),
        architecture: resolve(__dirname, 'architecture.html'),
        security: resolve(__dirname, 'security.html'),
        login: resolve(__dirname, 'login.html'),
        privacy: resolve(__dirname, 'privacy.html'),
        terms: resolve(__dirname, 'terms.html'),
        notFound: resolve(__dirname, '404.html'),
        workspace: resolve(__dirname, 'workspace.html'),
        knowledge: resolve(__dirname, 'knowledge.html'),
        integrations: resolve(__dirname, 'integrations.html'),
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
  },
});
