export type ImportSourceKind = 'local' | 'smb';
export type ImportDatasetState = 'unimported' | 'imported' | 'changed' | 'interrupted';
export type JobStatusValue = 'queued' | 'running' | 'interrupted' | 'done' | 'failed' | 'unknown';
export type ImportFormat = 'shp' | 'gdb' | 'tif' | 'img' | 'jp2' | 'vrt' | 'hdf' | 'netcdf';
export type DatasetKind = 'vector' | 'raster';

export type RasterFormulaNode =
  | { kind: 'band'; band: number }
  | { kind: 'number'; value: number }
  | { kind: 'unary'; operator: '+' | '-'; argument: RasterFormulaNode }
  | {
      kind: 'binary';
      operator: '+' | '-' | '*' | '/' | '^';
      left: RasterFormulaNode;
      right: RasterFormulaNode;
    }
  | {
      kind: 'function';
      name: 'abs' | 'sqrt' | 'log' | 'min' | 'max' | 'clamp';
      arguments: RasterFormulaNode[];
    };

export interface RasterStyle {
  schema_version: 'womap.raster-style/v1';
  mode: 'rgb' | 'grayscale' | 'classified' | 'formula';
  bands: number[];
  stretch: 'percentile' | 'minmax' | 'none';
  min_values: number[];
  max_values: number[];
  gamma: number;
  nodata_transparent: boolean;
  color_ramp: string;
  class_breaks: number[];
  class_colors: string[];
  formula: RasterFormulaNode | null;
}

export interface RasterBandMetadata {
  index: number;
  name: string;
  dtype: string;
  nodata: number | null;
  color_interpretation: string;
}

export interface RasterMetadata {
  width: number;
  height: number;
  band_count: number;
  driver: string;
  dtypes: string[];
  nodata: Array<number | null>;
  resolution: number[];
  byte_size: number;
  subdataset?: string | null;
  bands: RasterBandMetadata[];
}

export interface RasterLayerMetadata extends RasterMetadata {
  asset_url: string;
  fingerprint: string;
}

export interface ImportSourceProfile {
  id: string;
  name: string;
  kind: ImportSourceKind;
  root_path: string;
  server: string;
  share: string;
  base_path: string;
  username: string;
  domain: string;
  port: number;
  encrypt: boolean;
  enabled: boolean;
  credential_configured: boolean;
}

export type ImportSourceWrite = Omit<ImportSourceProfile, 'id' | 'credential_configured'> & {
  password?: string;
};

export interface ImportSettings {
  cache_path: string;
  batch_size: number;
  raster_store_path: string;
  raster_scratch_path: string;
  raster_quota_gb: number;
  sources: ImportSourceProfile[];
}

export interface CatalogDataset {
  id: string;
  source_id: string;
  format: ImportFormat;
  dataset_kind: DatasetKind;
  container: string;
  relative_path: string;
  layer_name: string;
  geometry_type: string;
  feature_count: number;
  crs: string | null;
  bounds: number[];
  fields: Array<{ name: string; type: string }>;
  raster: RasterMetadata | null;
  fingerprint: string;
  valid: boolean;
  missing_required: string[];
  missing_optional: string[];
  errors: string[];
  import_state: ImportDatasetState;
  resumable_job_id: string | null;
}

export interface ImportCatalog {
  source_id: string;
  scanned_at: string;
  datasets: CatalogDataset[];
  warnings: string[];
}

export interface ImportJobProgressDetail {
  kind: 'import';
  stage: string;
  source_id: string | null;
  dataset_id: string | null;
  dataset_name: string | null;
  current_layer: string | null;
  current_file: string | null;
  imported_features: number;
  total_features: number;
  current_batch: number;
  total_batches: number;
  transferred_bytes: number;
  total_bytes: number;
  warnings: string[];
  error: string | null;
}

export interface RasterJobProgressDetail {
  kind: 'raster-process';
  stage: string;
  operation: 'import' | 'derive';
  source_id: string | null;
  dataset_id: string | null;
  layer_id: number | null;
  dataset_name: string | null;
  processed_bytes: number;
  total_bytes: number;
  processed_blocks: number;
  total_blocks: number;
  phase_timings_ms?: {
    preflight: number;
    read_warp: number | null;
    compute: number | null;
    write_compress: number | null;
    overview: number | null;
    validation: number;
    combined_io: number | null;
    total: number;
    combined_phases: Array<'read_warp' | 'compute' | 'write_compress' | 'overview'>;
  } | null;
  space_estimate_bytes?: {
    source: number;
    candidate_asset: number;
    formula_intermediate: number;
    compression_overview: number;
    final_asset: number;
    scratch_required: number;
    store_required: number;
    reserve: number;
  } | null;
  warnings: string[];
  error: string | null;
}

export interface RasterExportJobProgressDetail {
  kind: 'raster-export';
  stage: string;
  processed_layers: number;
  total_layers: number;
  artifact_name: string | null;
  warnings: string[];
  error: string | null;
}

export interface VectorExportJobProgressDetail {
  kind: 'vector-export';
  stage: string;
  processed_layers: number;
  total_layers: number;
  artifact_name: string | null;
  warnings: string[];
  error: string | null;
}

export interface WorkspacePackageJobProgressDetail {
  kind: 'workspace-package';
  stage: string;
  operation: 'export' | 'import';
  workspace_id: number | null;
  current_layer: string | null;
  processed_features: number;
  total_features: number;
  warnings: string[];
  artifact_name: string | null;
  error: string | null;
}

export interface SpatialAnalysisJobProgressDetail {
  kind: 'spatial-analysis';
  stage: string;
  workspace_id: number | null;
  target_feature_id: number | null;
  processed_layers: number;
  total_layers: number;
  matched_features: number;
  warnings: string[];
  error: string | null;
}

export type JobProgressDetail =
  | ImportJobProgressDetail
  | WorkspacePackageJobProgressDetail
  | SpatialAnalysisJobProgressDetail
  | RasterJobProgressDetail
  | RasterExportJobProgressDetail
  | VectorExportJobProgressDetail;

export interface ImportJob {
  id: string;
  job_type: string;
  status: JobStatusValue;
  progress: number;
  message: string | null;
  detail: JobProgressDetail;
}

export interface BackendLayerSummary {
  id: number;
  name: string;
  kind: 'vector' | 'raster';
  geometry_type: string;
  feature_count: number;
  crs: string | null;
  bounds: Record<string, number>;
  visible: boolean;
  locked: boolean;
  opacity: number;
  source_type: string;
  fields: Array<{ name: string; type?: string }>;
  style: { color?: string; raster?: RasterStyle };
  performance: {
    feature_count: number;
    large_layer: boolean;
    indexed: boolean;
    recommended_mode: string;
    warning?: string;
  };
  provenance: {
    source_id: string | null;
    dataset_id: string | null;
    format: string;
    container: string | null;
    relative_path: string | null;
    layer_name: string | null;
    fingerprint: string | null;
  };
  raster: RasterLayerMetadata | null;
}

export interface RasterHistogram {
  layer_id: number;
  band: number;
  bins: number[];
  edges: number[];
  minimum: number | null;
  maximum: number | null;
  percentiles: Record<string, number | null>;
  sample_count: number;
  cache_hit: boolean;
}

export interface RasterPixel {
  layer_id: number;
  x: number;
  y: number;
  crs: string;
  values: Array<number | null>;
  nodata: boolean;
}
