import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getPerformanceCapabilities } from '../../services/api';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import { detectWebGLCapabilities } from './webgl';
import { PerformancePanel } from './PerformancePanel';

vi.mock('../../services/api', () => ({
  getPerformanceCapabilities: vi.fn(),
}));

vi.mock('./webgl', () => ({
  detectWebGLCapabilities: vi.fn(),
}));

beforeEach(() => {
  useWorkspaceStore.getState().reset();
  vi.mocked(getPerformanceCapabilities).mockResolvedValue({
    profile: {
      requested: 'auto',
      resolved: 'balanced',
      enforcement: 'diagnostic',
      gdalThreads: 4,
      gdalCacheMiB: 512,
    },
    runtimeMode: 'development',
    cpuLogicalCores: 12,
    totalMemoryBytes: 32 * 1024 ** 3,
    availableMemoryBytes: 18 * 1024 ** 3,
    gpu: {
      count: 1,
      label: 'Example GPU',
      cupyStatus: 'unavailable',
      executionEnabled: false,
      executionReason: 'cupy_runtime_unavailable',
    },
    queue: { status: 'available', queued: 0, running: 0 },
    warning: null,
  });
  vi.mocked(detectWebGLCapabilities).mockReturnValue({
    status: 'available',
    version: 2,
    rendererStatus: 'restricted',
    vendor: null,
    renderer: null,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PerformancePanel', () => {
  it('loads diagnostics only when mounted and distinguishes render GPU from compute GPU', async () => {
    render(<PerformancePanel />);

    expect(await screen.findByText('均衡')).toBeInTheDocument();
    expect(screen.getByText('WebGL 2')).toBeInTheDocument();
    expect(screen.getByText('隐私限制')).toBeInTheDocument();
    expect(screen.getByText('GPU 待基准 / CPU 生效')).toBeInTheDocument();
    expect(screen.getByText('4 线程 / 512 MiB')).toBeInTheDocument();
    expect(getPerformanceCapabilities).toHaveBeenCalledTimes(1);
  });
});
