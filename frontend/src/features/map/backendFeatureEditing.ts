import Feature from 'ol/Feature';
import type Geometry from 'ol/geom/Geometry';
import type VectorSource from 'ol/source/Vector';

export type BackendFeature = Feature<Geometry>;

export function resolveCurrentBackendFeature(
  source: VectorSource<BackendFeature>,
  layerId: string,
  featureId: number,
  fallback: BackendFeature,
) {
  return (
    (source.getFeatureById(`backend:${layerId}:${featureId}`) as BackendFeature | null) ?? fallback
  );
}
