import type { BasemapProvider, FeatureQueryMeta } from '../types/workspace';
import type {
  BackendLayerSummary,
  ImportCatalog,
  ImportJob,
  ImportSettings,
  ImportSourceProfile,
  ImportSourceWrite,
  RasterFormulaNode,
  RasterHistogram,
  RasterPixel,
  RasterStyle,
} from '../types/imports';
import type {
  MapFeatureSummaryPage,
  WorkspaceCatalog,
  WorkspaceDetail,
  WorkspacePackagePreview,
  WorkspaceSummary,
  WorkspaceUpdate,
  WorkspaceWrite,
} from '../types/workspaces';
import type { CapabilityStatus, PerformanceCapabilitySummary } from '../types/performance';
import type {
  AnalysisScope,
  AnalysisUnit,
  RealMapFeatureDetail,
  SpatialAnalysisHitPage,
  SpatialAnalysisResult,
} from '../types/spatialAnalysis';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '';
type ExportFormat = 'shp' | 'gdb';
export const AUTH_UNAUTHORIZED_EVENT = 'womap:auth-unauthorized';

let csrfCookieName = 'womap_session_csrf';

function cookieValue(name: string) {
  if (typeof document === 'undefined') return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split('; ').find((entry) => entry.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

export function configureCsrfCookie(sessionCookieName: string) {
  csrfCookieName = `${sessionCookieName}_csrf`;
}

export function hasAuthSessionHint() {
  return Boolean(cookieValue(csrfCookieName));
}

export function clearAuthSessionHint(secureCookie: boolean, sameSite: 'lax' | 'strict' | 'none') {
  if (typeof document === 'undefined') return;
  const secure = secureCookie ? '; Secure' : '';
  document.cookie = `${encodeURIComponent(csrfCookieName)}=; Max-Age=0; Path=/; SameSite=${sameSite}${secure}`;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers.has('X-WOMAP-CSRF')) {
    const csrfToken = cookieValue(csrfCookieName);
    if (csrfToken) headers.set('X-WOMAP-CSRF', csrfToken);
  }

  const response = await globalThis.fetch(input, {
    ...init,
    credentials: 'include',
    headers,
  });
  const requestUrl = String(input);
  if (
    response.status === 401 &&
    !requestUrl.includes('/api/v1/auth/') &&
    typeof window !== 'undefined'
  ) {
    window.dispatchEvent(new CustomEvent(AUTH_UNAUTHORIZED_EVENT));
  }
  return response;
}

export function resolveApiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

async function apiError(response: Response, fallback: string) {
  let detail = `${fallback}（${response.status}）`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    // Keep the status fallback for non-JSON responses.
  }
  return new ApiRequestError(detail, response.status);
}

export interface AuthPolicyApiResponse {
  enabled: boolean;
  username: string;
  credential_configured: boolean;
  password_min_length: number;
  password_max_length: number;
  block_common_passwords: boolean;
  lockout_attempts: number;
  lockout_window_minutes: number;
  idle_timeout_minutes: number;
  absolute_timeout_hours: number;
  renewal_timeout_minutes: number;
  remember_me_days: number;
  cookie_name: string;
  secure_cookie: boolean;
  http_only_cookie: boolean;
  same_site: 'lax' | 'strict' | 'none';
  policy_refresh_seconds: number;
  warn_before_expire_minutes: number;
  rotate_after_login: boolean;
  audit_logging: boolean;
  redact_session_id: boolean;
}

export interface AuthSessionApiResponse {
  authenticated: boolean;
  username: string;
  session_mode: 'short' | 'long';
  expires_in_seconds: number;
  renewal_in_seconds: number;
  policy_refresh_seconds: number;
  message: string;
}

export async function getAuthPolicy() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/policy`);
  if (!response.ok) throw await apiError(response, '登录策略加载失败');
  return response.json() as Promise<AuthPolicyApiResponse>;
}

export async function getAuthSession() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/session`);
  if (!response.ok) throw await apiError(response, '登录会话无效');
  return response.json() as Promise<AuthSessionApiResponse>;
}

export async function loginAuth(username: string, password: string, sessionMode: 'short' | 'long') {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, session_mode: sessionMode }),
  });
  if (!response.ok) throw await apiError(response, '登录失败');
  return response.json() as Promise<AuthSessionApiResponse>;
}

