import { LockKeyhole, MapPinned, RotateCw, ShieldCheck, TimerReset, UploadCloud } from 'lucide-react';
import { FormEvent, useMemo, useState } from 'react';

import womapLogo from '../../../logo.svg';
import { formatRemainingTime, useAuthStore } from '../stores/useAuthStore';
import type { SessionMode } from '../types/workspace';

const launchSteps = [
  { label: '导入', icon: UploadCloud },
  { label: '叠图', icon: MapPinned },
  { label: '校验', icon: ShieldCheck },
];

export function LoginPage() {
  const policy = useAuthStore((state) => state.policy);
  const error = useAuthStore((state) => state.error);
  const login = useAuthStore((state) => state.login);
  const [username, setUsername] = useState(policy.username);
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<SessionMode>('short');

  const passwordScore = useMemo(() => {
    return Math.min(100, Math.round((password.length / policy.passwordMinLength) * 100));
  }, [password.length, policy.passwordMinLength]);
  const canLogin = username.trim().length > 0 && password.length >= policy.passwordMinLength;
  const sessionDuration =
    mode === 'long'
      ? policy.rememberMeDays * 24 * 60 * 60 * 1000
      : policy.idleTimeoutMinutes * 60 * 1000;

  const submitLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    login({ username, password, mode });
  };

  return (
    <main className="login-page">
      <section className="login-stage" aria-label="工作台预览">
        <div className="login-brand">
          <img src={womapLogo} alt="WOMAP" />
        </div>

        <div className="login-map-preview" aria-hidden="true">
          <div className="login-map-line login-map-line-a" />
          <div className="login-map-line login-map-line-b" />
          <div className="login-map-area" />
          <div className="login-map-pin" />
          <div className="login-map-strip">
            {launchSteps.map((step) => {
              const Icon = step.icon;
              return (
                <span key={step.label}>
                  <Icon size={15} />
                  {step.label}
                </span>
              );
            })}
          </div>
        </div>
      </section>

      <section className="login-panel" aria-label="本地登录">
        <div className="login-panel-heading">
          <span className="security-emblem">
            <LockKeyhole size={19} aria-hidden="true" />
          </span>
          <div>
            <p>本地安全门禁</p>
            <h1>进入工作台</h1>
          </div>
        </div>

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
            />
          </label>
          <label>
            <span>密码</span>
            <input
              id="login-password"
              name="password"
              aria-label="登录密码"
              type="password"
              value={password}
              autoComplete="current-password"
              minLength={policy.passwordMinLength}
              maxLength={policy.passwordMaxLength}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

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

          <button className="login-submit" type="submit" disabled={!canLogin} aria-label="登录工作台">
            <LockKeyhole size={17} aria-hidden="true" />
            <span>进入</span>
          </button>

          {error && <div className="login-error" role="alert">{error}</div>}
        </form>

        <div className="login-security-grid">
          <span>
            <ShieldCheck size={15} aria-hidden="true" />
            {policy.passwordMinLength}-{policy.passwordMaxLength}
          </span>
          <span>
            <TimerReset size={15} aria-hidden="true" />
            {formatRemainingTime(sessionDuration)}
          </span>
          <span>
            <RotateCw size={15} aria-hidden="true" />
            {policy.policyRefreshSeconds}s
          </span>
        </div>
      </section>
    </main>
  );
}
