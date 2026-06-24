import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from './App';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

afterEach(() => {
  useWorkspaceStore.getState().closeInspector();
  cleanup();
});

describe('App', () => {
  it('renders the professional GIS workbench shell', () => {
    render(<App />);

    expect(screen.getByText('WOMAP')).toBeInTheDocument();
    expect(screen.getByTestId('brand-logo')).toBeInTheDocument();
    expect(screen.getByText('工作空间')).toBeInTheDocument();
    expect(screen.getAllByText('底图').length).toBeGreaterThan(0);
    expect(screen.getAllByText('性能').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('导入数据')).toBeInTheDocument();
    expect(screen.getByLabelText('新增图层')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '高德矢量' })).toBeInTheDocument();
    expect(screen.getByLabelText('打开设置')).toBeInTheDocument();
  });

  it('separates settings from the main workspace surface', async () => {
    render(<App />);

    fireEvent.click(screen.getAllByLabelText('打开设置')[0]);

    expect(await screen.findByRole('heading', { name: '工作台设置' })).toBeInTheDocument();
    expect(screen.getByLabelText('返回工作台')).toBeInTheDocument();
    expect(screen.getByLabelText('隐藏性能面板')).toBeInTheDocument();
    expect(screen.queryByLabelText('新增图层')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('返回工作台'));
    await waitFor(() => expect(screen.getByText('工作空间')).toBeInTheDocument());
  });

  it('opens layer and feature attributes on demand', async () => {
    render(<App />);

    fireEvent.click(screen.getAllByLabelText('查看 项目边界 属性')[0]);

    expect(await screen.findByRole('dialog', { name: '项目边界' })).toBeInTheDocument();
    expect(screen.getAllByText('加载策略').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText('关闭属性检查器'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('P-102 查看示例图斑属性'));

    expect(await screen.findByRole('dialog', { name: '边界图斑 102' })).toBeInTheDocument();
    expect(screen.getByText('项目编号')).toBeInTheDocument();
  });
});
