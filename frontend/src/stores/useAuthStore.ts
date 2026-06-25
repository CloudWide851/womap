import { create } from 'zustand';

import type { LoginSecurityPolicy, SessionMode } from '../types/workspace';

interface LoginInput {
  username: string;
  password: string;
  mode: SessionMode;
}

interface AuthState {
  authenticated: boolean;
  username: string | null;
  mode: SessionMode;
  expiresAt: number | null;
  renewalAt: number | null;
  now: number;
  error: string | null;
  policy: LoginSecurityPolicy;
  login: (input: LoginInput) => boolean;
  logout: () => void;
  tick: () => void;
  reset: () => void;
}

const policy: LoginSecurityPolicy = {
  username: 'local-admin',
  passwordMinLength: 15,
  passwordMaxLength: 128,
  lockoutAttempts: 5,
  lockoutWindowMinutes: 15,
  idleTimeoutMinutes: 30,
  absoluteTimeoutHours: 12,
  renewalTimeoutMinutes: 30,
  rememberMeDays: 7,
  policyRefreshSeconds: 30,
  warnBeforeExpireMinutes: 5,
  secureCookie: true,
  httpOnlyCookie: true,
  sameSite: 'lax',
  rotateAfterLogin: true,
  auditLogging: true,
};

const initialState = {
  authenticated: false,
  username: null,
  mode: 'short' as SessionMode,
  expiresAt: null,
  renewalAt: null,
  now: Date.now(),
  error: null,
  policy,
};

function getSessionDurationMs(mode: SessionMode) {
  if (mode === 'long') {
    return policy.rememberMeDays * 24 * 60 * 60 * 1000;
  }
  return policy.idleTimeoutMinutes * 60 * 1000;
}

export function formatRemainingTime(milliseconds: number) {
  if (milliseconds <= 0) {
    return '0分';
  }

  const safeSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const days = Math.floor(safeSeconds / 86_400);
  const hours = Math.floor((safeSeconds % 86_400) / 3_600);
  const minutes = Math.floor((safeSeconds % 3_600) / 60);

  if (days > 0) {
    return `${days}天${hours}时`;
  }
  if (hours > 0) {
    return `${hours}时${minutes}分`;
  }
  return `${Math.max(1, minutes)}分`;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  ...initialState,
  login: ({ username, password, mode }) => {
    const trimmedUsername = username.trim();
    const currentPolicy = get().policy;

    if (!trimmedUsername) {
      set({ error: '账号不能为空' });
      return false;
    }

    if (
      password.length < currentPolicy.passwordMinLength ||
      password.length > currentPolicy.passwordMaxLength
    ) {
      set({ error: `密码长度需为 ${currentPolicy.passwordMinLength}-${currentPolicy.passwordMaxLength}` });
      return false;
    }

    const now = Date.now();
    set({
      authenticated: true,
      username: trimmedUsername,
      mode,
      expiresAt: now + getSessionDurationMs(mode),
      renewalAt: now + currentPolicy.renewalTimeoutMinutes * 60 * 1000,
      now,
      error: null,
    });
    return true;
  },
  logout: () =>
    set({
      authenticated: false,
      username: null,
      expiresAt: null,
      renewalAt: null,
      now: Date.now(),
      error: null,
    }),
  tick: () => {
    const now = Date.now();
    const current = get();

    if (current.authenticated && current.expiresAt !== null && current.expiresAt <= now) {
      set({
        authenticated: false,
        username: null,
        expiresAt: null,
        renewalAt: null,
        now,
        error: '会话已过期，请重新登录',
      });
      return;
    }

    set({ now });
  },
  reset: () => set({ ...initialState, now: Date.now() }),
}));
