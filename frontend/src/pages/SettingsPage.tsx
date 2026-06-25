import { ArrowLeft, DatabaseZap, Gauge, KeyRound, MapPinned, PanelsTopLeft, RotateCw, ShieldCheck } from 'lucide-react';
import { memo } from 'react';
import type { ReactNode } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from '../components/IconTooltipButton';
import { BasemapPanel } from '../features/basemaps/BasemapPanel';
import { SecurityPanel } from '../features/security/SecurityPanel';
import { PanelSettings } from '../features/settings/PanelSettings';
import { useAuthStore } from '../stores/useAuthStore';
import { useSettingsStore } from '../stores/useSettingsStore';

interface SettingsPageProps {
  onBack: () => void;
}

interface SettingsMetricProps {
  icon: ReactNode;
  label: string;
  value: string;
}

const SettingsMetric = memo(function SettingsMetric({ icon, label, value }: SettingsMetricProps) {
  return (
    <div className="settings-metric" aria-label={`${label} ${value}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
});

export function SettingsPage({ onBack }: SettingsPageProps) {
  const basemaps = useSettingsStore((state) => state.basemaps);
  const policy = useAuthStore((state) => state.policy);
  const enabledBasemapCount = basemaps.filter((provider) => provider.enabled).length;
  const keyedProviderCount = basemaps.filter((provider) => provider.apiKeyConfigured).length;

  return (
    <div className="settings-page">
      <header className="settings-header">
        <div className="brand-lockup settings-brand brand-logo-only">
          <img className="brand-logo" src={womapLogo} alt="WOMAP" />
        </div>
        <IconTooltipButton
          className="tool-icon-button"
          label="返回工作台"
          icon={<ArrowLeft size={17} />}
          onClick={onBack}
        />
      </header>

      <main className="settings-content">
        <section className="settings-hero">
          <div>
            <p>设置</p>
            <h1>工作台设置</h1>
          </div>
          <div className="settings-metrics-grid">
            <SettingsMetric
              icon={<PanelsTopLeft size={17} aria-hidden="true" />}
              label="面板"
              value="分离"
            />
            <SettingsMetric
              icon={<MapPinned size={17} aria-hidden="true" />}
              label="底图"
              value={`${enabledBasemapCount}`}
            />
            <SettingsMetric
              icon={<KeyRound size={17} aria-hidden="true" />}
              label="密钥"
              value={`${keyedProviderCount}`}
            />
            <SettingsMetric
              icon={<RotateCw size={17} aria-hidden="true" />}
              label="刷新"
              value={`${policy.policyRefreshSeconds}s`}
            />
          </div>
        </section>

        <div className="settings-grid">
          <section className="settings-card settings-card-panel">
            <PanelSettings />
          </section>
          <section className="settings-card settings-card-basemap">
            <BasemapPanel />
          </section>
          <section className="settings-card settings-card-security">
            <SecurityPanel />
          </section>
          <section className="settings-card">
            <div className="section-title">
              <DatabaseZap size={16} />
              <span>本地配置</span>
            </div>
            <div className="settings-list">
              <span>YAML · 本地优先</span>
              <span>PostGIS · geometry + GiST</span>
              <span>Redis · 任务与 bbox 缓存</span>
              <span>Secret · 只检查布尔状态</span>
            </div>
          </section>
          <section className="settings-card">
            <div className="section-title">
              <Gauge size={16} />
              <span>性能策略</span>
            </div>
            <div className="settings-list">
              <span>Core Web Vitals · LCP / INP / CLS</span>
              <span>动画 · transform / opacity</span>
              <span>React · memo + 窄 selector</span>
              <span>地图 · bbox 后续接 WebGL / 瓦片</span>
            </div>
            <div className="settings-status">
              <ShieldCheck size={16} aria-hidden="true" />
              <span>主工作台不再承载设置表单，减少常驻 DOM。</span>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
