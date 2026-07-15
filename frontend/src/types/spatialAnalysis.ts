import type { BackendLayerSummary, ImportJob } from './imports';

export type AnalysisUnit = 'm' | 'km' | 'ft' | 'mi';
export type AnalysisScope = 'all' | 'visible';

export interface RealMapFeatureDetail {
  id: number;
  layer_id: number;
  source_feature_id: string | null;
  geometry: { type: string; coordinates: unknown } | null;
  properties: Record<string, unknown>;
  bbox: Record<string, number>;
  area: number | null;
  perimeter: number | null;
  revision: number;
  layer: BackendLayerSummary;
}

export interface SpatialAnalysisLayerSummary {
  layer_id: number;
  layer_name: string;
  geometry_type: string;
  exists: boolean;
  hit_count: number;
  nearest_distance_m: number | null;
  direct_intersection_count: number;
  buffer_intersection_count: number;
  direct_area_sqm: number;
  buffer_area_sqm: number;
  direct_length_m: number;
  buffer_length_m: number;
  point_hit_count: number;
  coverage_ratio: number | null;
}

export interface SpatialAnalysisDatasetSummary {
  key: string;
  name: string;
  source_type: string;
  layers: SpatialAnalysisLayerSummary[];
}

export interface SpatialAnalysisResult {
  job: ImportJob;
  workspace_id: number;
  target_layer_id: number;
  target_feature_id: number;
  distance: number;
  unit: AnalysisUnit;
  distance_meters: number;
  scope: AnalysisScope;
  target_geometry: Record<string, unknown> | null;
  buffer_geometry: Record<string, unknown> | null;
  groups: SpatialAnalysisDatasetSummary[];
  stale: boolean;
  warnings: string[];
}

export interface SpatialAnalysisHit {
  layer_id: number;
  layer_name: string;
  feature_id: number;
  source_feature_id: string | null;
  label: string;
  geometry_type: string;
  direct_intersection: boolean;
  buffer_intersection: boolean;
  distance_m: number;
  intersection_area_sqm: number;
  intersection_length_m: number;
  properties: Record<string, unknown>;
  geometry: Record<string, unknown> | null;
}

export interface SpatialAnalysisHitPage {
  items: SpatialAnalysisHit[];
  next_cursor: string | null;
  has_more: boolean;
  stale: boolean;
  warnings: string[];
}
