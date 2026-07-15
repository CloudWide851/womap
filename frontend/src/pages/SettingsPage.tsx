import { ArrowLeft, DatabaseZap, Gauge, ShieldCheck } from 'lucide-react';
import { useEffect } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from '../components/IconTooltipButton';
import { BasemapPanel } from '../features/basemaps/BasemapPanel';
import { SecurityPanel } from '../features/security/SecurityPanel';
import { PanelSettings } from '../features/settings/PanelSettings';
import { ImportSourceSettings } from '../features/settings/ImportSourceSettings';

interface SettingsPageProps {
  onBack: () => void;
  focusSection?: 'import-sources' | null;
}

export function SettingsPage({ onBack, focusSection }: SettingsPageProps) {
  useEffect(() => {
    if (focusSection !== 'import-sources') return;
    window.requestAnimationFrame(() =>
      document.getElementById('import-sources-settings')?.scrollIntoView({ behavior: 'smooth' }),
    );
  }, [focusSection]);

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
          <p className="settings-intro-copy">数据源、界面、底图与安全策略集中管理，修改后立即回到地图验证。</p>
        </section>

        <div className="settings-grid">
          <section className="settings-card settings-card-imports" id="import-sources-settings">
            <ImportSourceSettings />
          </section>
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
              <span>地图 · bbox 矢量加载 + COG Range</span>
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
