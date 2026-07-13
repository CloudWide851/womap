import type { BackendLayerSummary } from '../../types/imports';
import type {
  GeometryType,
  WorkspaceField,
  WorkspaceFieldType,
  WorkspaceLayer,
} from '../../types/workspace';

export function normalizeBackendLayer(layer: BackendLayerSummary): WorkspaceLayer {
  return {
    id: String(layer.id),
    name: layer.name,
    geometryType: normalizeGeometryType(layer.geometry_type),
    featureCount: layer.feature_count,
    visible: layer.visible,
    locked: layer.locked,
    opacity: layer.opacity,
    color: layer.style.color ?? '#4656a8',
    fields: layer.fields.map(normalizeField),
    performance: {
      featureCount: layer.feature_count,
      largeLayer: layer.performance.large_layer,
      indexed: layer.performance.indexed,
      recommendedMode: 'bbox',
      warning: layer.performance.warning,
    },
    source: 'backend',
    bounds: layer.bounds,
  };
}

function normalizeGeometryType(value: string): GeometryType {
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
