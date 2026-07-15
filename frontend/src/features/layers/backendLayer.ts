import type { BackendLayerSummary } from '../../types/imports';
import type {
  GeometryType,
  WorkspaceField,
  WorkspaceFieldType,
  WorkspaceLayer,
} from '../../types/workspace';

export function normalizeBackendLayer(layer: BackendLayerSummary): WorkspaceLayer {
  const rasterStyle = layer.style.raster ?? (layer.kind === 'raster'
    ? {
        schema_version: 'womap.raster-style/v1' as const,
        mode: (layer.raster?.band_count ?? 0) >= 3 ? 'rgb' as const : 'grayscale' as const,
        bands: (layer.raster?.band_count ?? 0) >= 3 ? [1, 2, 3] : [1],
        stretch: 'percentile' as const,
        min_values: [],
        max_values: [],
        gamma: 1,
        nodata_transparent: true,
        color_ramp: 'magma',
        class_breaks: [],
        class_colors: [],
        formula: null,
      }
    : undefined);
  return {
    id: String(layer.id),
    name: layer.name,
    geometryType: normalizeGeometryType(layer.geometry_type),
    featureCount: layer.feature_count,
    visible: layer.visible,
    locked: layer.locked,
    opacity: layer.opacity,
    color: layer.kind === 'raster' ? '#a66a18' : layer.style.color ?? '#4656a8',
    fields: layer.fields.map(normalizeField),
    performance: {
      featureCount: layer.feature_count,
      largeLayer: layer.performance.large_layer,
      indexed: layer.performance.indexed,
      recommendedMode: layer.kind === 'raster' ? 'cog-range' : 'bbox',
      warning: layer.performance.warning,
    },
    source: 'backend',
    bounds: layer.bounds,
    kind: layer.kind,
    raster: layer.raster,
    rasterStyle,
  };
}

function normalizeGeometryType(value: string): GeometryType {
  if (value === 'Raster') return 'Raster';
  if (value.includes('Point')) return 'Point';
  if (value.includes('Line')) return 'LineString';
  if (value.includes('Polygon')) return 'Polygon';
  return 'Mixed';
}

function normalizeField(field: { name: string; type?: string }): WorkspaceField {
  const rawType = field.type?.toLowerCase() ?? 'string';
  const type: WorkspaceFieldType = rawType.includes('int') || rawType.includes('float')
    ? 'number'
    : rawType.includes('bool')
      ? 'boolean'
      : rawType.includes('date') || rawType.includes('time')
        ? 'date'
        : 'string';
  return {
    name: field.name,
    alias: field.name,
    type,
    nullable: true,
    example: '',
    description: '导入字段',
  };
}
