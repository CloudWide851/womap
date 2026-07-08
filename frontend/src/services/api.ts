import type { BasemapProvider, FeatureQueryMeta } from '../types/workspace';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
type ExportFormat = 'shp' | 'gdb';

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

export async function getLayerFeatures(layerId: string, bbox: string, limit = 1000) {
  const params = new URLSearchParams({ bbox, limit: String(limit) });
  const response = await fetch(`${apiBaseUrl}/api/v1/layers/${layerId}/features?${params}`);
  if (!response.ok) {
    throw new Error('视口图斑加载失败');
  }
  return response.json() as Promise<{
    type: 'FeatureCollection';
    features: unknown[];
    meta: FeatureQueryMeta;
  }>;
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
