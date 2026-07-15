import { afterEach, describe, expect, it, vi } from 'vitest';

import { formatRemainingTime, useAuthStore } from './useAuthStore';

const policyResponse = {
  enabled: true,
  username: 'local-admin',
  credential_configured: true,
  password_min_length: 15,
  password_max_length: 128,
  block_common_passwords: true,
  lockout_attempts: 5,
  lockout_window_minutes: 15,
  idle_timeout_minutes: 30,
  absolute_timeout_hours: 12,
  renewal_timeout_minutes: 30,
  remember_me_days: 7,
  cookie_name: 'womap_session',
  secure_cookie: true,
  http_only_cookie: true,
  same_site: 'lax',
  policy_refresh_seconds: 30,
  warn_before_expire_minutes: 5,
  rotate_after_login: true,
  audit_logging: true,
  redact_session_id: true,
};

const sessionResponse = {
  authenticated: true,
  username: 'local-admin',
  session_mode: 'short',
  expires_in_seconds: 1800,
  renewal_in_seconds: 900,
  policy_refresh_seconds: 30,
  message: '登录成功。',
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useAuthStore.getState().reset();
});

describe('auth store', () => {
  it('loads the backend policy and treats a missing session as signed out', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith('/health/live')) {
          return new Response(JSON.stringify({ status: 'alive' }), { status: 200 });
        }
        if (url.endsWith('/auth/policy')) {
          return new Response(JSON.stringify(policyResponse), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: '登录会话无效或已过期。' }), {
          status: 401,
        });
      }),
    );

    await useAuthStore.getState().initialize();

    expect(useAuthStore.getState()).toMatchObject({
      initialized: true,
      serviceStatus: 'ready',
      authenticated: false,
    });
    expect(useAuthStore.getState().policy.credentialConfigured).toBe(true);
  });

  it('rejects attempts below the server policy before sending credentials', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const loggedIn = await useAuthStore.getState().login({
      username: 'local-admin',
      password: 'short',
      mode: 'short',
    });

    expect(loggedIn).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().error).toContain('密码长度需为');
  });

  it('authenticates through the backend and expires the current session locally', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(sessionResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const loggedIn = await useAuthStore.getState().login({
      username: 'local-admin',
      password: 'local-passphrase-2026',
      mode: 'short',
    });

    expect(loggedIn).toBe(true);
    expect(useAuthStore.getState().authenticated).toBe(true);
    const request = fetchMock.mock.calls[0];
    const init = request?.[1] ?? {};
    expect(init).toMatchObject({ credentials: 'include', method: 'POST' });
    expect(JSON.parse(init.body as string)).toMatchObject({ session_mode: 'short' });

    useAuthStore.setState({ expiresAt: Date.now() - 1 });
    useAuthStore.getState().tick();

    expect(useAuthStore.getState().authenticated).toBe(false);
    expect(useAuthStore.getState().error).toBe('会话已过期，请重新登录');
  });

  it('formats expired and long sessions without overstating remaining time', () => {
    expect(formatRemainingTime(0)).toBe('0分');
    expect(formatRemainingTime(7 * 24 * 60 * 60 * 1000)).toBe('7天0时');
  });
});