export async function setupAuth(
  username: string,
  password: string,
  passwordConfirmation: string,
  sessionMode: 'short' | 'long',
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      password_confirmation: passwordConfirmation,
      session_mode: sessionMode,
    }),
  });
  if (!response.ok) throw await apiError(response, '本地密码设置失败');
  return response.json() as Promise<AuthSessionApiResponse>;
}

export async function renewAuthSession() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/renew`, { method: 'POST' });
  if (!response.ok) throw await apiError(response, '会话续期失败');
  return response.json() as Promise<AuthSessionApiResponse>;
}

export async function logoutAuth() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/auth/logout`, { method: 'POST' });
  if (!response.ok) throw await apiError(response, '退出登录失败');
}

export interface LocalRuntimeSettingsUpdate {
  server: {
    host: string;
    port: number;
  };
  frontend: {
    dev_server: {
      host: string;
      port: number;
    };
  };
}

export interface LocalRuntimeSettings extends LocalRuntimeSettingsUpdate {
  config_source: string;
  local_config_path: string;
}

export async function getHealth() {
  const response = await apiFetch(`${apiBaseUrl}/health/live`);
  if (!response.ok) {
    throw new Error('服务状态检查失败');
  }
  return response.json() as Promise<{
    status: string;
  }>;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function finiteNumber(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function nullableNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function capabilityStatus(value: unknown): CapabilityStatus {
  return ['available', 'unavailable', 'restricted', 'unknown'].includes(String(value))
    ? (value as CapabilityStatus)
    : 'unknown';
}

export function decodePerformanceCapabilities(value: unknown): PerformanceCapabilitySummary {
  const root = recordValue(value);
  const system = recordValue(root.system);
  const cpu = recordValue(system.cpu);
  const memory = recordValue(system.memory);
  const runtime = recordValue(root.runtime);
  const profile = recordValue(runtime.profile);
  const software = recordValue(root.software);
  const cupy = recordValue(software.cupy);
  const queue = recordValue(root.queue);
  const recommendations = Array.isArray(root.recommendations) ? root.recommendations : [];
  const warning = recommendations
    .map(recordValue)
    .find((item) => item.severity === 'warning');
  const gpus = Array.isArray(root.gpus) ? root.gpus.map(recordValue) : [];
  const firstGpu = gpus[0];
  const gpuName = typeof firstGpu?.name === 'string' ? firstGpu.name : null;
  const resolvedProfile = ['low', 'balanced', 'high'].includes(String(profile.resolved_profile))
    ? (profile.resolved_profile as 'low' | 'balanced' | 'high')
    : 'low';
  const requestedProfile = ['auto', 'low', 'balanced', 'high'].includes(
    String(profile.requested_profile),
  )
    ? (profile.requested_profile as 'auto' | 'low' | 'balanced' | 'high')
    : 'auto';

  return {
    profile: {
      requested: requestedProfile,
      resolved: resolvedProfile,
      enforcement: 'diagnostic',
      gdalThreads: finiteNumber(profile.gdal_threads, 1),
      gdalCacheMiB: finiteNumber(profile.gdal_cache_mib, 128),
    },
    runtimeMode: runtime.mode === 'production' ? 'production' : 'development',
    cpuLogicalCores: Math.max(1, finiteNumber(cpu.logical_cores, 1)),
    totalMemoryBytes: nullableNumber(memory.total_bytes),
    availableMemoryBytes: nullableNumber(memory.available_bytes),
    gpu: {
      count: gpus.length,
      label: gpuName ?? (gpus.length > 0 ? `${gpus.length} 个 GPU` : '未检测到'),
      cupyStatus: capabilityStatus(cupy.status),
      executionEnabled: runtime.gpu_execution_enabled === true,
      executionReason:
        typeof runtime.gpu_execution_reason === 'string'
          ? runtime.gpu_execution_reason
          : 'unknown',
    },
    queue: {
      status: capabilityStatus(queue.status),
      queued: nullableNumber(queue.queued),
      running: nullableNumber(queue.running),
    },
    warning: warning && typeof warning.action === 'string' ? warning.action : null,
  };
}

export async function getPerformanceCapabilities(signal?: AbortSignal) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/performance/capabilities`, { signal });
  if (!response.ok) throw await apiError(response, '性能能力加载失败');
  return decodePerformanceCapabilities(await response.json());
}

export async function getBasemaps() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/basemaps`);
  if (!response.ok) {
    throw new Error('底图配置加载失败');
  }
  return response.json() as Promise<BasemapProvider[]>;
}

