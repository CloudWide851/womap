import { Switch } from 'antd';
import { SlidersHorizontal } from 'lucide-react';

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
          <label key={panel}>
            <span>{labels[panel]}</span>
            <Switch size="small" checked={panels[panel]} onChange={() => togglePanel(panel)} />
          </label>
        ))}
      </div>
    </section>
  );
}
