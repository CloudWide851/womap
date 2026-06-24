import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('renders the professional GIS workbench shell', () => {
    render(<App />);

    expect(screen.getByText('WOMAP')).toBeInTheDocument();
    expect(screen.getByText('工作空间')).toBeInTheDocument();
    expect(screen.getAllByText('底图').length).toBeGreaterThan(0);
    expect(screen.getAllByText('性能').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('导入数据')).toBeInTheDocument();
    expect(screen.getByLabelText('新增图层')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '高德矢量' })).toBeInTheDocument();
    expect(screen.getByLabelText('隐藏性能面板')).toBeInTheDocument();
  });
});
