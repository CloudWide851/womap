import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { useAuthStore } from '../stores/useAuthStore';
import { useMapStore } from '../stores/useMapStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useAuthStore.getState().reset();
  useMapStore.getState().reset();
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
    expect(screen.getByLabelText('测绘扫描状态')).toBeInTheDocument();
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
    expect(screen.getByRole('group', { name: '编辑工具' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '历史操作' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '工作台状态' })).toBeInTheDocument();
    expect(screen.getByLabelText('新增图层')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '高德矢量' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('打开设置')).toBeInTheDocument();
    expect(screen.getByLabelText(/当前短会话/)).toBeInTheDocument();
    expect(screen.getByLabelText('退出登录')).toBeInTheDocument();
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

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '工作模式' }));
    fireEvent.click(await screen.findByText('浏览查看'));

    await waitFor(() => expect(screen.getByText('工作空间')).toBeInTheDocument());
    expect(useMapStore.getState().imagerySwipe.enabled).toBe(false);
    expect(useSettingsStore.getState().panels.layers).toBe(true);
  });

  it('reports stage-1 command feedback instead of leaving unfinished actions silent', async () => {
    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByLabelText('导入数据'));
    expect(screen.getByRole('status', { name: /导入入口已标记/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('保存项目'));
    expect(screen.getByRole('status', { name: /保存入口已标记/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('撤销'));
    expect(screen.getByRole('status', { name: /暂无可撤销操作/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('重做'));
    expect(screen.getByRole('status', { name: /暂无可重做操作/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('新增图层'));
    expect(screen.getByRole('status', { name: /新增图层入口已标记/ })).toBeInTheDocument();

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
    const firstLayer = useWorkspaceStore.getState().layers[0];
    useWorkspaceStore.setState({
      selectedLayerId: '1',
      layers: [{ ...firstLayer, id: '1', name: '后端地块', visible: true }],
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(['zip'], { type: 'application/zip' }), {
        status: 200,
        headers: { 'content-disposition': 'attachment; filename="womap-export-gdb.zip"' },
      }),
    );
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

    fireEvent.click(screen.getByLabelText('导出成果'));
    fireEvent.click(await screen.findByRole('radio', { name: 'GDB' }));
    fireEvent.click(screen.getByRole('button', { name: '导出 GDB' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(requestInit.body as string)).toEqual({
      format: 'gdb',
      layer_ids: [1],
    });
    expect(await screen.findByRole('status', { name: /GDB 导出完成/ })).toBeInTheDocument();
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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(initialSettings), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(updatedSettings), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    await loginToWorkbench();

    fireEvent.click(screen.getByLabelText('本地配置'));

    expect(await screen.findByRole('dialog', { name: '本地运行配置' })).toBeInTheDocument();
    expect(await screen.findByDisplayValue('9173')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('API Port'), { target: { value: '8100' } });
    fireEvent.change(screen.getByLabelText('Web Port'), { target: { value: '9273' } });
    fireEvent.click(screen.getByRole('button', { name: '写入本地配置' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const requestInit = fetchMock.mock.calls[1][1] as RequestInit;
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
