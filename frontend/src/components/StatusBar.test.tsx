import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useAuthStore } from '../stores/useAuthStore';
import { useMapStore } from '../stores/useMapStore';
import { useWorkspaceContextStore } from '../stores/useWorkspaceContextStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { StatusBar } from './StatusBar';

afterEach(() => {
  cleanup();
  useWorkspaceContextStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useMapStore.getState().reset();
  useAuthStore.getState().reset();
});

describe('StatusBar', () => {
  it('shows the selected layer and each real save state', () => {
    const selected = useWorkspaceStore.getState().layers[0];
    act(() => useWorkspaceStore.setState({ selectedLayerId: selected.id }));
    render(<StatusBar />);

    expect(screen.getByLabelText(`选中图层 ${selected.name}`)).toBeInTheDocument();
    expect(screen.getByLabelText('保存状态 已保存')).toBeInTheDocument();

    act(() => useWorkspaceContextStore.setState({ dirty: true }));
    expect(screen.getByLabelText('保存状态 有未保存更改')).toBeInTheDocument();

    act(() => useWorkspaceContextStore.setState({ saving: true }));
    expect(screen.getByLabelText('保存状态 保存中')).toBeInTheDocument();

    act(() =>
      useWorkspaceContextStore.setState({ saving: false, saveError: 'revision conflict' }),
    );
    expect(screen.getByLabelText('保存状态 保存失败')).toBeInTheDocument();
  });

  it('does not mislabel a workspace loading error as a save failure', () => {
    act(() =>
      useWorkspaceContextStore.setState({ error: '工作空间初始化失败', saveError: null }),
    );
    render(<StatusBar />);

    expect(screen.getByLabelText('保存状态 已保存')).toBeInTheDocument();
    expect(screen.queryByLabelText('保存状态 保存失败')).not.toBeInTheDocument();
  });

  it('shows the current backend service status', () => {
    render(<StatusBar />);

    expect(screen.getByLabelText('后端服务 检查中')).toBeInTheDocument();
    act(() => useAuthStore.setState({ serviceStatus: 'ready' }));
    expect(screen.getByLabelText('后端服务 已连接')).toBeInTheDocument();
    act(() => useAuthStore.setState({ serviceStatus: 'unavailable' }));
    expect(screen.getByLabelText('后端服务 不可用')).toBeInTheDocument();
  });
});
