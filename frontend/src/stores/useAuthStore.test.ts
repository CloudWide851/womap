import { afterEach, describe, expect, it } from 'vitest';

import { formatRemainingTime, useAuthStore } from './useAuthStore';

afterEach(() => {
  useAuthStore.getState().reset();
});

describe('auth store', () => {
  it('rejects local login attempts below the configured password length', () => {
    const loggedIn = useAuthStore.getState().login({
      username: 'local-admin',
      password: 'short',
      mode: 'short',
    });

    expect(loggedIn).toBe(false);
    expect(useAuthStore.getState().authenticated).toBe(false);
    expect(useAuthStore.getState().error).toContain('密码长度需为');
  });

  it('expires the current session when the timer passes expiresAt', () => {
    const loggedIn = useAuthStore.getState().login({
      username: 'local-admin',
      password: 'local-passphrase-2026',
      mode: 'short',
    });

    expect(loggedIn).toBe(true);

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
