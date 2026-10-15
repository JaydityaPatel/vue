import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { cpSync, createReadStream, existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Connect } from 'vite';

function copyPyodideAssets() {
  return {
    name: 'copy-pyodide-assets',
    configureServer(server: { middlewares: { use: (path: string, handler: Connect.NextHandleFunction) => void } }) {
      server.middlewares.use('/pyodide', (request, response, next) => {
        const path = request.url?.split('?')[0] ?? '';
        if (!/^\/(pyodide\.mjs|pyodide\.asm\.js|pyodide\.asm\.wasm|python_stdlib\.zip|pyodide-lock\.json)$/.test(path)) return next();
        const file = resolve('node_modules/pyodide', path.slice(1));
        if (!existsSync(file)) return next();
        response.setHeader('Content-Type', path.endsWith('.wasm') ? 'application/wasm' : path.endsWith('.zip') ? 'application/zip' : path.endsWith('.json') ? 'application/json' : 'text/javascript');
        return createReadStream(file).pipe(response);
      });
    },
    closeBundle() {
      const source = resolve('node_modules/pyodide');
      const target = resolve('dist/pyodide');
      mkdirSync(target, { recursive: true });
      for (const file of ['pyodide.mjs', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
        if (existsSync(resolve(source, file))) cpSync(resolve(source, file), resolve(target, file));
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), copyPyodideAssets()],
  worker: { format: 'es' },
  optimizeDeps: { exclude: ['pyodide'] },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', css: true },
});
