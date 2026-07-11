import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, URL } from 'node:url';

const repoRoot = fileURLToPath(new URL('..', import.meta.url));

function getWorkspaceConfigPath() {
  const localPath = resolve(repoRoot, 'config/settings.local.yaml');
  if (existsSync(localPath)) {
    return localPath;
  }
  return resolve(repoRoot, 'config/settings.example.yaml');
}

function cleanYamlScalar(value: string) {
  const text = value.trim();
  if (
    ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) &&
    text.length >= 2
  ) {
    return text.slice(1, -1);
  }
  return text;
}

function readYamlScalar(path: string, fallback: string) {
  const configPath = getWorkspaceConfigPath();
  if (!existsSync(configPath)) {
    return fallback;
  }

  const target = path.split('.');
  const stack = new Map<number, string>();
  const lines = readFileSync(configPath, 'utf8').split(/\r?\n/);

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+#.*$/, '');
    if (!line.trim()) {
      continue;
    }
    const match = /^(\s*)([^:\s][^:]*):\s*(.*)$/.exec(line);
    if (!match) {
      continue;
    }

    const indent = match[1].length;
    const key = match[2].trim();
    const value = match[3].trim();
    const level = Math.floor(indent / 2);
    stack.set(level, key);
    for (const existingLevel of Array.from(stack.keys())) {
      if (existingLevel > level) {
        stack.delete(existingLevel);
      }
    }

    const parts = Array.from({ length: level + 1 }, (_, index) => stack.get(index)).filter(Boolean);
    if (parts.join('.') === target.join('.') && value) {
      return cleanYamlScalar(value);
    }
  }

  return fallback;
}

function readYamlPort(path: string, fallback: number) {
  const rawValue = readYamlScalar(path, String(fallback));
  const parsed = Number.parseInt(rawValue, 10);
  if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535) {
    return parsed;
  }
  return fallback;
}

const devServerHost = readYamlScalar('frontend.dev_server.host', '127.0.0.1');
const devServerPort = readYamlPort('frontend.dev_server.port', 5173);
const configuredApiHost = readYamlScalar('server.host', '127.0.0.1');
const apiHost = ['0.0.0.0', '::'].includes(configuredApiHost) ? '127.0.0.1' : configuredApiHost;
const apiPort = readYamlPort('server.port', 8000);
const apiBaseUrl = process.env.VITE_API_BASE_URL?.trim() || `http://${apiHost}:${apiPort}`;

export default defineConfig({
  plugins: [react()],
  cacheDir: '../.vite-cache/frontend',
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl),
  },
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
    host: devServerHost,
    port: devServerPort,
    strictPort: true,
    fs: {
      allow: [repoRoot],
    },
  },
});
