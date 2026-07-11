export type ImportSourceKind = 'local' | 'smb';
export type ImportDatasetState = 'unimported' | 'imported' | 'changed' | 'interrupted';
export type JobStatusValue = 'queued' | 'running' | 'interrupted' | 'done' | 'failed' | 'unknown';

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
  sources: ImportSourceProfile[];
}

export interface CatalogDataset {
  id: string;
  source_id: string;
  format: 'shp' | 'gdb';
  container: string;
  relative_path: string;
  layer_name: string;
  geometry_type: string;
  feature_count: number;
  crs: string | null;
  bounds: number[];
  fields: Array<{ name: string; type: string }>;
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

export interface JobProgressDetail {
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

export interface ImportJob {
  id: string;
  job_type: string;
  status: JobStatusValue;
  progress: number;
  message: string | null;
  detail: JobProgressDetail;
  result: Record<string, unknown>;
}

export interface BackendLayerSummary {
  id: number;
  name: string;
  geometry_type: string;
  feature_count: number;
  crs: string | null;
  bounds: Record<string, number>;
  visible: boolean;
  locked: boolean;
  opacity: number;
  source_type: string;
  fields: Array<{ name: string; type?: string }>;
  style: { color?: string };
  performance: {
    feature_count: number;
    large_layer: boolean;
    indexed: boolean;
    recommended_mode: string;
    warning?: string;
  };
}
