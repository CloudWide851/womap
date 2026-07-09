export type GeometryType = 'Point' | 'LineString' | 'Polygon' | 'Mixed';
export type BasemapType = 'xyz' | 'wms';
export type AppPageMode = 'workspace' | 'settings';
export type AttributeInspectorKind = 'layer' | 'feature';
export type SessionMode = 'short' | 'long';
export type WorkspaceFieldType = 'string' | 'number' | 'boolean' | 'date';
export type WorkspaceNoticeTone = 'info' | 'success' | 'warning';
export type WorkspaceCommand = 'import-data' | 'save-project' | 'export-results' | 'undo' | 'redo' | 'add-layer';
export type CoordinateCrs = 'EPSG:4326' | 'EPSG:3857' | 'GCJ-02' | 'BD-09';

export interface AttributeInspectorTarget {
  kind: AttributeInspectorKind;
  layerId: string;
  featureId?: string;
}

export interface WorkspaceLayer {
  id: string;
  name: string;
  geometryType: GeometryType;
  featureCount: number;
  visible: boolean;
  locked: boolean;
  opacity: number;
  color: string;
  fields: WorkspaceField[];
  performance: LayerPerformanceState;
}

export interface WorkspaceField {
  name: string;
  alias: string;
  type: WorkspaceFieldType;
  nullable: boolean;
  example: string | number | boolean;
  description: string;
}

export interface WorkspaceNotice {
  id: number;
  tone: WorkspaceNoticeTone;
  title: string;
  detail: string;
}

export interface FeatureAttributePreview {
  id: string;
  layerId: string;
  title: string;
  geometryType: GeometryType;
  area: string;
  perimeter: string;
  bounds: string;
  properties: Record<string, string | number | boolean>;
}

export interface ToolAction {
  key: string;
  label: string;
}

export interface LayerPerformanceState {
  featureCount: number;
  largeLayer: boolean;
  indexed: boolean;
  recommendedMode: 'bbox' | 'tile' | 'table';
  warning?: string;
}

export interface BasemapProvider {
  id: string;
  type: BasemapType;
  name: string;
  urlTemplate: string;
  apiKey: string;
  subdomains: string[];
  enabled: boolean;
  apiKeyConfigured: boolean;
}

export interface CoordinateConversionInput {
  x: string;
  y: string;
  source: CoordinateCrs;
  target: CoordinateCrs;
}

export interface CoordinateConversionResult {
  source: CoordinateCrs;
  target: CoordinateCrs;
  x: number;
  y: number;
  formattedX: string;
  formattedY: string;
  xLabel: string;
  yLabel: string;
  targetLabel: string;
}

export interface CoordinateConversionState {
  input: CoordinateConversionInput;
  result: CoordinateConversionResult | null;
  error: string | null;
}

export interface ImagerySwipeState {
  enabled: boolean;
  beforeBasemapId: string;
  afterBasemapId: string;
  position: number;
}

export interface PanelLayoutSettings {
  layers: boolean;
  basemaps: boolean;
  jobs: boolean;
  properties: boolean;
  fields: boolean;
  performance: boolean;
}

export interface FeatureQueryMeta {
  limit: number;
  returned: number;
  truncated: boolean;
  warning?: string;
  bbox?: [number, number, number, number];
  simplify?: number;
  cacheHit: boolean;
  strategy: string;
}

export interface MapRuntimeState {
  coordinate: [number, number];
  zoom: number;
  scale: string;
  crs: string;
  selectedBasemapId: string;
  coordinateConversion: CoordinateConversionState;
  imagerySwipe: ImagerySwipeState;
}

export interface JobState {
  id: string;
  jobType: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'unknown';
  progress: number;
  message?: string;
}

export interface LoginSecurityPolicy {
  username: string;
  passwordMinLength: number;
  passwordMaxLength: number;
  lockoutAttempts: number;
  lockoutWindowMinutes: number;
  idleTimeoutMinutes: number;
  absoluteTimeoutHours: number;
  renewalTimeoutMinutes: number;
  rememberMeDays: number;
  policyRefreshSeconds: number;
  warnBeforeExpireMinutes: number;
  secureCookie: boolean;
  httpOnlyCookie: boolean;
  sameSite: 'lax' | 'strict' | 'none';
  rotateAfterLogin: boolean;
  auditLogging: boolean;
}

export interface AuthSessionState {
  authenticated: boolean;
  username: string | null;
  mode: SessionMode;
  expiresAt: number | null;
  renewalAt: number | null;
  now: number;
  error: string | null;
}
