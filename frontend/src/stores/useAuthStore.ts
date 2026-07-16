import { create } from 'zustand';

import {
  ApiRequestError,
  clearAuthSessionHint,
  configureCsrfCookie,
  getAuthPolicy,
  getAuthSession,
  getHealth,
  hasAuthSessionHint,
  loginAuth,
  logoutAuth,
  renewAuthSession,
  setupAuth,
  type AuthPolicyApiResponse,
  type AuthSessionApiResponse,
} from '../services/api';
import type { LoginSecurityPolicy, SessionMode } from '../types/workspace';

interface LoginInput {
  username: string;
  password: string;
  mode: SessionMode;
}

interface SetupInput extends LoginInput {
  passwordConfirmation: string;
}

type ServiceStatus = 'checking' | 'ready' | 'unavailable';

interface AuthState {
  initialized: boolean;
  initializing: boolean;
  submitting: boolean;
  renewing: boolean;
  serviceStatus: ServiceStatus;
  authenticated: boolean;
  username: string | null;
  mode: SessionMode;
  expiresAt: number | null;
  renewalAt: number | null;
  now: number;
  error: string | null;
  policy: LoginSecurityPolicy;
  initialize: () => Promise<void>;
  refreshPolicy: () => Promise<void>;
  login: (input: LoginInput) => Promise<boolean>;
  setup: (input: SetupInput) => Promise<boolean>;
  logout: () => Promise<void>;
  renew: () => Promise<void>;
  handleUnauthorized: () => void;
  tick: () => void;
  reset: () => void;
}

const defaultPolicy: LoginSecurityPolicy = {
  enabled: true,
  username: 'local-admin',
  credentialConfigured: false,
  passwordMinLength: 15,
  passwordMaxLength: 128,
  blockCommonPasswords: true,
  lockoutAttempts: 5,
  lockoutWindowMinutes: 15,
  idleTimeoutMinutes: 30,
  absoluteTimeoutHours: 12,
  renewalTimeoutMinutes: 30,
  rememberMeDays: 7,
  cookieName: 'womap_session',
  policyRefreshSeconds: 30,
  warnBeforeExpireMinutes: 5,
  secureCookie: true,
  httpOnlyCookie: true,
  sameSite: 'lax',
  rotateAfterLogin: true,
  auditLogging: true,
  redactSessionId: true,
};

const initialState = {
  initialized: false,
  initializing: false,
  submitting: false,
  renewing: false,
  serviceStatus: 'checking' as ServiceStatus,
  authenticated: false,
  username: null,
  mode: 'short' as SessionMode,
  expiresAt: null,
  renewalAt: null,
  now: Date.now(),
  error: null,
  policy: defaultPolicy,
};

function policyFromApi(policy: AuthPolicyApiResponse): LoginSecurityPolicy {
  return {
    enabled: policy.enabled,
    username: policy.username,
    credentialConfigured: policy.credential_configured,
    passwordMinLength: policy.password_min_length,
    passwordMaxLength: policy.password_max_length,
    blockCommonPasswords: policy.block_common_passwords,
    lockoutAttempts: policy.lockout_attempts,
    lockoutWindowMinutes: policy.lockout_window_minutes,
    idleTimeoutMinutes: policy.idle_timeout_minutes,
    absoluteTimeoutHours: policy.absolute_timeout_hours,
    renewalTimeoutMinutes: policy.renewal_timeout_minutes,
    rememberMeDays: policy.remember_me_days,
    cookieName: policy.cookie_name,
    policyRefreshSeconds: policy.policy_refresh_seconds,
    warnBeforeExpireMinutes: policy.warn_before_expire_minutes,
    secureCookie: policy.secure_cookie,
    httpOnlyCookie: policy.http_only_cookie,
    sameSite: policy.same_site,
    rotateAfterLogin: policy.rotate_after_login,
    auditLogging: policy.audit_logging,
    redactSessionId: policy.redact_session_id,
  };
}

function sessionState(session: AuthSessionApiResponse) {
  const now = Date.now();
  return {
    authenticated: session.authenticated,
    username: session.username,
    mode: session.session_mode,
    expiresAt: now + session.expires_in_seconds * 1000,
    renewalAt: now + session.renewal_in_seconds * 1000,
    now,
    error: null,
  };
}

