import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('frontend startup configuration', () => {
  it('uses the native Vite config loader to avoid Windows realpath spawn failures', () => {
    const packageJson = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf8')) as {
      scripts: Record<string, string>;
    };

    expect(packageJson.scripts.dev).toContain('--configLoader native');
    expect(packageJson.scripts.test).toContain('--configLoader native');
    expect(packageJson.scripts.build).toContain('--configLoader native');
  });

  it('passes launcher Web host and port without a literal separator argument', () => {
    const launcher = readFileSync(join(process.cwd(), '..', 'scripts', 'launcher.ps1'), 'utf8');

    expect(launcher).toContain('pnpm dev --host {0} --port {1}');
    expect(launcher).toContain('taskkill.exe /PID $RootProcessId /T /F');
    expect(launcher).toContain('stopped orphan listener pid={0}');
    expect(launcher).toContain('function Start-DevelopmentServices');
    expect(launcher).toContain('"dev" { return (Start-DevelopmentServices) }');
    expect(launcher).toContain('Stop-CapturedProcessTree -CapturedProcess $launchedProcess');
    expect(launcher).not.toContain('pnpm dev -- --host');
  });

  it('keeps a local drawing cursor with a keyword fallback', () => {
    const layoutCss = readFileSync(join(process.cwd(), 'src', 'styles', 'layout.css'), 'utf8');
    const cursorSvg = readFileSync(
      join(process.cwd(), 'public', 'cursors', 'draw-pen.svg'),
      'utf8',
    );

    expect(layoutCss).toContain('url("/cursors/draw-pen.svg") 4 20, crosshair');
    expect(cursorSvg).toContain('<svg');
  });

  it('keeps Vite bound to the configured frontend dev server port', () => {
    const viteConfig = readFileSync(join(process.cwd(), 'vite.config.ts'), 'utf8');
    const vitestConfig = readFileSync(join(process.cwd(), 'vitest.config.ts'), 'utf8');

    expect(viteConfig).toContain("readYamlScalar('frontend.dev_server.host'");
    expect(viteConfig).toContain("readYamlPort('frontend.dev_server.port'");
    expect(viteConfig).toContain("readYamlScalar('server.host'");
    expect(viteConfig).toContain("readYamlPort('server.port'");
    expect(viteConfig).toContain("'import.meta.env.VITE_API_BASE_URL'");
    expect(viteConfig).toContain('strictPort: true');
    expect(vitestConfig).toContain('preserveSymlinks: true');
    expect(vitestConfig).toContain("pool: 'threads'");
  });
});
