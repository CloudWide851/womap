import type { BasemapProvider, FeatureQueryMeta } from '../types/workspace';
import type {
  BackendLayerSummary,
  ImportCatalog,
  ImportJob,
  ImportSettings,
  ImportSourceProfile,
  ImportSourceWrite,
} from '../types/imports';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
type ExportFormat = 'shp' | 'gdb';

async function apiError(response: Response, fallback: string) {
  let detail = `${fallback}（${response.status}）`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    // Keep the status fallback for non-JSON responses.
  }
  return new Error(detail);
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
  const response = await fetch(`${apiBaseUrl}/health`);
  if (!response.ok) {
    throw new Error('服务状态检查失败');
  }
  return response.json() as Promise<{
    status: string;
    environment: string;
    database: string;
    redis_configured: boolean;
  }>;
}

export async function getBasemaps() {
  const response = await fetch(`${apiBaseUrl}/api/v1/basemaps`);
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
) {
  const params = new URLSearchParams({ bbox, limit: String(limit) });
  const response = await fetch(`${apiBaseUrl}/api/v1/layers/${layerId}/features?${params}`, {
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

export async function getLayers() {
  const response = await fetch(`${apiBaseUrl}/api/v1/layers`);
  if (!response.ok) throw await apiError(response, '图层列表加载失败');
  return response.json() as Promise<BackendLayerSummary[]>;
}

export async function getJobs() {
  const response = await fetch(`${apiBaseUrl}/api/v1/jobs`);
  if (!response.ok) throw await apiError(response, '任务列表加载失败');
  return response.json() as Promise<ImportJob[]>;
}

export async function getImportSettings() {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources`);
  if (!response.ok) throw await apiError(response, '导入数据源加载失败');
  return response.json() as Promise<ImportSettings>;
}

export async function createImportSource(payload: ImportSourceWrite) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '数据源创建失败');
  return response.json() as Promise<ImportSourceProfile>;
}

export async function updateImportSource(sourceId: string, payload: ImportSourceWrite) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await apiError(response, '数据源保存失败');
  return response.json() as Promise<ImportSourceProfile>;
}

export async function deleteImportSource(sourceId: string) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw await apiError(response, '数据源删除失败');
}

export async function testImportSource(sourceId: string, password?: string) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources/${sourceId}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: password || null }),
  });
  if (!response.ok) throw await apiError(response, '数据源连接失败');
  return response.json() as Promise<{ ok: boolean; message: string }>;
}

export async function updateImportOptions(cachePath: string, batchSize: number) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/import-sources/options`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cache_path: cachePath, batch_size: batchSize }),
  });
  if (!response.ok) throw await apiError(response, '导入选项保存失败');
  return response.json() as Promise<ImportSettings>;
}

export async function syncImportSource(sourceId: string) {
  const response = await fetch(`${apiBaseUrl}/api/v1/imports/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId }),
  });
  if (!response.ok) throw await apiError(response, '目录同步失败');
  return response.json() as Promise<ImportJob>;
}

export async function getImportCatalog(sourceId: string) {
  const response = await fetch(
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
  const response = await fetch(`${apiBaseUrl}/api/v1/imports`, {
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
  const response = await fetch(`${apiBaseUrl}/api/v1/imports/${jobId}/resume`, { method: 'POST' });
  if (!response.ok) throw await apiError(response, '任务恢复失败');
  return response.json() as Promise<ImportJob>;
}

export async function getLocalRuntimeSettings() {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/local`);
  if (!response.ok) {
    throw new Error('本地配置加载失败');
  }
  return response.json() as Promise<LocalRuntimeSettings>;
}

export async function updateLocalRuntimeSettings(payload: LocalRuntimeSettingsUpdate) {
  const response = await fetch(`${apiBaseUrl}/api/v1/settings/local`, {
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
  const response = await fetch(`${apiBaseUrl}/api/v1/exports`, {
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

  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(
      response.headers.get('content-disposition'),
      `womap-export-${format}.zip`,
    ),
  };
}
