import { afterEach, describe, expect, it, vi } from 'vitest';

import { getLayerFeatures } from './api';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('viewport API performance contract', () => {
  it('sends bounded browsing simplification and preserves explicit full geometry', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          type: 'FeatureCollection',
          features: [],
          meta: { limit: 1200, returned: 0, truncated: false },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getLayerFeatures('7', '0,0,10,10', 1200, undefined, 3, 2.5);
    await getLayerFeatures('7', '0,0,10,10', 1200, undefined, 3, 0);

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('simplify=2.5');
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('simplify=0');
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('limit=1200');
  });
});