export async function getLayerFeatures(
  layerId: string,
  bbox: string,
  limit = 1000,
  signal?: AbortSignal,
  workspaceId?: number | null,
) {
  const params = new URLSearchParams({ bbox, limit: String(limit) });
  if (workspaceId) params.set('workspace_id', String(workspaceId));
  const response = await apiFetch(`${apiBaseUrl}/api/v1/layers/${layerId}/features?${params}`, {
    signal,
  });
  if (!response.ok) {
    throw new Error('视口图斑加载失败');
  }
  return response.json() as Promise<{
    type: 'FeatureCollection';
    features: unknown[];
    meta: FeatureQueryMeta;
  }>;
}

export async function getLayerFeatureSummaries(
  layerId: number,
  workspaceId?: number | null,
  cursor?: string | null,
) {
  const params = new URLSearchParams({ limit: '200' });
  if (workspaceId) params.set('workspace_id', String(workspaceId));
  if (cursor) params.set('cursor', cursor);
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/layers/${layerId}/feature-summaries?${params}`,
  );
  if (!response.ok) throw await apiError(response, '图斑列表加载失败');
  return response.json() as Promise<MapFeatureSummaryPage>;
}

export async function getLayerFeatureDetail(
  layerId: number,
  featureId: number,
  workspaceId?: number | null,
) {
  const params = new URLSearchParams();
  if (workspaceId) params.set('workspace_id', String(workspaceId));
  const query = params.size > 0 ? `?${params}` : '';
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/layers/${layerId}/features/${featureId}${query}`,
  );
  if (!response.ok) throw await apiError(response, '图斑详情加载失败');
  return response.json() as Promise<RealMapFeatureDetail>;
}

export async function createSpatialAnalysis(payload: {
  workspace_id: number;
  target_layer_id: number;
  target_feature_id: number;
  distance: number;
  unit: AnalysisUnit;
  scope: AnalysisScope;
}) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/spatial-analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '空间分析提交失败');
  return response.json() as Promise<ImportJob>;
}

export async function getSpatialAnalysis(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/spatial-analyses/${encodeURIComponent(jobId)}`,
  );
  if (!response.ok) throw await apiError(response, '空间分析结果加载失败');
  return response.json() as Promise<SpatialAnalysisResult>;
}

export async function getSpatialAnalysisHits(jobId: string, cursor?: string | null) {
  const params = new URLSearchParams({ limit: '100', include_geometry: 'true' });
  if (cursor) params.set('cursor', cursor);
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/spatial-analyses/${encodeURIComponent(jobId)}/hits?${params}`,
  );
  if (!response.ok) throw await apiError(response, '分析命中列表加载失败');
  return response.json() as Promise<SpatialAnalysisHitPage>;
}

export async function cancelSpatialAnalysis(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/spatial-analyses/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
  );
  if (!response.ok) throw await apiError(response, '空间分析取消失败');
  return response.json() as Promise<ImportJob>;
}

export async function exportSpatialAnalysis(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/spatial-analyses/${encodeURIComponent(jobId)}/exports`,
    { method: 'POST' },
  );
  if (!response.ok) throw await apiError(response, '分析结果导出失败');
  return response.json() as Promise<ImportJob>;
}

export async function downloadSpatialAnalysis(exportJobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/spatial-analyses/exports/${encodeURIComponent(exportJobId)}/download`,
  );
  if (!response.ok) throw await apiError(response, '分析结果下载失败');
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(
      response.headers.get('content-disposition'),
      'spatial-analysis.zip',
    ),
  };
}

export async function getWorkspaces() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces`);
  if (!response.ok) throw await apiError(response, '工作空间列表加载失败');
  return response.json() as Promise<WorkspaceSummary[]>;
}

export async function getWorkspace(workspaceId: number) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/${workspaceId}`);
  if (!response.ok) throw await apiError(response, '工作空间加载失败');
  return response.json() as Promise<WorkspaceDetail>;
}

export async function getWorkspaceCatalog() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/catalog`);
  if (!response.ok) throw await apiError(response, '工作空间数据目录加载失败');
  return response.json() as Promise<WorkspaceCatalog>;
}

export async function createWorkspace(payload: WorkspaceWrite) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '工作空间创建失败');
  return response.json() as Promise<WorkspaceDetail>;
}

export async function updateWorkspace(workspaceId: number, payload: WorkspaceUpdate) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/${workspaceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '工作空间保存失败');
  return response.json() as Promise<WorkspaceDetail>;
}

export async function deleteWorkspace(workspaceId: number) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/${workspaceId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw await apiError(response, '工作空间删除失败');
}

export async function exportWorkspace(workspaceId: number, includeRasters = false) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/${workspaceId}/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ include_rasters: includeRasters }),
  });
  if (!response.ok) throw await apiError(response, '工作空间包导出失败');
  return response.json() as Promise<ImportJob>;
}

export async function previewWorkspacePackage(file: File) {
  const formData = new FormData();
  formData.append('package', file);
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/packages/preview`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) throw await apiError(response, '工作空间包预览失败');
  return response.json() as Promise<WorkspacePackagePreview>;
}

