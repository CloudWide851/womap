import { afterEach, describe, expect, it, vi } from 'vitest';

import { decodePerformanceCapabilities, getPerformanceCapabilities } from './api';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const rawCapability = {
  system: {
    cpu: { logical_cores: 16 },
    memory: { total_bytes: 32 * 1024 ** 3, available_bytes: 20 * 1024 ** 3 },
  },
  gpus: [{ name: 'Example GPU' }],
  software: { cupy: { status: 'unavailable' } },
  runtime: {
    mode: 'development',
    gpu_execution_enabled: false,
    gpu_execution_reason: 'cpu_backend_is_default',
    profile: {
      requested_profile: 'auto',
      resolved_profile: 'high',
      enforcement: 'diagnostic',
      gdal_threads: 8,
      gdal_cache_mib: 1024,
    },
  },
  queue: { status: 'available', queued: 1, running: 0 },
  recommendations: [],
};

describe('performance capability API boundary', () => {
  it('normalizes the wire response once at the API boundary', () => {
    expect(decodePerformanceCapabilities(rawCapability)).toMatchObject({
      profile: { requested: 'auto', resolved: 'high', gdalThreads: 8, gdalCacheMiB: 1024 },
      cpuLogicalCores: 16,
      gpu: { count: 1, label: 'Example GPU', executionEnabled: false },
      queue: { status: 'available', queued: 1, running: 0 },
    });
  });

  it('uses the authenticated API fetch path and supports cancellation', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(rawCapability), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();

    const result = await getPerformanceCapabilities(controller.signal);

    expect(result.profile.resolved).toBe('high');
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/performance/capabilities');
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe('include');
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });
});
