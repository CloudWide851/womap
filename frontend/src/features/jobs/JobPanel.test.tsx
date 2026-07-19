import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getJobs: vi.fn(),
  downloadRasterExport: vi.fn(),
  downloadVectorExport: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

import { JobPanel } from './JobPanel';
import { useJobsStore } from '../../stores/useJobsStore';
import type { ImportJob } from '../../types/imports';

const vectorJob: ImportJob = {
  id: 'vector-export-1',
  job_type: 'vector-export',
  status: 'done',
  progress: 100,
  message: '矢量成果导出已完成。',
  detail: {
    kind: 'vector-export',
    stage: 'done',
    processed_layers: 2,
    total_layers: 2,
    artifact_name: 'womap-vector-shp.zip',
    warnings: [],
    error: null,
  },
};

const fallbackRasterJob: ImportJob = {
  id: 'raster-derive-1',
  job_type: 'raster-derive',
  status: 'done',
  progress: 100,
  message: '派生栅格已生成；GPU 失败后已完整回退 CPU。',
  detail: {
    kind: 'raster-process',
    stage: 'completed',
    operation: 'derive',
    source_id: null,
    dataset_id: null,
    layer_id: 9,
    dataset_name: '派生栅格',
    processed_bytes: 0,
    total_bytes: 0,
    processed_blocks: 4,
    total_blocks: 4,
    formula_backend: {
      requested_backend: 'auto',
      effective_backend: 'cpu',
      gate_status: 'fallback',
      fallback_reason: 'gpu_oom',
      fallback_attempt_ms: 125,
      max_batch_windows: 1,
    },
    warnings: [],
    error: null,
  },
};

describe('JobPanel', () => {
  beforeEach(() => {
    apiMocks.getJobs.mockResolvedValue([vectorJob]);
    apiMocks.downloadVectorExport.mockResolvedValue({
      blob: new Blob(['vector zip'], { type: 'application/zip' }),
      filename: 'womap-vector-shp.zip',
    });
    useJobsStore.setState({ jobs: [vectorJob], loading: false });
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:womap-vector-export'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    useJobsStore.getState().reset();
    vi.restoreAllMocks();
  });

  it('shows typed vector progress and downloads the completed artifact', async () => {
    render(<JobPanel />);

    expect(screen.getByText('矢量成果导出')).toBeInTheDocument();
    expect(screen.getByLabelText('vector-export 进度 100%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下载矢量成果导出' }));

    await waitFor(() =>
      expect(apiMocks.downloadVectorExport).toHaveBeenCalledWith('vector-export-1'),
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:womap-vector-export');
  });

  it('shows the safe raster formula fallback state', async () => {
    apiMocks.getJobs.mockResolvedValue([fallbackRasterJob]);
    useJobsStore.setState({ jobs: [fallbackRasterJob], loading: false });

    render(<JobPanel />);

    expect(screen.getByText('公式计算 · GPU 失败后 CPU 回退')).toBeInTheDocument();
  });
});
