import type Feature from 'ol/Feature';
import type Geometry from 'ol/geom/Geometry';
import type VectorSource from 'ol/source/Vector';

import type { WorkspaceMode } from '../../types/workspace';

export interface SourceUpdateResult {
  added: number;
  updated: number;
  removed: number;
}

export function resolveBrowseSimplifyTolerance(
  mode: WorkspaceMode,
  resolution: number,
  maxTolerance: number,
) {
  if (mode !== 'browse') return 0;
  return Math.min(Math.max(0, maxTolerance), Math.max(0, resolution) * 0.5);
}

export function updateVectorSourceIncrementally(
  source: VectorSource<Feature<Geometry>>,
  incoming: Feature<Geometry>[],
): SourceUpdateResult {
  const incomingIds = new Set(incoming.map((feature) => String(feature.getId())));
  let removed = 0;
  for (const existing of source.getFeatures()) {
    if (!incomingIds.has(String(existing.getId()))) {
      source.removeFeature(existing);
      removed += 1;
    }
  }

  let added = 0;
  let updated = 0;
  for (const feature of incoming) {
    const id = feature.getId();
    const existing = id === undefined ? null : source.getFeatureById(id);
    if (!existing) {
      source.addFeature(feature);
      added += 1;
      continue;
    }
    const geometryName = existing.getGeometryName();
    const properties = feature.getProperties();
    for (const key of existing.getKeys()) {
      if (key !== geometryName && !(key in properties)) existing.unset(key, true);
    }
    existing.setProperties(properties, true);
    existing.setGeometry(feature.getGeometry());
    updated += 1;
  }
  return { added, updated, removed };
}
