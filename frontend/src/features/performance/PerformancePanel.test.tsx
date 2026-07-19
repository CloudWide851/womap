import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getPerformanceCapabilities } from '../../services/api';
import { usePerformanceStore } from '../../stores/usePerformanceStore';
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
  usePerformanceStore.getState().reset();
  vi.mocked(getPerformanceCapabilities).mockResolvedValue({
    profile: {
      requested: 'auto',
      resolved: 'balanced',
      enforcement: 'active',
      gdalThreads: 4,
      gdalCacheMiB: 512,
      gdalDatasetPoolSize: 64,
      formulaWindowBudgetMiB: 128,
      scratchReserveGiB: 5,
      databasePoolSize: 8,
      databaseMaxOverflow: 2,
    },
    browser: {
      vectorLimit: 2000,
      bboxDebounceMs: 180,
      webglTextureCache: 256,
      geotiffCacheSize: 48,
      incrementalSourceUpdates: false,
      browseSimplifyMaxTolerance: 5,
    },
    cache: { enabled: false, ttlSeconds: 120, maxEntryKiB: 256 },
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
      effectiveBackend: 'cpu',
      gateStatus: 'unavailable',
      benchmarkSpeedup: null,
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
    expect(screen.getByText('CuPy 未安装')).toBeInTheDocument();
    expect(screen.getByText('4 线程 / 512 MiB')).toBeInTheDocument();
    expect(getPerformanceCapabilities).toHaveBeenCalledTimes(1);
  });

  it('does not describe a device or driver failure as a missing CuPy install', async () => {
    vi.mocked(getPerformanceCapabilities).mockResolvedValue({
      ...(await vi.mocked(getPerformanceCapabilities)()),
      gpu: {
        count: 1,
        label: 'Example GPU',
        cupyStatus: 'available',
        executionEnabled: false,
        executionReason: 'gpu_runtime_error',
        effectiveBackend: 'cpu',
        gateStatus: 'unavailable',
        benchmarkSpeedup: null,
      },
    });

    render(<PerformancePanel />);

    expect(await screen.findByText('GPU 环境不可用')).toBeInTheDocument();
    expect(screen.queryByText('CuPy 未安装')).not.toBeInTheDocument();
  });
});
