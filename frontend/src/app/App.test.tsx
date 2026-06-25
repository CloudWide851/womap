import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from './App';
import { useAuthStore } from '../stores/useAuthStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

afterEach(() => {
  useAuthStore.getState().reset();
  useWorkspaceStore.getState().closeInspector();
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
  });

  it('renders the professional GIS workbench shell', async () => {
    render(<App />);
    await loginToWorkbench();

    expect(screen.getByTestId('brand-logo')).toBeInTheDocument();
    expect(screen.queryByText('WOMAP')).not.toBeInTheDocument();
    expect(screen.queryByText('图斑工坊')).not.toBeInTheDocument();
    expect(screen.getByText('工作空间')).toBeInTheDocument();
    expect(screen.getAllByText('底图').length).toBeGreaterThan(0);
    expect(screen.getAllByText('性能').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('导入数据')).toBeInTheDocument();
    expect(screen.getByLabelText('新增图层')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '高德矢量' })).toBeInTheDocument();
    expect(screen.getByLabelText('打开设置')).toBeInTheDocument();
    expect(screen.getByLabelText(/当前短会话/)).toBeInTheDocument();
    expect(screen.getByLabelText('退出登录')).toBeInTheDocument();
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

  it('opens layer and feature attributes on demand', async () => {
    render(<App />);
    await loginToWorkbench();

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
