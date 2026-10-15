import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))

// Built assets are served by the ClassAid Flask app from src/classaid/static/dist/
// (Flask's static URL /static/).  Flask templates resolve hashed file names through
// the manifest (src/classaid/assets.py).  During development, set
// CLASSAID_VITE_DEV_SERVER=http://localhost:5173 for Flask to load modules from
// `pnpm dev` instead (Vite "backend integration"; pages and API stay on Flask's origin).
export default defineConfig({
  plugins: [vue()],
  base: '/static/dist/',
  server: {
    port: 5173,
    strictPort: true,
    cors: true,
    origin: 'http://localhost:5173',
  },
  build: {
    outDir: resolve(root, '../src/classaid/static/dist'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        styleguide: resolve(root, 'src/styleguide/main.ts'),
        workspace: resolve(root, 'src/workspace/main.ts'),
        modes: resolve(root, 'src/modes/main.ts'),
      },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
