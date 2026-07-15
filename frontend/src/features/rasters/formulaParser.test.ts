import { describe, expect, it } from 'vitest';

import {
  formatRasterFormula,
  parseRasterFormula,
  supportsRasterWebGLPreview,
} from './formulaParser';

describe('parseRasterFormula', () => {
  it('builds a tagged AST for NDVI-style arithmetic', () => {
    expect(parseRasterFormula('(B4-B3)/(B4+B3)')).toMatchObject({
      kind: 'binary',
      operator: '/',
      left: { kind: 'binary', operator: '-' },
      right: { kind: 'binary', operator: '+' },
    });
  });

  it('supports bounded functions and rejects arbitrary code', () => {
    expect(parseRasterFormula('clamp(B1, 0, 1)')).toMatchObject({
      kind: 'function',
      name: 'clamp',
    });
    expect(() => parseRasterFormula('window.alert(1)')).toThrow();
    expect(() => parseRasterFormula('min(B1)')).toThrow('2 个参数');
  });

  it('formats persisted formulas and reports WebGL-only limitations', () => {
    const formula = parseRasterFormula('sqrt(abs(B2-B1))');
    expect(formatRasterFormula(formula)).toBe('sqrt(abs((B2-B1)))');
    expect(supportsRasterWebGLPreview(formula)).toBe(true);
    expect(supportsRasterWebGLPreview(parseRasterFormula('log(B1)'))).toBe(false);
  });
});
