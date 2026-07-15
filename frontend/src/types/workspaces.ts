import type { BackendLayerSummary, ImportJob, RasterStyle } from './imports';

export type WorkspaceFeatureSelectionMode = 'all' | 'include';

export interface WorkspaceFeatureSelection {
  mode: WorkspaceFeatureSelectionMode;
  feature_ids: number[];
  source_feature_ids: string[];
}

export interface WorkspaceLayerConfig {
  layer_id: number;
  dataset_id: string | null;
  visible: boolean;
  opacity: number;
  order: number;
  selection: WorkspaceFeatureSelection;
  raster_style?: RasterStyle | null;
}

export interface WorkspaceMapView {
  center: [number, number];
  zoom: number;
}

export interface WorkspaceSummary {
  id: number;
  name: string;
  description: string;
  default_basemap: string;
  revision: number;
  layer_count: number;
  is_default: boolean;
  updated_at: string | null;
}

export interface WorkspaceLayerState {
  config: WorkspaceLayerConfig;
  layer: BackendLayerSummary;
}

export interface WorkspaceDetail extends WorkspaceSummary {
  schema_version: 'womap.workspace/v1';
  workspace_uuid: string;
  view: WorkspaceMapView;
  layers: WorkspaceLayerState[];
  warnings: string[];
}

export interface WorkspaceWrite {
  name: string;
  description: string;
  default_basemap: string;
  view: WorkspaceMapView;
  layers: WorkspaceLayerConfig[];
}

export interface WorkspaceUpdate extends WorkspaceWrite {
  revision: number;
}

export interface WorkspaceCatalogGroup {
  key: string;
  label: string;
  format: string;
  source_id: string | null;
  container: string | null;
  layers: BackendLayerSummary[];
}

export interface WorkspaceCatalog {
  groups: WorkspaceCatalogGroup[];
}

export interface MapFeatureSummary {
  id: number;
  layer_id: number;
  source_feature_id: string | null;
  label: string;
  properties: Record<string, unknown>;
}

export interface MapFeatureSummaryPage {
  items: MapFeatureSummary[];
  next_cursor: string | null;
  has_more: boolean;
  returned: number;
}

export interface WorkspacePackagePreview {
  upload_token: string;
  workspace_name: string;
  workspace_uuid: string;
  revision: number;
  package_version: string;
  layer_count: number;
  feature_count: number;
  basemap: { id: string; name: string; type: string };
  basemap_missing: boolean;
  conflicting_workspace_id: number | null;
  warnings: string[];
}

export type WorkspacePackageJob = ImportJob;
