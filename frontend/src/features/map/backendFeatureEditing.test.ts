import Feature from 'ol/Feature';
import Polygon from 'ol/geom/Polygon';
import VectorSource from 'ol/source/Vector';
import { describe, expect, it } from 'vitest';

import {
  resolveCurrentBackendFeature,
  type BackendFeature,
} from './backendFeatureEditing';

function feature(id: string) {
  const item = new Feature({
    geometry: new Polygon([[[0, 0], [10, 0], [0, 10], [0, 0]]]),
  }) as BackendFeature;
  item.setId(id);
  return item;
}

describe('resolveCurrentBackendFeature', () => {
  it('uses the source replacement after a viewport reload', () => {
    const source = new VectorSource<BackendFeature>();
    const stale = feature('backend:7:11');
    const replacement = feature('backend:7:11');
    source.addFeature(stale);
    source.clear(true);
    source.addFeature(replacement);

    expect(resolveCurrentBackendFeature(source, '7', 11, stale)).toBe(replacement);
  });

  it('falls back while the current viewport does not contain the feature', () => {
    const source = new VectorSource<BackendFeature>();
    const fallback = feature('backend:7:11');

    expect(resolveCurrentBackendFeature(source, '7', 11, fallback)).toBe(fallback);
  });
});
