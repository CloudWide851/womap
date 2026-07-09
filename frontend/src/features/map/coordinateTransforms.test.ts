import { describe, expect, it } from 'vitest';

import { convertCoordinate } from './coordinateTransforms';

describe('coordinateTransforms', () => {
  it('converts WGS84 longitude and latitude to Web Mercator meters', () => {
    const result = convertCoordinate({
      x: '113.2644',
      y: '23.1291',
      source: 'EPSG:4326',
      target: 'EPSG:3857',
    });

    expect(result.targetLabel).toBe('Web Mercator 米');
    expect(result.x).toBeCloseTo(12608535, 0);
    expect(result.y).toBeCloseTo(2647639, 0);
    expect(result.formattedX).toMatch(/\d+\.\d{2}/);
  });

  it('round-trips Web Mercator back to WGS84', () => {
    const projected = convertCoordinate({
      x: '113.2644',
      y: '23.1291',
      source: 'EPSG:4326',
      target: 'EPSG:3857',
    });
    const wgs84 = convertCoordinate({
      x: String(projected.x),
      y: String(projected.y),
      source: 'EPSG:3857',
      target: 'EPSG:4326',
    });

    expect(wgs84.x).toBeCloseTo(113.2644, 6);
    expect(wgs84.y).toBeCloseTo(23.1291, 6);
  });

  it('supports GCJ-02 and BD-09 web map coordinate offsets', () => {
    const gcj = convertCoordinate({
      x: '113.2644',
      y: '23.1291',
      source: 'EPSG:4326',
      target: 'GCJ-02',
    });
    const bd = convertCoordinate({
      x: String(gcj.x),
      y: String(gcj.y),
      source: 'GCJ-02',
      target: 'BD-09',
    });

    expect(gcj.x).not.toBeCloseTo(113.2644, 5);
    expect(gcj.y).not.toBeCloseTo(23.1291, 5);
    expect(bd.x).toBeGreaterThan(gcj.x);
    expect(bd.y).toBeGreaterThan(gcj.y);
  });

  it('rejects invalid coordinate input with a useful message', () => {
    expect(() =>
      convertCoordinate({
        x: 'not-a-number',
        y: '23.1291',
        source: 'EPSG:4326',
        target: 'EPSG:3857',
      }),
    ).toThrow('请输入有效的经度数值');
  });
});
