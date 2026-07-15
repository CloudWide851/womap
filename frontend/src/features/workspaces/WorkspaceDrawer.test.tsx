import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BackendLayerSummary } from '../../types/imports';
import type { WorkspaceCatalog, WorkspaceDetail, WorkspaceSummary } from '../../types/workspaces';
import { useWorkspaceContextStore } from '../../stores/useWorkspaceContextStore';
import { WorkspaceDrawer } from './WorkspaceDrawer';

const layer: BackendLayerSummary = {
  id: 7,
  name: '宗地面',
  geometry_type: 'Polygon',
  feature_count: 2,
  crs: 'EPSG:3857',
  bounds: {},
  visible: true,
  locked: false,
  opacity: 1,
  source_type: 'gdb',
  fields: [],
  style: {},
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
};

const current: WorkspaceDetail = {
  id: 1,
  name: '本地工作台',
  description: '默认工作空间',
  default_basemap: 'amap-vector',
  revision: 1,
  layer_count: 1,
  is_default: true,
  updated_at: null,
  schema_version: 'womap.workspace/v1',
  workspace_uuid: '11111111-1111-1111-1111-111111111111',
  view: { center: [0, 0], zoom: 10 },
  layers: [
    {
      layer,
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

const other: WorkspaceSummary = {
  id: 2,
  name: '外业工作空间',
  description: '',
  default_basemap: 'osm',
  revision: 1,
  layer_count: 0,
  is_default: false,
  updated_at: null,
};

const catalog: WorkspaceCatalog = {
  groups: [
    {
      key: 'gdb:source-a:survey.gdb',
      label: 'survey.gdb',
      format: 'gdb',
      source_id: 'source-a',
      container: 'survey.gdb',
      layers: [layer],
    },
  ],
};

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useWorkspaceContextStore.getState().reset();
  cleanup();
});

describe('WorkspaceDrawer', () => {
  it('groups GDB data, guards dirty switching, and previews a conflicting portable package', async () => {
    useWorkspaceContextStore.setState({
      current,
      workspaces: [current, other],
      catalog,
      dirty: true,
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/workspaces/catalog')) return jsonResponse(catalog);
      if (url.endsWith('/api/v1/workspaces/packages/preview')) {
        return jsonResponse({
          upload_token: 'upload-token',
          workspace_name: '分享工作空间',
          workspace_uuid: current.workspace_uuid,
          revision: 3,
          package_version: 'womap.workspace/v1',
          layer_count: 1,
          feature_count: 2,
          basemap: { id: 'missing-map', name: '外部底图', type: 'xyz' },
          basemap_missing: true,
          conflicting_workspace_id: 1,
          warnings: ['底图需要重新绑定。'],
        });
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<WorkspaceDrawer open onClose={() => undefined} />);

    expect(await screen.findByText('survey.gdb · 1')).toBeInTheDocument();
    fireEvent.click(screen.getByText('survey.gdb · 1'));
    expect(screen.getByText('宗地面')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '全部图斑' })).toBeChecked();

    expect(screen.getByText('未保存')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存' })).toBeEnabled();

    const workspaceSelect = screen.getByRole('combobox', { name: '当前工作空间' });
    fireEvent.mouseDown(workspaceSelect);
    const workspaceOption = await screen.findByText('外业工作空间', {
      selector: '.ant-select-item-option-content',
    });
    const optionNode = workspaceOption.closest<HTMLElement>('.ant-select-item-option');
    expect(optionNode).not.toBeNull();
    fireEvent.mouseDown(optionNode!);
    fireEvent.click(optionNode!);
    expect(await screen.findByRole('button', { name: '保存并切换' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '放弃修改' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '保存并切换' })).not.toBeInTheDocument(),
    );
    expect(useWorkspaceContextStore.getState().current?.id).toBe(1);

    const uploadInput = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(uploadInput).not.toBeNull();
    fireEvent.change(uploadInput!, {
      target: { files: [new File(['workspace'], 'shared.womap.zip', { type: 'application/zip' })] },
    });

    expect(await screen.findByText('分享工作空间')).toBeInTheDocument();
    expect(screen.getByText('1 图层 · 2 图斑 · womap.workspace/v1')).toBeInTheDocument();
    expect(screen.getByText('底图 外部底图 · 需重新绑定')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '创建副本' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '覆盖同 UUID' })).toBeEnabled();
  }, 10_000);
});
