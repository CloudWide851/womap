import { LockKeyhole, ShieldCheck, TimerReset } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import womapLogo from '../../../logo.svg';
import { useAuthStore } from '../stores/useAuthStore';
import type { SessionMode } from '../types/workspace';

export function LoginPage() {
  const policy = useAuthStore((state) => state.policy);
  const error = useAuthStore((state) => state.error);
  const serviceStatus = useAuthStore((state) => state.serviceStatus);
  const submitting = useAuthStore((state) => state.submitting);
  const login = useAuthStore((state) => state.login);
  const setup = useAuthStore((state) => state.setup);
  const [username, setUsername] = useState(policy.username);
  const [password, setPassword] = useState('');
  const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [mode, setMode] = useState<SessionMode>('short');
  const firstRun = !policy.credentialConfigured;

  useEffect(() => {
    if (firstRun) setUsername(policy.username);
  }, [firstRun, policy.username]);

  const passwordScore = useMemo(() => {
    return Math.min(100, Math.round((password.length / policy.passwordMinLength) * 100));
  }, [password.length, policy.passwordMinLength]);
  const canSubmit =
    serviceStatus === 'ready' &&
    !submitting &&
    username.trim().length > 0 &&
    password.length >= policy.passwordMinLength &&
    (!firstRun || passwordConfirmation.length > 0);
  const submitLabel = submitting
    ? firstRun
      ? '正在设置…'
      : '正在验证…'
    : serviceStatus === 'unavailable'
      ? '本地服务未连接'
      : canSubmit
        ? firstRun
          ? '设置密码并进入'
          : '进入工作台'
        : `输入至少 ${policy.passwordMinLength} 位密码`;

  const submitLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (firstRun) {
      void setup({ username, password, passwordConfirmation, mode });
      return;
    }
    void login({ username, password, mode });
  };

  return (
    <main className="login-page">
      <section className="login-panel" aria-label="本地登录">
        <div className="login-brand">
          <img src={womapLogo} alt="WOMAP" />
        </div>

        <div className="login-panel-heading">
          <span className="security-emblem">
            <LockKeyhole size={19} aria-hidden="true" />
          </span>
          <h1>{firstRun ? '设置本地密码' : '进入工作台'}</h1>
        </div>

        {firstRun && (
          <p className="login-setup-note">
            首次使用请设置本机专用密码。系统只保存加盐后的不可逆哈希。
          </p>
        )}

        <form className="login-form" onSubmit={submitLogin}>
          <label>
            <span>账号</span>
            <input
              id="login-username"
              name="username"
              aria-label="登录账号"
              value={username}
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              readOnly={firstRun}
              disabled={submitting}
            />
            <em>默认账号 local-admin</em>
          </label>
          <label>
            <span>密码</span>
            <input
              id="login-password"
              name="password"
              aria-label="登录密码"
              type="password"
              value={password}
              autoComplete={firstRun ? 'new-password' : 'current-password'}
              minLength={policy.passwordMinLength}
              maxLength={policy.passwordMaxLength}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
            />
            <em>
              {firstRun
                ? `设置 ${policy.passwordMinLength}-${policy.passwordMaxLength} 位本机专用密码`
                : `密码不少于 ${policy.passwordMinLength} 位即可进入本地工作台`}
            </em>
          </label>

          {firstRun && (
            <label>
              <span>确认密码</span>
              <input
                id="login-password-confirmation"
                name="password-confirmation"
                aria-label="确认登录密码"
                type="password"
                value={passwordConfirmation}
                autoComplete="new-password"
                minLength={policy.passwordMinLength}
                maxLength={policy.passwordMaxLength}
                onChange={(event) => setPasswordConfirmation(event.target.value)}
                disabled={submitting}
              />
              <em>再次输入，避免首次密码设置错误</em>
            </label>
          )}

          <div className="password-meter" aria-label={`密码长度 ${password.length}`}>
            <span style={{ transform: `scaleX(${passwordScore / 100})` }} />
          </div>

          <div className="session-mode-group" aria-label="会话时长">
            <button
              type="button"
              className={mode === 'short' ? 'is-selected' : ''}
              aria-pressed={mode === 'short'}
              onClick={() => setMode('short')}
            >
              <TimerReset size={16} aria-hidden="true" />
              <span>短会话</span>
              <strong>{policy.idleTimeoutMinutes}分</strong>
            </button>
            <button
              type="button"
              className={mode === 'long' ? 'is-selected' : ''}
              aria-pressed={mode === 'long'}
              onClick={() => setMode('long')}
            >
              <ShieldCheck size={16} aria-hidden="true" />
              <span>长会话</span>
              <strong>{policy.rememberMeDays}天</strong>
            </button>
          </div>

          <button
            className="login-submit"
            type="submit"
            disabled={!canSubmit}
            aria-label={firstRun ? '设置本地密码并进入工作台' : '登录工作台'}
            aria-busy={submitting}
          >
            <LockKeyhole size={17} aria-hidden="true" />
            <span>{submitLabel}</span>
          </button>

          {error && <div className="login-error" role="alert">{error}</div>}
        </form>
      </section>
    </main>
  );
}
