import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BackendLayerSummary, ImportJob, SpatialAnalysisJobProgressDetail } from '../types/imports';
import type { RealMapFeatureDetail, SpatialAnalysisHit, SpatialAnalysisResult } from '../types/spatialAnalysis';
import type { WorkspaceDetail } from '../types/workspaces';
import { useJobsStore } from './useJobsStore';
import { useMapStore } from './useMapStore';
import { useSettingsStore } from './useSettingsStore';
import { useSpatialAnalysisStore } from './useSpatialAnalysisStore';
import { useWorkspaceContextStore } from './useWorkspaceContextStore';
import { useWorkspaceStore } from './useWorkspaceStore';

const backendLayer: BackendLayerSummary = {
  id: 7,
  name: '宗地面',
  geometry_type: 'Polygon',
  feature_count: 3,
  crs: 'EPSG:3857',
  bounds: {},
  visible: true,
  locked: false,
  opacity: 1,
  source_type: 'gdb',
  fields: [],
  style: { color: '#4656a8' },
  performance: {
    feature_count: 3,
    large_layer: false,
    indexed: true,
    recommended_mode: 'bbox',
  },
  provenance: {
    source_id: 'source-a',
    dataset_id: 'dataset-a',
    format: 'gdb',
    container: 'survey.gdb',
    relative_path: 'survey.gdb/宗地面',
    layer_name: '宗地面',
    fingerprint: 'fingerprint-a',
  },
};

const workspace: WorkspaceDetail = {
  id: 1,
  name: '分析工作空间',
  description: '',
  default_basemap: 'amap-vector',
  revision: 1,
  layer_count: 1,
  is_default: true,
  updated_at: null,
  schema_version: 'womap.workspace/v1',
  workspace_uuid: '22222222-2222-2222-2222-222222222222',
  view: { center: [0, 0], zoom: 10 },
  layers: [
    {
      layer: backendLayer,
      config: {
        layer_id: 7,
        dataset_id: 'dataset-a',
        visible: true,
        opacity: 1,
        order: 0,
        selection: { mode: 'all', feature_ids: [], source_feature_ids: [] },
      },
    },
  ],
  warnings: [],
};

const target: RealMapFeatureDetail = {
  id: 44,
  layer_id: 7,
  source_feature_id: 'parcel-44',
  geometry: {
    type: 'Polygon',
    coordinates: [[[0, 0], [100, 0], [100, 100], [0, 0]]],
  },
  properties: { 名称: '目标宗地' },
  bbox: { min_x: 0, min_y: 0, max_x: 100, max_y: 100 },
  area: 5000,
  perimeter: 341.42,
  revision: 1,
  layer: backendLayer,
};

const jobDetail: SpatialAnalysisJobProgressDetail = {
  kind: 'spatial-analysis',
  stage: 'queued',
  workspace_id: 1,
  target_feature_id: 44,
  processed_layers: 0,
  total_layers: 1,
  matched_features: 0,
  warnings: [],
  error: null,
};

function analysisJob(status: ImportJob['status'] = 'queued'): ImportJob {
  return {
    id: 'analysis-1',
    job_type: 'spatial-analysis',
    status,
    progress: status === 'done' ? 100 : 0,
    message: status === 'done' ? '空间分析完成' : '空间分析排队中',
    detail: { ...jobDetail, stage: status },
    result: {},
  };
}

const firstHit: SpatialAnalysisHit = {
  layer_id: 7,
  layer_name: '宗地面',
  feature_id: 45,
  source_feature_id: 'parcel-45',
  label: '相邻宗地',
  geometry_type: 'Polygon',
  direct_intersection: false,
  buffer_intersection: true,
  distance_m: 12,
  intersection_area_sqm: 300,
  intersection_length_m: 0,
  properties: { 名称: '相邻宗地' },
  geometry: null,
};

