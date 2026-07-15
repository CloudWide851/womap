import { Button, Empty, Tag, Tooltip } from 'antd';
import { BoxSelect, Crosshair, Database, PanelRightOpen, Ruler, ScanSearch } from 'lucide-react';
import { memo } from 'react';
import type { ReactNode } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';
import { RasterInspector } from '../rasters/RasterInspector';

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
  const selectedFeatureId = useWorkspaceStore((state) => state.selectedFeatureId);
  const featurePreviews = useWorkspaceStore((state) => state.featurePreviews);
  const openLayerInspector = useWorkspaceStore((state) => state.openLayerInspector);
  const openFeatureInspector = useWorkspaceStore((state) => state.openFeatureInspector);
  const selectedLayer = layers.find((layer) => layer.id === selectedLayerId);
  const selectedFeature = featurePreviews.find((feature) => feature.id === selectedFeatureId);
  const workspaceMode = useWorkspaceStore((state) => state.workspaceMode);
  const analysisTarget = useSpatialAnalysisStore((state) => state.target);
  const setAnalysisDrawerOpen = useSpatialAnalysisStore((state) => state.setDrawerOpen);
  const analysisTargetLabel = analysisTarget
    ? String(
        analysisTarget.properties.name ??
          analysisTarget.properties['名称'] ??
          analysisTarget.properties['编号'] ??
          `图斑 ${analysisTarget.id}`,
      )
    : null;

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
              <strong>{selectedLayer.kind === 'raster' ? '托管栅格' : selectedLayer.geometryType}</strong>
              <span>
                {selectedLayer.kind === 'raster'
                  ? `${selectedLayer.raster?.band_count ?? 0} 波段 · COG`
                  : `${selectedLayer.featureCount} 个要素`}
              </span>
            </div>
            <Tag className="soft-status-tag" color={selectedLayer.visible ? 'geekblue' : 'default'}>
              {selectedLayer.visible ? '显示' : '隐藏'}
            </Tag>
          </div>
          {selectedFeature && selectedLayer.kind !== 'raster' && (
            <div className="context-feature-focus">
              <span className="feature-nav-code">{selectedFeature.displayCode}</span>
              <div>
                <strong>{selectedFeature.title}</strong>
                <span>{selectedFeature.area === '-' ? selectedFeature.geometryType : selectedFeature.area}</span>
              </div>
              <IconTooltipButton
                size="small"
                className="context-action-button"
                label={`查看 ${selectedFeature.title} 属性`}
                icon={<Crosshair size={15} />}
                onClick={() => openFeatureInspector(selectedFeature.layerId, selectedFeature.id)}
              />
            </div>
          )}
          {workspaceMode === 'analysis' && analysisTarget && (
            <div className="context-analysis-target">
              <div>
                <strong>{analysisTargetLabel}</strong>
                <span>真实图斑 · ID {analysisTarget.id}</span>
              </div>
              <Button
                type="primary"
                size="small"
                icon={<ScanSearch size={14} />}
                onClick={() => setAnalysisDrawerOpen(true)}
              >
                空间分析
              </Button>
            </div>
          )}
          <div className="context-metric-grid">
            <SummaryMetric
              icon={<Database size={16} aria-hidden="true" />}
              label="数据策略"
              value={selectedLayer.performance.recommendedMode}
            />
            <SummaryMetric
              icon={<BoxSelect size={16} aria-hidden="true" />}
              label="索引状态"
              value={selectedLayer.kind === 'raster' ? 'Overview' : selectedLayer.performance.indexed ? 'GiST' : '未索引'}
            />
            <SummaryMetric
              icon={<Ruler size={16} aria-hidden="true" />}
              label="透明度"
              value={`${Math.round(selectedLayer.opacity * 100)}%`}
            />
            <SummaryMetric
              icon={<ScanSearch size={16} aria-hidden="true" />}
              label="查看方式"
              value={selectedLayer.kind === 'raster' ? 'Range' : '点击'}
            />
          </div>
          {selectedLayer.kind === 'raster' && <RasterInspector layer={selectedLayer} />}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择图层" />
      )}
    </section>
  );
}
