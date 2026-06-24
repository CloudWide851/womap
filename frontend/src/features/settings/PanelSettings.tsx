import { Button, Tooltip } from 'antd';
import {
  Activity,
  Gauge,
  Layers3,
  MapPinned,
  PanelRight,
  SlidersHorizontal,
  TableProperties,
} from 'lucide-react';
import { memo } from 'react';
import type { ComponentType } from 'react';

import { useSettingsStore } from '../../stores/useSettingsStore';
import type { PanelLayoutSettings } from '../../types/workspace';

const labels: Record<keyof PanelLayoutSettings, string> = {
  layers: '图层',
  basemaps: '底图',
  jobs: '任务',
  properties: '属性',
  fields: '字段',
  performance: '性能',
};

const icons: Record<keyof PanelLayoutSettings, ComponentType<{ size?: number }>> = {
  layers: Layers3,
  basemaps: MapPinned,
  jobs: Activity,
  properties: PanelRight,
  fields: TableProperties,
  performance: Gauge,
};

interface PanelToggleProps {
  panel: keyof PanelLayoutSettings;
  enabled: boolean;
  onToggle: (panel: keyof PanelLayoutSettings) => void;
}

const PanelToggle = memo(function PanelToggle({ panel, enabled, onToggle }: PanelToggleProps) {
  const Icon = icons[panel];
  const label = `${enabled ? '隐藏' : '显示'}${labels[panel]}面板`;
  return (
    <Tooltip title={label}>
      <Button
        className="panel-toggle-button"
        type={enabled ? 'primary' : 'default'}
        aria-label={label}
        aria-pressed={enabled}
        icon={<Icon size={15} />}
        onClick={() => onToggle(panel)}
      />
    </Tooltip>
  );
});

export function PanelSettings() {
  const panels = useSettingsStore((state) => state.panels);
  const togglePanel = useSettingsStore((state) => state.togglePanel);

  return (
    <section className="panel-section">
      <div className="section-title">
        <SlidersHorizontal size={16} />
        <span>面板</span>
      </div>
      <div className="panel-toggle-list">
        {(Object.keys(panels) as Array<keyof PanelLayoutSettings>).map((panel) => (
          <PanelToggle key={panel} panel={panel} enabled={panels[panel]} onToggle={togglePanel} />
        ))}
      </div>
    </section>
  );
}
