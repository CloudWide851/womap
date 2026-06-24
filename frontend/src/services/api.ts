import type { BasemapProvider, FeatureQueryMeta } from '../types/workspace';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

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
