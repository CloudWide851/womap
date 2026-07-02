import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const sourceFiles = [
  'src/styles/global.css',
  'src/styles/layout.css',
  'src/main.tsx',
  'src/stores/useWorkspaceStore.ts',
  'src/features/properties/PropertiesPanel.tsx',
];

function readVisualSources() {
  return sourceFiles.map((filePath) => readFileSync(join(process.cwd(), filePath), 'utf8')).join('\n');
}

describe('visual style constraints', () => {
  it('keeps the white workstation direction free of decorative gradients', () => {
    expect(readVisualSources()).not.toMatch(/(?:linear|radial|repeating-linear)-gradient/);
  });

  it('does not reintroduce the previous green and teal visual system', () => {
    expect(readVisualSources()).not.toMatch(/green|teal|emerald|#256f5d|rgba\(15,\s*111|rgba\(34,\s*95|rgba\(42,\s*81/i);
  });
});