export async function importWorkspacePackage(
  uploadToken: string,
  strategy: 'copy' | 'replace',
  targetWorkspaceId?: number | null,
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/workspaces/packages/imports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upload_token: uploadToken,
      strategy,
      target_workspace_id: targetWorkspaceId ?? null,
    }),
  });
  if (!response.ok) throw await apiError(response, '工作空间包导入失败');
  return response.json() as Promise<ImportJob>;
}

export async function downloadWorkspacePackage(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/workspaces/packages/exports/${encodeURIComponent(jobId)}/download`,
  );
  if (!response.ok) throw await apiError(response, '工作空间包下载失败');
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('content-disposition'), 'workspace.womap.zip'),
  };
}

export async function getLayers() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/layers`);
  if (!response.ok) throw await apiError(response, '图层列表加载失败');
  return response.json() as Promise<BackendLayerSummary[]>;
}

export async function getRasterHistogram(layerId: number, band: number, bins = 96) {
  const params = new URLSearchParams({ band: String(band), bins: String(bins) });
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rasters/${layerId}/histogram?${params}`);
  if (!response.ok) throw await apiError(response, '栅格直方图加载失败');
  return response.json() as Promise<RasterHistogram>;
}

export async function getRasterPixel(
  layerId: number,
  x: number,
  y: number,
  crs = 'EPSG:3857',
) {
  const params = new URLSearchParams({ x: String(x), y: String(y), crs });
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rasters/${layerId}/pixel?${params}`);
  if (!response.ok) throw await apiError(response, '像元查询失败');
  return response.json() as Promise<RasterPixel>;
}

export async function updateRasterStyle(layerId: number, style: RasterStyle) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rasters/${layerId}/style`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(style),
  });
  if (!response.ok) throw await apiError(response, '栅格样式保存失败');
  return response.json() as Promise<BackendLayerSummary>;
}

export async function deriveRaster(
  layerId: number,
  name: string,
  formula: RasterFormulaNode,
  style?: RasterStyle,
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rasters/${layerId}/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, formula, style }),
  });
  if (!response.ok) throw await apiError(response, '派生栅格任务提交失败');
  return response.json() as Promise<ImportJob>;
}

export async function exportRasters(layerIds: number[]) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/rasters/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format: 'cog', layer_ids: layerIds }),
  });
  if (!response.ok) throw await apiError(response, '栅格导出任务提交失败');
  return response.json() as Promise<ImportJob>;
}

export async function downloadRasterExport(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/rasters/exports/${encodeURIComponent(jobId)}/download`,
  );
  if (!response.ok) throw await apiError(response, '栅格成果下载失败');
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('content-disposition'), 'raster-cog.zip'),
  };
}

export async function createManualLayer(name?: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/layers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, geometry_type: 'Polygon' }),
  });
  if (!response.ok) throw await apiError(response, '图斑图层创建失败');
  return response.json() as Promise<BackendLayerSummary>;
}

export async function createLayerFeature(
  layerId: string,
  coordinates: number[][][],
  properties: Record<string, unknown> = {},
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/layers/${layerId}/features`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      geometry: { type: 'Polygon', coordinates },
      properties,
    }),
  });
  if (!response.ok) throw await apiError(response, '图斑保存失败');
  return response.json() as Promise<MapFeatureMutationResponse>;
}

export interface MapFeatureMutationResponse {
  feature: {
    id: number;
    layer_id: number;
    geometry: { type: 'Polygon'; coordinates: number[][][] };
    properties: Record<string, unknown>;
    revision: number;
  };
  layer: BackendLayerSummary;
}

export async function updateLayerFeature(
  layerId: string,
  featureId: number,
  coordinates: number[][][],
  properties: Record<string, unknown>,
  revision: number,
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/layers/${layerId}/features/${featureId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      geometry: { type: 'Polygon', coordinates },
      properties,
      revision,
    }),
  });
  if (!response.ok) throw await apiError(response, '图斑修改失败');
  return response.json() as Promise<MapFeatureMutationResponse>;
}

export async function deleteLayerFeature(layerId: string, featureId: number, revision: number) {
  const params = new URLSearchParams({ revision: String(revision) });
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/layers/${layerId}/features/${featureId}?${params}`,
    { method: 'DELETE' },
  );
  if (!response.ok) throw await apiError(response, '图斑删除失败');
  return response.json() as Promise<{
    deleted_feature_id: number;
    layer: BackendLayerSummary;
  }>;
}

