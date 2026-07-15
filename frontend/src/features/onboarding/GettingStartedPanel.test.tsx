import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../stores/useAuthStore';
import { useWorkspaceContextStore } from '../../stores/useWorkspaceContextStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { WorkspaceDetail } from '../../types/workspaces';
import { GettingStartedPanel } from './GettingStartedPanel';

afterEach(() => {
  cleanup();
  useWorkspaceContextStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useAuthStore.getState().reset();
  vi.restoreAllMocks();
});

describe('GettingStartedPanel', () => {
  it('offers working service, settings, import, and save actions for first-time users', async () => {
    const openSettings = vi.fn();
    const saveCurrent = vi.fn(async () => ({ id: 1 }) as WorkspaceDetail);
    const openImport = vi.fn();
    const refreshPolicy = vi.fn(async () => undefined);
    window.addEventListener('womap:open-import-center', openImport);
    act(() =>
      useWorkspaceContextStore.setState({
        current: { id: 1 } as WorkspaceDetail,
        dirty: true,
        saveCurrent,
      }),
    );
    act(() => useAuthStore.setState({ serviceStatus: 'unavailable', refreshPolicy }));
    render(<GettingStartedPanel onOpenSettings={openSettings} />);

    expect(screen.getByRole('heading', { name: '四步加入自己的地图数据' })).toBeInTheDocument();
    expect(screen.getByText(/示例.*不会作为后端成果导出/)).toBeInTheDocument();
    expect(screen.getByText('服务不可用')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    fireEvent.click(screen.getByRole('button', { name: /配置/ }));
    fireEvent.click(screen.getByRole('button', { name: /导入/ }));
    fireEvent.click(screen.getByRole('button', { name: /保存/ }));

    expect(openSettings).toHaveBeenCalledTimes(1);
    expect(refreshPolicy).toHaveBeenCalledTimes(1);
    expect(openImport).toHaveBeenCalledTimes(1);
    expect(saveCurrent).toHaveBeenCalledTimes(1);
    window.removeEventListener('womap:open-import-center', openImport);
  });

  it('disappears after real backend data is available', () => {
    const demo = useWorkspaceStore.getState().layers[0];
    act(() =>
      useWorkspaceStore.setState({ layers: [{ ...demo, id: '9', source: 'backend' }] }),
    );
    const { container } = render(<GettingStartedPanel onOpenSettings={() => undefined} />);

    expect(container).toBeEmptyDOMElement();
  });
});
