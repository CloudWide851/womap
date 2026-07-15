import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BackendLayerSummary } from '../types/imports';
import type {
  WorkspaceDetail,
  WorkspaceFeatureSelection,
  WorkspaceSummary,
} from '../types/workspaces';
import { useMapStore } from './useMapStore';
import { useWorkspaceContextStore } from './useWorkspaceContextStore';
import { useWorkspaceStore } from './useWorkspaceStore';

const layer: BackendLayerSummary = {
  id: 7,
  name: '宗地面',
  kind: 'vector',
  geometry_type: 'Polygon',
  feature_count: 2,
  crs: 'EPSG:3857',
  bounds: { min_x: 1, min_y: 2, max_x: 3, max_y: 4 },
  visible: true,
  locked: false,
  opacity: 1,
  source_type: 'gdb',
  fields: [{ name: '名称', type: 'string' }],
  style: { color: '#4656a8' },
  performance: {
    feature_count: 2,
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
  raster: null,
};

const summary: WorkspaceSummary = {
  id: 1,
  name: '本地工作台',
  description: '默认工作空间',
  default_basemap: 'amap-vector',
  revision: 1,
  layer_count: 1,
  is_default: true,
  updated_at: null,
};

function workspaceDetail(
  revision = 1,
  selection: WorkspaceFeatureSelection = {
    mode: 'all',
    feature_ids: [],
    source_feature_ids: [],
  },
  visible = true,
  opacity = 1,
): WorkspaceDetail {
  return {
    ...summary,
    revision,
    schema_version: 'womap.workspace/v1',
    workspace_uuid: '11111111-1111-1111-1111-111111111111',
    view: { center: [12614000, 2647000], zoom: 12 },
    layers: [
      {
        layer: { ...layer, visible, opacity },
        config: {
          layer_id: layer.id,
          dataset_id: layer.provenance.dataset_id,
          visible,
          opacity,
          order: 0,
          selection,
        },
      },
    ],
    warnings: [],
  };
}

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  useWorkspaceContextStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useMapStore.getState().reset();
});

describe('workspace context store', () => {
  it('initializes the default workspace and applies its map and backend layer context', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/workspaces')) return jsonResponse([summary]);
      if (url.endsWith('/api/v1/workspaces/1')) return jsonResponse(workspaceDetail());
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    await useWorkspaceContextStore.getState().initialize();

    expect(useWorkspaceContextStore.getState()).toMatchObject({
      dirty: false,
      loading: false,
      current: {
        id: 1,
        revision: 1,
        workspace_uuid: '11111111-1111-1111-1111-111111111111',
      },
    });
    expect(useWorkspaceStore.getState().layers.find((item) => item.id === '7')).toMatchObject({
      name: '宗地面',
      source: 'backend',
      visible: true,
    });
    expect(useMapStore.getState()).toMatchObject({
      selectedBasemapId: 'amap-vector',
      viewCenter: [12614000, 2647000],
      zoom: 12,
    });
    expect(window.localStorage.getItem('womap.active-workspace-id')).toBe('1');
  });

  it('tracks runtime and feature-selection changes and saves them with revision control', async () => {
    const saved = workspaceDetail(
      2,
      { mode: 'include', feature_ids: [44], source_feature_ids: ['parcel-44'] },
      false,
      0.4,
    );
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/workspaces') && !init?.method) return jsonResponse([summary]);
      if (url.endsWith('/api/v1/workspaces/1') && init?.method === 'PUT') {
        return jsonResponse(saved);
      }
      if (url.endsWith('/api/v1/workspaces/1')) return jsonResponse(workspaceDetail());
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);
    await useWorkspaceContextStore.getState().initialize();

    useWorkspaceStore.getState().toggleLayer('7');
    useWorkspaceStore.getState().setLayerOpacity('7', 0.4);
    useWorkspaceContextStore.getState().syncRuntimeLayer('7', false, 0.4);
    useWorkspaceContextStore.getState().setLayerSelection(7, {
      mode: 'include',
      feature_ids: [44],
      source_feature_ids: ['parcel-44'],
    });

    expect(useWorkspaceContextStore.getState().dirty).toBe(true);
    await useWorkspaceContextStore.getState().saveCurrent();

    const updateCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).endsWith('/api/v1/workspaces/1') && call[1]?.method === 'PUT',
    );
    expect(updateCall).toBeDefined();
    expect(JSON.parse(updateCall?.[1]?.body as string)).toMatchObject({
      revision: 1,
      default_basemap: 'amap-vector',
      layers: [
        {
          layer_id: 7,
          dataset_id: 'dataset-a',
          visible: false,
          opacity: 0.4,
          selection: {
            mode: 'include',
            feature_ids: [44],
            source_feature_ids: ['parcel-44'],
          },
        },
      ],
    });
    expect(useWorkspaceContextStore.getState()).toMatchObject({
      dirty: false,
      current: { revision: 2 },
    });
  });
});