function messageFrom(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function formatRemainingTime(milliseconds: number) {
  if (milliseconds <= 0) return '0分';
  const safeSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const days = Math.floor(safeSeconds / 86_400);
  const hours = Math.floor((safeSeconds % 86_400) / 3_600);
  const minutes = Math.floor((safeSeconds % 3_600) / 60);
  if (days > 0) return `${days}天${hours}时`;
  if (hours > 0) return `${hours}时${minutes}分`;
  return `${Math.max(1, minutes)}分`;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  ...initialState,
  initialize: async () => {
    if (get().initializing || get().initialized) return;
    set({ initializing: true, serviceStatus: 'checking', error: null });
    try {
      await getHealth();
      const policy = policyFromApi(await getAuthPolicy());
      configureCsrfCookie(policy.cookieName);
      set({ policy, serviceStatus: 'ready' });
      if (!policy.credentialConfigured || !hasAuthSessionHint()) return;
      try {
        const session = await getAuthSession();
        set(sessionState(session));
      } catch (error) {
        if (!(error instanceof ApiRequestError) || error.status !== 401) throw error;
        clearAuthSessionHint(policy.secureCookie, policy.sameSite);
      }
    } catch (error) {
      set({
        serviceStatus: 'unavailable',
        error: messageFrom(error, '后端服务不可用，请启动 WOMAP 服务后重试。'),
      });
    } finally {
      set({ initialized: true, initializing: false });
    }
  },
  refreshPolicy: async () => {
    try {
      const policy = policyFromApi(await getAuthPolicy());
      configureCsrfCookie(policy.cookieName);
      set({ policy, serviceStatus: 'ready' });
    } catch {
      set({ serviceStatus: 'unavailable' });
    }
  },
  login: async ({ username, password, mode }) => {
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
    set({ submitting: true, error: null });
    try {
      const session = await loginAuth(trimmedUsername, password, mode);
      set({ ...sessionState(session), serviceStatus: 'ready' });
      return true;
    } catch (error) {
      set({ error: messageFrom(error, '登录失败，请重试。') });
      return false;
    } finally {
      set({ submitting: false });
    }
  },
  setup: async ({ username, password, passwordConfirmation, mode }) => {
    const trimmedUsername = username.trim();
    const currentPolicy = get().policy;
    if (!trimmedUsername) {
      set({ error: '账号不能为空' });
      return false;
    }
    if (trimmedUsername !== currentPolicy.username) {
      set({ error: `首次设置请使用本地账号 ${currentPolicy.username}` });
      return false;
    }
    if (
      password.length < currentPolicy.passwordMinLength ||
      password.length > currentPolicy.passwordMaxLength
    ) {
      set({ error: `密码长度需为 ${currentPolicy.passwordMinLength}-${currentPolicy.passwordMaxLength}` });
      return false;
    }
    if (password !== passwordConfirmation) {
      set({ error: '两次输入的密码不一致' });
      return false;
    }

    set({ submitting: true, error: null });
    try {
      const session = await setupAuth(trimmedUsername, password, passwordConfirmation, mode);
      set({
        ...sessionState(session),
        serviceStatus: 'ready',
        policy: { ...currentPolicy, credentialConfigured: true },
      });
      return true;
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 409) {
        await get().refreshPolicy();
      }
      set({ error: messageFrom(error, '本地密码设置失败，请重试。') });
      return false;
    } finally {
      set({ submitting: false });
    }
  },
  logout: async () => {
    try {
      if (get().authenticated) await logoutAuth();
    } catch {
      // Local state must still be cleared if the server session has already expired.
    } finally {
      const policy = get().policy;
      clearAuthSessionHint(policy.secureCookie, policy.sameSite);
      set({
        authenticated: false,
        username: null,
        expiresAt: null,
        renewalAt: null,
        now: Date.now(),
        error: null,
      });
    }
  },
  renew: async () => {
    if (!get().authenticated || get().renewing) return;
    set({ renewing: true });
    try {
      set(sessionState(await renewAuthSession()));
    } catch {
      get().handleUnauthorized();
    } finally {
      set({ renewing: false });
    }
  },
  handleUnauthorized: () => {
    const policy = get().policy;
    clearAuthSessionHint(policy.secureCookie, policy.sameSite);
    set({
      authenticated: false,
      username: null,
      expiresAt: null,
      renewalAt: null,
      now: Date.now(),
      error: '会话已过期，请重新登录',
    });
  },
  tick: () => {
    const now = Date.now();
    const current = get();
    if (current.authenticated && current.expiresAt !== null && current.expiresAt <= now) {
      current.handleUnauthorized();
      return;
    }
    set({ now });
    if (current.authenticated && current.renewalAt !== null && current.renewalAt <= now) {
      void current.renew();
    }
  },
  reset: () => set({ ...initialState, now: Date.now() }),
}));