const result: SpatialAnalysisResult = {
  job: analysisJob('done'),
  workspace_id: 1,
  target_layer_id: 7,
  target_feature_id: 44,
  distance: 2,
  unit: 'km',
  distance_meters: 2000,
  scope: 'visible',
  target_geometry: target.geometry,
  buffer_geometry: target.geometry,
  groups: [
    {
      key: 'gdb:source-a:survey.gdb',
      name: 'survey.gdb',
      source_type: 'gdb',
      layers: [
        {
          layer_id: 7,
          layer_name: '宗地面',
          geometry_type: 'Polygon',
          exists: true,
          hit_count: 1,
          nearest_distance_m: 12,
          direct_intersection_count: 0,
          buffer_intersection_count: 1,
          direct_area_sqm: 0,
          buffer_area_sqm: 300,
          direct_length_m: 0,
          buffer_length_m: 0,
          point_hit_count: 0,
          coverage_ratio: 0.06,
        },
      ],
    },
  ],
  stale: false,
  warnings: [],
};

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useJobsStore.getState().reset();
  useMapStore.getState().reset();
  useSettingsStore.getState().reset();
  useSpatialAnalysisStore.getState().reset();
  useWorkspaceContextStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe('spatial analysis store', () => {
  it('enters and exits analysis mode while disabling imagery swipe', () => {
    useMapStore.getState().setSwipeEnabled(true);
    useSettingsStore.getState().collapseSidePanelsForSwipe();

    useSpatialAnalysisStore.getState().enter();

    expect(useWorkspaceStore.getState().workspaceMode).toBe('analysis');
    expect(useMapStore.getState().imagerySwipe.enabled).toBe(false);
    expect(useSettingsStore.getState().panels.layers).toBe(true);

    useSpatialAnalysisStore.getState().exit();
    expect(useWorkspaceStore.getState().workspaceMode).toBe('browse');
    expect(useSpatialAnalysisStore.getState()).toMatchObject({ target: null, drawerOpen: false });
  });

  it('loads a real feature, submits common-unit parameters, and cancels the job', async () => {
    vi.useFakeTimers();
    useWorkspaceContextStore.setState({ current: workspace, workspaces: [workspace] });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/layers/7/features/44?workspace_id=1')) {
        return jsonResponse(target);
      }
      if (url.endsWith('/api/v1/spatial-analyses') && init?.method === 'POST') {
        return jsonResponse(analysisJob());
      }
      if (url.endsWith('/api/v1/spatial-analyses/analysis-1/cancel')) {
        return jsonResponse({ ...analysisJob('interrupted'), message: '空间分析已取消' });
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    await useSpatialAnalysisStore.getState().selectFeature(7, 44);
    useSpatialAnalysisStore.getState().setDistance(2);
    useSpatialAnalysisStore.getState().setUnit('km');
    useSpatialAnalysisStore.getState().setScope('visible');
    await useSpatialAnalysisStore.getState().run();

    const createCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).endsWith('/api/v1/spatial-analyses'),
    );
    expect(JSON.parse(createCall?.[1]?.body as string)).toEqual({
      workspace_id: 1,
      target_layer_id: 7,
      target_feature_id: 44,
      distance: 2,
      unit: 'km',
      scope: 'visible',
    });
    expect(useSpatialAnalysisStore.getState()).toMatchObject({
      target: { id: 44 },
      job: { id: 'analysis-1', status: 'queued' },
      drawerOpen: true,
      busy: true,
    });

    await useSpatialAnalysisStore.getState().cancel();
    expect(useSpatialAnalysisStore.getState()).toMatchObject({
      job: { status: 'interrupted' },
      busy: false,
    });
  });

  it('reopens completed history and appends paged hit results', async () => {
    let hitPage = 0;
    const secondHit = { ...firstHit, feature_id: 46, source_feature_id: 'parcel-46', label: '第二宗地' };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/spatial-analyses/analysis-1')) return jsonResponse(result);
      if (url.includes('/api/v1/spatial-analyses/analysis-1/hits?')) {
        hitPage += 1;
        return jsonResponse(
          hitPage === 1
            ? { items: [firstHit], next_cursor: '7:45', has_more: true, stale: false, warnings: [] }
            : { items: [secondHit], next_cursor: null, has_more: false, stale: false, warnings: [] },
        );
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    await useSpatialAnalysisStore.getState().openHistory('analysis-1');
    expect(useSpatialAnalysisStore.getState()).toMatchObject({
      result: { distance_meters: 2000 },
      hits: [{ feature_id: 45 }],
      nextCursor: '7:45',
      hasMore: true,
      busy: false,
    });

    await useSpatialAnalysisStore.getState().loadMore();
    expect(useSpatialAnalysisStore.getState()).toMatchObject({
      hits: [{ feature_id: 45 }, { feature_id: 46 }],
      nextCursor: null,
      hasMore: false,
    });
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('cursor=7%3A45'))).toBe(true);
  });
});
