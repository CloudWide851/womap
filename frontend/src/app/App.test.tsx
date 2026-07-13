import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { useAuthStore } from '../stores/useAuthStore';
import { useMapStore } from '../stores/useMapStore';
import { useJobsStore } from '../stores/useJobsStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useAuthStore.getState().reset();
  useMapStore.getState().reset();
  useJobsStore.getState().reset();
  useSettingsStore.getState().reset();
  useWorkspaceStore.getState().reset();
  cleanup();
});

async function loginToWorkbench() {
  const passwordInput = await screen.findByLabelText('登录密码');
  fireEvent.change(passwordInput, {
    target: { value: 'local-passphrase-2026' },
  });
  fireEvent.click(screen.getByLabelText('登录工作台'));
  await screen.findByTestId('brand-logo');
}

describe('App', () => {
  it('starts with a guided local login surface', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: '进入工作台' })).toBeInTheDocument();
    expect(screen.getByAltText('WOMAP')).toBeInTheDocument();
    expect(screen.queryByLabelText('测绘扫描状态')).not.toBeInTheDocument();
    expect(screen.getByText('默认账号 local-admin')).toBeInTheDocument();
    expect(screen.getByText('密码不少于 15 位即可进入本地工作台')).toBeInTheDocument();
    expect(screen.queryByLabelText('工作台预览')).not.toBeInTheDocument();
    expect(screen.queryByText('本地安全门禁')).not.toBeInTheDocument();
  });

  it('shows login security controls before entering the workspace', async () => {
    render(<App />);

    expect(await screen.findByLabelText('登录账号')).toBeInTheDocument();
    expect(screen.getByLabelText('登录账号')).toBeInTheDocument();
    expect(screen.getByLabelText('登录密码')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '短会话 30分' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '长会话 7天' })).toBeInTheDocument();
    expect(screen.getByLabelText('登录工作台')).toBeDisabled();
    expect(screen.getByText('输入至少 15 位密码')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('登录密码'), {
      target: { value: 'short' },
    });
    expect(screen.getByLabelText('登录工作台')).toBeDisabled();
    expect(screen.getByText('输入至少 15 位密码')).toBeInTheDocument();
  });

  it('renders the professional GIS workbench shell', async () => {
    render(<App />);
    await loginToWorkbench();

    expect(screen.getByTestId('brand-logo')).toBeInTheDocument();
    expect(screen.queryByText('WOMAP')).not.toBeInTheDocument();
    expect(screen.queryByText('图斑工坊')).not.toBeInTheDocument();
    expect(screen.getByText('工作空间')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '定位序列' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '地图工具' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '字段概览' })).toBeInTheDocument();
    expect(screen.getAllByText('性能').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('导入数据')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '文件操作' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '工作模式' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '工作模式' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '地图底图' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '地图底图' })).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '编辑工具' })).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: '历史操作' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '工作台状态' })).toBeInTheDocument();
    expect(screen.getByLabelText('新增图层')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '高德矢量' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('打开设置')).toBeInTheDocument();
    expect(screen.getByLabelText(/当前短会话/)).toBeInTheDocument();
    expect(screen.getByLabelText('退出登录')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('图斑编辑'));
    expect(screen.getByRole('group', { name: '编辑工具' })).toBeInTheDocument();
    expect(screen.getByLabelText('绘制图斑')).toBeInTheDocument();
  });

  it('converts coordinates from the map tools panel', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.change(screen.getByLabelText('坐标 X 或经度'), {
      target: { value: '113.2644' },
    });
    fireEvent.change(screen.getByLabelText('坐标 Y 或纬度'), {
      target: { value: '23.1291' },
    });
    fireEvent.click(screen.getByRole('button', { name: '转换坐标' }));

    expect(
      screen.getByRole('status', { name: /坐标转换结果 12608535\.33, 2647638\.58/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status', { name: /坐标转换完成/ })).toBeInTheDocument();
  });

  it('enables two-period imagery swipe controls', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('两期卷帘'));

    expect(screen.queryByText('工作空间')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '字段概览' })).not.toBeInTheDocument();
    expect(screen.getByText('卷帘 50%')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: /已进入两期影像卷帘模式/ })).toBeInTheDocument();
    expect(useMapStore.getState().imagerySwipe).toMatchObject({
      enabled: true,
      beforeBasemapId: 'amap-vector',
      afterBasemapId: 'tencent-vector',
      position: 50,
    });
    expect(useSettingsStore.getState().panels.layers).toBe(false);
    expect(screen.queryByRole('group', { name: '编辑工具' })).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('浏览查看'));

    await waitFor(() => expect(screen.getByText('工作空间')).toBeInTheDocument());
    expect(useMapStore.getState().imagerySwipe.enabled).toBe(false);
    expect(useSettingsStore.getState().panels.layers).toBe(true);
  });

  it('opens the import center and still reports unfinished command feedback', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/settings/import-sources')) {
        return new Response(JSON.stringify({ cache_path: '.womap-data/import-cache', batch_size: 2000, sources: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/jobs') || url.endsWith('/api/v1/layers')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('{}', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByLabelText('导入数据'));
    expect(await screen.findByRole('dialog', { name: '导入中心' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '管理数据源' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    fireEvent.click(screen.getByLabelText('保存项目'));
    expect(screen.getByRole('status', { name: /保存入口已标记/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('撤销'));
    expect(screen.getByRole('status', { name: /暂无可撤销操作/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('重做'));
    expect(screen.getByRole('status', { name: /暂无可重做操作/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('新增图层'));
    expect(screen.getByRole('status', { name: /新增图层入口已标记/ })).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('图斑编辑'));
    fireEvent.click(screen.getByLabelText('移动'));
    expect(screen.getByRole('status', { name: /已切换到移动工具/ })).toBeInTheDocument();
    expect(screen.getByLabelText('当前工具 移动')).toBeInTheDocument();
  });

  it('focuses sample features from the feature navigator', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByRole('button', { name: '定位 边界图斑 108' }));

    expect(useWorkspaceStore.getState().selectedFeatureId).toBe('feature-boundary-108');
    expect(useWorkspaceStore.getState().featureFocusRequest).toMatchObject({
      featureId: 'feature-boundary-108',
      sequence: 1,
    });
    expect(screen.getByRole('status', { name: /已定位 B-108/ })).toBeInTheDocument();
    expect(screen.getAllByText('B-108').length).toBeGreaterThan(0);
    expect(screen.getAllByText('边界图斑 108').length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByLabelText('查看 边界图斑 108 属性')[0]);

    expect(await screen.findByRole('dialog', { name: '边界图斑 108' })).toBeInTheDocument();
  });

  it('opens a real export panel and refuses to fake local demo layers', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByLabelText('导出成果'));

    expect(await screen.findByLabelText('导出设置')).toBeInTheDocument();
    expect(screen.getByText('选择后端图层与格式')).toBeInTheDocument();
    expect(screen.getByText('SHP')).toBeInTheDocument();
    expect(screen.getByText('GDB')).toBeInTheDocument();
    expect(screen.queryByText(/阶段 6/)).not.toBeInTheDocument();
    expect(screen.queryByText(/导出入口已标记/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '导出 SHP' }));

    expect(screen.getByRole('status', { name: /暂无后端图层可导出/ })).toBeInTheDocument();
  });

  it('submits selected backend layers for GDB export and reports the download', async () => {
    useWorkspaceStore.setState({ selectedLayerId: '2' });
    const backendLayers = [
      {
        id: 1,
        name: '后端地块 A',
        geometry_type: 'Polygon',
        feature_count: 3,
        crs: 'EPSG:3857',
        bounds: {},
        visible: true,
        locked: false,
        opacity: 1,
        source_type: 'manual',
        fields: [],
        style: { color: '#4656a8' },
        performance: {
          feature_count: 3,
          large_layer: false,
          indexed: true,
          recommended_mode: 'bbox',
        },
      },
      {
        id: 2,
        name: '后端地块 B',
        geometry_type: 'Polygon',
        feature_count: 4,
        crs: 'EPSG:3857',
        bounds: {},
        visible: true,
        locked: false,
        opacity: 1,
        source_type: 'manual',
        fields: [],
        style: { color: '#8a6d3b' },
        performance: {
          feature_count: 4,
          large_layer: false,
          indexed: true,
          recommended_mode: 'bbox',
        },
      },
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/layers')) {
        return new Response(JSON.stringify(backendLayers), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/v1/jobs')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(new Blob(['zip'], { type: 'application/zip' }), {
        status: 200,
        headers: { 'content-disposition': 'attachment; filename="womap-export-gdb.zip"' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:womap-export'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<App />);
    await loginToWorkbench();
    await waitFor(() =>
      expect(useWorkspaceStore.getState().layers.some((layer) => layer.id === '2')).toBe(true),
    );

    fireEvent.click(screen.getByLabelText('导出成果'));
    expect(await screen.findByRole('checkbox', { name: /后端地块 A/ })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /后端地块 B/ })).toBeChecked();
    fireEvent.click(await screen.findByRole('radio', { name: 'GDB' }));
    fireEvent.click(screen.getByRole('button', { name: '导出 GDB' }));

    const exportCall = await waitFor(() => {
      const call = fetchMock.mock.calls.find((item) => String(item[0]).endsWith('/api/v1/exports'));
      expect(call).toBeDefined();
      return call!;
    });
    const requestInit = exportCall[1] as RequestInit;
    expect(JSON.parse(requestInit.body as string)).toEqual({
      format: 'gdb',
      layer_ids: [2],
    });
    expect(await screen.findByRole('status', { name: /GDB 导出完成/ })).toBeInTheDocument();
  });

  it('creates a real polygon layer before drawing when only a demo layer is selected', async () => {
    const createdLayer = {
      id: 9,
      name: '新建图斑图层 1',
      geometry_type: 'Polygon',
      feature_count: 0,
      crs: 'EPSG:3857',
      bounds: {},
      visible: true,
      locked: false,
      opacity: 1,
      source_type: 'manual',
      fields: [],
      style: { color: '#4656a8' },
      performance: {
        feature_count: 0,
        large_layer: false,
        indexed: true,
        recommended_mode: 'bbox',
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/layers') && init?.method === 'POST') {
        return new Response(JSON.stringify(createdLayer), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/layers/9/features?')) {
        return new Response(
          JSON.stringify({
            type: 'FeatureCollection',
            features: [],
            meta: { limit: 2000, returned: 0, truncated: false, cache_hit: false, strategy: 'postgis-bbox-gist' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/v1/layers') || url.endsWith('/api/v1/jobs')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('{}', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await loginToWorkbench();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('图斑编辑'));
    fireEvent.click(screen.getByLabelText('绘制图斑'));

    await waitFor(() => expect(useWorkspaceStore.getState().selectedLayerId).toBe('9'));
    expect(useWorkspaceStore.getState().layers.find((layer) => layer.id === '9')).toMatchObject({
      name: '新建图斑图层 1',
      source: 'backend',
      geometryType: 'Polygon',
    });
    const createCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).endsWith('/api/v1/layers') && call[1]?.method === 'POST',
    );
    expect(JSON.parse(createCall?.[1]?.body as string)).toEqual({ geometry_type: 'Polygon' });
  });

  it('opens local config dialog and writes editable runtime settings', async () => {
    const initialSettings = {
      config_source: 'H:/repo/config/settings.example.yaml',
      local_config_path: 'H:/repo/config/settings.local.yaml',
      server: { host: '127.0.0.1', port: 8000 },
      frontend: { dev_server: { host: '127.0.0.1', port: 9173 } },
    };
    const updatedSettings = {
      ...initialSettings,
      config_source: initialSettings.local_config_path,
      server: { host: '127.0.0.1', port: 8100 },
      frontend: { dev_server: { host: '127.0.0.1', port: 9273 } },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/layers') || url.endsWith('/api/v1/jobs')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/v1/settings/local') && init?.method === 'PUT') {
        return new Response(JSON.stringify(updatedSettings), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify(initialSettings), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByLabelText('本地配置'));

    expect(await screen.findByRole('dialog', { name: '本地运行配置' })).toBeInTheDocument();
    expect(await screen.findByDisplayValue('9173')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('API Port'), { target: { value: '8100' } });
    fireEvent.change(screen.getByLabelText('Web Port'), { target: { value: '9273' } });
    fireEvent.click(screen.getByRole('button', { name: '写入本地配置' }));

    const updateCall = await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (item) => String(item[0]).endsWith('/api/v1/settings/local') && item[1]?.method === 'PUT',
      );
      expect(call).toBeDefined();
      return call!;
    });
    const requestInit = updateCall[1] as RequestInit;
    expect(JSON.parse(requestInit.body as string)).toEqual({
      server: { host: '127.0.0.1', port: 8100 },
      frontend: { dev_server: { host: '127.0.0.1', port: 9273 } },
    });
    expect(screen.getByRole('status', { name: /本地配置已写入/ })).toBeInTheDocument();
  });

  it('separates settings from the main workspace surface', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getAllByLabelText('打开设置')[0]);

    expect(await screen.findByRole('heading', { name: '工作台设置' })).toBeInTheDocument();
    expect(screen.getByLabelText('返回工作台')).toBeInTheDocument();
    expect(screen.getByLabelText('隐藏性能面板')).toBeInTheDocument();
    expect(screen.getByText('登录安全')).toBeInTheDocument();
    expect(screen.getByText('短会话')).toBeInTheDocument();
    expect(screen.queryByLabelText('新增图层')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('返回工作台'));
    await waitFor(() => expect(screen.getByText('工作空间')).toBeInTheDocument());
  });

  it('lets the fields setting control a real field overview panel', async () => {
    render(<App />);
    await loginToWorkbench();

    expect(screen.getByRole('heading', { name: '字段概览' })).toBeInTheDocument();
    expect(screen.getByText('project_code')).toBeInTheDocument();

    fireEvent.click(screen.getAllByLabelText('打开设置')[0]);
    fireEvent.click(await screen.findByLabelText('隐藏字段面板'));
    fireEvent.click(screen.getByLabelText('返回工作台'));

    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: '字段概览' })).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getAllByLabelText('打开设置')[0]);
    fireEvent.click(await screen.findByLabelText('显示字段面板'));
    fireEvent.click(screen.getByLabelText('返回工作台'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '字段概览' })).toBeInTheDocument(),
    );
  });

  it('opens layer and feature attributes on demand', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getAllByLabelText('查看 项目边界 属性')[0]);

    expect(await screen.findByRole('dialog', { name: '项目边界' })).toBeInTheDocument();
    expect(screen.getAllByText('加载策略').length).toBeGreaterThan(0);
    expect(screen.getByText('字段结构')).toBeInTheDocument();
    expect(screen.getByText(/project_code · string · 必填/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('关闭属性检查器'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('B-102 查看示例图斑属性'));

    expect(await screen.findByRole('dialog', { name: '边界图斑 102' })).toBeInTheDocument();
    expect(screen.getAllByText('项目编号').length).toBeGreaterThan(0);
  });
});