export async function getJobs() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs`);
  if (!response.ok) throw await apiError(response, '任务列表加载失败');
  return response.json() as Promise<ImportJob[]>;
}

export async function getJob(jobId: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) throw await apiError(response, '任务状态加载失败');
  return response.json() as Promise<ImportJob>;
}

export async function getImportSettings() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources`);
  if (!response.ok) throw await apiError(response, '导入数据源加载失败');
  return response.json() as Promise<ImportSettings>;
}

export async function createImportSource(payload: ImportSourceWrite) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '数据源创建失败');
  return response.json() as Promise<ImportSourceProfile>;
}

export async function updateImportSource(sourceId: string, payload: ImportSourceWrite) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '数据源保存失败');
  return response.json() as Promise<ImportSourceProfile>;
}

export async function deleteImportSource(sourceId: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw await apiError(response, '数据源删除失败');
}

export async function testImportSource(sourceId: string, password?: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: password || null }),
  });
  if (!response.ok) throw await apiError(response, '数据源连接失败');
  return response.json() as Promise<{ ok: boolean; message: string }>;
}

export async function updateImportOptions(
  cachePath: string,
  batchSize: number,
  rasterStorePath: string,
  rasterScratchPath: string,
  rasterQuotaGb: number,
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/import-sources/options`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cache_path: cachePath,
      batch_size: batchSize,
      raster_store_path: rasterStorePath,
      raster_scratch_path: rasterScratchPath,
      raster_quota_gb: rasterQuotaGb,
    }),
  });
  if (!response.ok) throw await apiError(response, '导入选项保存失败');
  return response.json() as Promise<ImportSettings>;
}

export async function syncImportSource(sourceId: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/imports/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId }),
  });
  if (!response.ok) throw await apiError(response, '目录同步失败');
  return response.json() as Promise<ImportJob>;
}

export async function getImportCatalog(sourceId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/imports/catalog?${new URLSearchParams({ source_id: sourceId })}`,
  );
  if (!response.ok) throw await apiError(response, '导入目录加载失败');
  return response.json() as Promise<ImportCatalog>;
}

export async function importDatasets(
  sourceId: string,
  datasetIds: string[],
  crsOverrides: Record<string, string>,
) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/imports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_id: sourceId,
      dataset_ids: datasetIds,
      crs_overrides: crsOverrides,
    }),
  });
  if (!response.ok) throw await apiError(response, '数据导入失败');
  return response.json() as Promise<ImportJob>;
}

export async function resumeImportJob(jobId: string) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/imports/${jobId}/resume`, { method: 'POST' });
  if (!response.ok) throw await apiError(response, '任务恢复失败');
  return response.json() as Promise<ImportJob>;
}

export async function getLocalRuntimeSettings() {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/local`);
  if (!response.ok) {
    throw new Error('本地配置加载失败');
  }
  return response.json() as Promise<LocalRuntimeSettings>;
}

export async function updateLocalRuntimeSettings(payload: LocalRuntimeSettingsUpdate) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/settings/local`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = `本地配置保存失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<LocalRuntimeSettings>;
}

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) {
    return fallback;
  }
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition);
  const encoded = match?.[1] ?? match?.[2];
  if (!encoded) {
    return fallback;
  }
  return decodeURIComponent(encoded);
}

export async function exportLayers(format: ExportFormat, layerIds: number[]) {
  const response = await apiFetch(`${apiBaseUrl}/api/v1/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format, layer_ids: layerIds }),
  });

  if (!response.ok) {
    let detail = `导出失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<ImportJob>;
}

export async function downloadVectorExport(jobId: string) {
  const response = await apiFetch(
    `${apiBaseUrl}/api/v1/exports/${encodeURIComponent(jobId)}/download`,
  );
  if (!response.ok) throw await apiError(response, '矢量成果下载失败');
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(
      response.headers.get('content-disposition'),
      'womap-vector-export.zip',
    ),
  };
}
