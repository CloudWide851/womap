import { Empty, Tag, Tooltip } from 'antd';
import { BoxSelect, Database, PanelRightOpen, Ruler, ScanSearch } from 'lucide-react';
import { memo } from 'react';
import type { ReactNode } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

interface SummaryMetricProps {
  icon: ReactNode;
  label: string;
  value: string | number;
}

const SummaryMetric = memo(function SummaryMetric({ icon, label, value }: SummaryMetricProps) {
  return (
    <Tooltip title={label}>
      <div className="context-metric" aria-label={`${label} ${value}`}>
        {icon}
        <span>{value}</span>
      </div>
    </Tooltip>
  );
});

export function PropertiesPanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const openLayerInspector = useWorkspaceStore((state) => state.openLayerInspector);
  const selectedLayer = layers.find((layer) => layer.id === selectedLayerId);

  return (
    <section className="panel-section properties-panel-section">
      <div className="panel-heading">
        <div>
          <p>上下文</p>
          <h2>{selectedLayer ? selectedLayer.name : '未选择'}</h2>
        </div>
        {selectedLayer && (
          <IconTooltipButton
            size="small"
            className="context-action-button"
            label={`查看 ${selectedLayer.name} 属性`}
            icon={<PanelRightOpen size={15} />}
            onClick={() => openLayerInspector(selectedLayer.id)}
          />
        )}
      </div>

      {selectedLayer ? (
        <div className="context-summary">
          <div className="context-summary-main">
            <span className="layer-swatch" style={{ background: selectedLayer.color }} />
            <div>
              <strong>{selectedLayer.geometryType}</strong>
              <span>{selectedLayer.featureCount} 个要素</span>
            </div>
            <Tag className="soft-status-tag" color={selectedLayer.visible ? 'geekblue' : 'default'}>
              {selectedLayer.visible ? '显示' : '隐藏'}
            </Tag>
          </div>
          <div className="context-metric-grid">
            <SummaryMetric
              icon={<Database size={16} aria-hidden="true" />}
              label="数据策略"
              value={selectedLayer.performance.recommendedMode}
            />
            <SummaryMetric
              icon={<BoxSelect size={16} aria-hidden="true" />}
              label="索引状态"
              value={selectedLayer.performance.indexed ? 'GiST' : '未索引'}
            />
            <SummaryMetric
              icon={<Ruler size={16} aria-hidden="true" />}
              label="透明度"
              value={`${Math.round(selectedLayer.opacity * 100)}%`}
            />
            <SummaryMetric
              icon={<ScanSearch size={16} aria-hidden="true" />}
              label="查看方式"
              value="点击"
            />
          </div>
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择图层" />
      )}
    </section>
  );
}
