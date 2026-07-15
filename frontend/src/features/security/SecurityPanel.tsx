import { KeyRound, LockKeyhole, RotateCw, ShieldCheck, TimerReset } from 'lucide-react';
import { memo } from 'react';
import type { ReactNode } from 'react';

import { formatRemainingTime, useAuthStore } from '../../stores/useAuthStore';

const SecurityRow = memo(function SecurityRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="security-row">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
});

export function SecurityPanel() {
  const policy = useAuthStore((state) => state.policy);
  const mode = useAuthStore((state) => state.mode);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const now = useAuthStore((state) => state.now);
  const authenticated = useAuthStore((state) => state.authenticated);
  const serviceStatus = useAuthStore((state) => state.serviceStatus);

  const remaining = authenticated && expiresAt ? formatRemainingTime(expiresAt - now) : '未登录';

  return (
    <section className="security-panel-section panel-section">
      <div className="section-title">
        <LockKeyhole size={16} />
        <span>登录安全</span>
      </div>
      <div className="security-grid">
        <SecurityRow
          icon={<KeyRound size={15} aria-hidden="true" />}
          label="长度"
          value={`${policy.passwordMinLength}-${policy.passwordMaxLength}`}
        />
        <SecurityRow
          icon={<TimerReset size={15} aria-hidden="true" />}
          label={mode === 'long' ? '长会话' : '短会话'}
          value={remaining}
        />
        <SecurityRow
          icon={<RotateCw size={15} aria-hidden="true" />}
          label="刷新"
          value={`${policy.policyRefreshSeconds}s`}
        />
        <SecurityRow
          icon={<ShieldCheck size={15} aria-hidden="true" />}
          label="Cookie"
          value={policy.secureCookie && policy.httpOnlyCookie ? '强制' : '检查'}
        />
        <SecurityRow
          icon={<ShieldCheck size={15} aria-hidden="true" />}
          label="服务"
          value={serviceStatus === 'ready' ? '已连接' : '不可用'}
        />
      </div>
    </section>
  );
}
