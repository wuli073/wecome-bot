import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

function resolveApiBaseUrl(mode: string) {
  const env = loadEnv(mode, process.cwd(), '');
  const apiBaseUrl = env.VITE_API_BASE_URL?.trim();

  if (!apiBaseUrl) {
    if (mode !== 'development') {
      return undefined;
    }
    throw new Error('Missing VITE_API_BASE_URL. Configure it in web/.env.');
  }

  let parsed: URL;
  try {
    parsed = new URL(apiBaseUrl);
  } catch {
    throw new Error(`Invalid VITE_API_BASE_URL: ${apiBaseUrl}`);
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`VITE_API_BASE_URL must use http or https: ${apiBaseUrl}`);
  }

  return parsed.origin;
}

export default defineConfig(({ mode }) => {
  const apiBaseUrl = resolveApiBaseUrl(mode);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: apiBaseUrl
      ? {
          port: 3000,
          strictPort: true,
          proxy: {
            '/api': {
              target: apiBaseUrl,
              changeOrigin: false,
            },
          },
        }
      : {
          port: 3000,
          strictPort: true,
        },
    build: {
      outDir: 'dist',
    },
  };
});
