import { Alert, Statistic } from 'antd';
import { Gauge } from 'lucide-react';

import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

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
        <Statistic title="当前要素" value={layer?.performance.featureCount ?? 0} />
        <Statistic title="加载策略" value={layer?.performance.recommendedMode ?? 'bbox'} />
      </div>
      {layer?.performance.warning ? (
        <Alert type="warning" showIcon message={layer.performance.warning} />
      ) : (
        <Alert type="success" showIcon message="当前图层可按视口安全加载。" />
      )}
    </section>
  );
}
