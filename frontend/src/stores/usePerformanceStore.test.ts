import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getPerformanceCapabilities } from '../services/api';
import type { PerformanceCapabilitySummary } from '../types/performance';
import { usePerformanceStore } from './usePerformanceStore';

vi.mock('../services/api', () => ({ getPerformanceCapabilities: vi.fn() }));

const capability: PerformanceCapabilitySummary = {
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
  cache: { enabled: true, ttlSeconds: 120, maxEntryKiB: 256 },
  runtimeMode: 'production',
  cpuLogicalCores: 12,
  totalMemoryBytes: null,
  availableMemoryBytes: null,
  gpu: {
    count: 0,
    label: '未检测到',
    cupyStatus: 'unavailable',
    executionEnabled: false,
    executionReason: 'no_gpu_detected',
    effectiveBackend: 'cpu',
    gateStatus: 'unavailable',
    benchmarkSpeedup: null,
  },
  queue: { status: 'available', queued: 0, running: 0 },
  warning: null,
};

beforeEach(() => {
  usePerformanceStore.getState().reset();
  vi.clearAllMocks();
});

describe('shared performance capability store', () => {
  it('deduplicates concurrent capability probes for panel and map consumers', async () => {
    vi.mocked(getPerformanceCapabilities).mockResolvedValue(capability);

    await Promise.all([
      usePerformanceStore.getState().load(),
      usePerformanceStore.getState().load(),
    ]);

    expect(getPerformanceCapabilities).toHaveBeenCalledTimes(1);
    expect(usePerformanceStore.getState().capabilities?.browser.vectorLimit).toBe(2000);
  });
});
