import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import VectorSource from 'ol/source/Vector';
import { describe, expect, it } from 'vitest';

import {
  resolveBrowseSimplifyTolerance,
  updateVectorSourceIncrementally,
} from './viewportSource';

function feature(id: string, x: number, name: string) {
  const value = new Feature({ geometry: new Point([x, x]), name });
  value.setId(id);
  return value;
}

describe('viewport source performance boundary', () => {
  it('keeps stable feature objects while adding updating and removing by id', () => {
    const kept = feature('backend:1:1', 1, 'old');
    const removed = feature('backend:1:2', 2, 'remove');
    const source = new VectorSource({ features: [kept, removed] });

    const result = updateVectorSourceIncrementally(source, [
      feature('backend:1:1', 10, 'updated'),
      feature('backend:1:3', 3, 'added'),
    ]);

    expect(result).toEqual({ added: 1, updated: 1, removed: 1 });
    expect(source.getFeatureById('backend:1:1')).toBe(kept);
    expect(kept.get('name')).toBe('updated');
    expect((kept.getGeometry() as Point).getCoordinates()).toEqual([10, 10]);
    expect(source.getFeatureById('backend:1:2')).toBeNull();
  });

  it('uses half-pixel bounded simplification only in browse mode', () => {
    expect(resolveBrowseSimplifyTolerance('browse', 4, 5)).toBe(2);
    expect(resolveBrowseSimplifyTolerance('browse', 20, 5)).toBe(5);
    expect(resolveBrowseSimplifyTolerance('edit', 20, 5)).toBe(0);
    expect(resolveBrowseSimplifyTolerance('inspect', 20, 5)).toBe(0);
    expect(resolveBrowseSimplifyTolerance('analysis', 20, 5)).toBe(0);
  });
});
