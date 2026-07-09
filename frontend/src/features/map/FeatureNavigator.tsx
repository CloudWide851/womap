import { Empty, Tooltip } from 'antd';
import { Crosshair, MapPin, PanelRightOpen } from 'lucide-react';
import { memo, useMemo } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { FeatureAttributePreview } from '../../types/workspace';

interface FeatureNavigationItemProps {
  feature: FeatureAttributePreview;
  selected: boolean;
  onFocus: (featureId: string) => void;
  onInspect: (layerId: string, featureId: string) => void;
}

const FeatureNavigationItem = memo(function FeatureNavigationItem({
  feature,
  selected,
  onFocus,
  onInspect,
}: FeatureNavigationItemProps) {
  return (
    <div className={`feature-nav-item ${selected ? 'is-selected' : ''}`}>
      <button
        type="button"
        className="feature-nav-focus"
        aria-label={`定位 ${feature.title}`}
        aria-pressed={selected}
        onClick={() => onFocus(feature.id)}
      >
        <span className="feature-nav-code">{feature.displayCode}</span>
        <span className="feature-nav-main">
          <strong>{feature.title}</strong>
          <span>{feature.area === '-' ? feature.geometryType : feature.area}</span>
        </span>
        <Crosshair size={15} aria-hidden="true" />
      </button>
      <IconTooltipButton
        className="feature-nav-inspect"
        size="small"
        label={`查看 ${feature.title} 属性`}
        icon={<PanelRightOpen size={14} />}
        onClick={() => onInspect(feature.layerId, feature.id)}
      />
    </div>
  );
});

export function FeatureNavigator() {
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const selectedFeatureId = useWorkspaceStore((state) => state.selectedFeatureId);
  const featurePreviews = useWorkspaceStore((state) => state.featurePreviews);
  const focusFeature = useWorkspaceStore((state) => state.focusFeature);
  const openFeatureInspector = useWorkspaceStore((state) => state.openFeatureInspector);
  const visibleFeatures = useMemo(
    () => featurePreviews.filter((feature) => feature.layerId === selectedLayerId),
    [featurePreviews, selectedLayerId],
  );

  return (
    <section className="panel-section feature-nav-section">
      <div className="panel-heading compact-heading">
        <div>
          <p>图斑</p>
          <h2>定位序列</h2>
        </div>
        <Tooltip title="点击图斑即可缩放到对应范围">
          <span className="panel-heading-icon" aria-label="图斑定位说明" role="img">
            <MapPin size={16} aria-hidden="true" />
          </span>
        </Tooltip>
      </div>

      {visibleFeatures.length > 0 ? (
        <div className="feature-nav-list">
          {visibleFeatures.map((feature) => (
            <FeatureNavigationItem
              key={feature.id}
              feature={feature}
              selected={selectedFeatureId === feature.id}
              onFocus={focusFeature}
              onInspect={openFeatureInspector}
            />
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无示例图斑" />
      )}
    </section>
  );
}
