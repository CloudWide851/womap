import { Tooltip } from 'antd';
import { DatabaseZap, Gauge, Layers3, ShieldCheck, TriangleAlert } from 'lucide-react';
import { memo } from 'react';
import type { ReactNode } from 'react';

import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { LayerPerformanceState } from '../../types/workspace';

interface PerformanceMetricProps {
  icon: ReactNode;
  label: string;
  value: string | number;
}

const PerformanceMetric = memo(function PerformanceMetric({
  icon,
  label,
  value,
}: PerformanceMetricProps) {
  return (
    <Tooltip title={label}>
      <div className="performance-metric" aria-label={`${label} ${value}`}>
        {icon}
        <span>{value}</span>
      </div>
    </Tooltip>
  );
});

function getStrategyLabel(strategy?: LayerPerformanceState['recommendedMode']) {
  if (strategy === 'tile') {
    return '瓦片';
  }
  if (strategy === 'table') {
    return '分页';
  }
  return 'bbox';
}

export function PerformancePanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const layer = layers.find((item) => item.id === selectedLayerId);

  return (
    <section className="panel-section">
      <div className="section-title">
        <Gauge size={16} />
        <span>性能</span>
      </div>
      <div className="performance-grid">
        <PerformanceMetric
          icon={<Layers3 size={16} aria-hidden="true" />}
          label="当前要素"
          value={layer?.performance.featureCount ?? 0}
        />
        <PerformanceMetric
          icon={<DatabaseZap size={16} aria-hidden="true" />}
          label="加载策略"
          value={getStrategyLabel(layer?.performance.recommendedMode)}
        />
      </div>
      <div
        className={`performance-hint ${layer?.performance.warning ? 'is-warning' : 'is-ok'}`}
        role="status"
      >
        {layer?.performance.warning ? (
          <TriangleAlert size={16} aria-hidden="true" />
        ) : (
          <ShieldCheck size={16} aria-hidden="true" />
        )}
        <span>{layer?.performance.warning ?? '当前图层可按视口安全加载。'}</span>
      </div>
    </section>
  );
}
