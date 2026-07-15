import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AUTH_UNAUTHORIZED_EVENT,
  apiFetch,
  configureCsrfCookie,
  deleteLayerFeature,
  updateLayerFeature,
} from './api';

afterEach(() => {
  document.cookie = 'womap_session_csrf=; Max-Age=0; path=/';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('apiFetch', () => {
  it('includes credentials and the CSRF token on unsafe requests', async () => {
    configureCsrfCookie('womap_session');
    document.cookie = 'womap_session_csrf=csrf-test-token; path=/';
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response('{}', { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('http://127.0.0.1/api/v1/layers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });

    const init = fetchMock.mock.calls[0]?.[1] ?? {};
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe('include');
    expect(headers.get('X-WOMAP-CSRF')).toBe('csrf-test-token');
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('announces business-route 401 responses without treating login rejection as expiry', async () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, listener);
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));

    await apiFetch('http://127.0.0.1/api/v1/layers');
    await apiFetch('http://127.0.0.1/api/v1/auth/login', { method: 'POST' });

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, listener);
  });

  it('sends optimistic revisions for feature updates and deletes', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ feature: {}, layer: {} }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const coordinates = [[[0, 0], [10, 0], [0, 10], [0, 0]]];

    await updateLayerFeature('7', 11, coordinates, { name: '宗地 A' }, 4);
    await deleteLayerFeature('7', 11, 5);

    const update = fetchMock.mock.calls[0];
    expect(String(update?.[0])).toContain('/api/v1/layers/7/features/11');
    expect(update?.[1]?.method).toBe('PUT');
    expect(JSON.parse(update?.[1]?.body as string)).toEqual({
      geometry: { type: 'Polygon', coordinates },
      properties: { name: '宗地 A' },
      revision: 4,
    });
    const deletion = fetchMock.mock.calls[1];
    expect(String(deletion?.[0])).toContain('/api/v1/layers/7/features/11?revision=5');
    expect(deletion?.[1]?.method).toBe('DELETE');
  });
});
