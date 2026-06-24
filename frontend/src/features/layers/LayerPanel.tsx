import { Slider, Tag, Tooltip } from 'antd';
import { Eye, EyeOff, Lock, Plus, SlidersHorizontal, Unlock } from 'lucide-react';
import { memo } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { WorkspaceLayer } from '../../types/workspace';

interface LayerItemProps {
  layer: WorkspaceLayer;
  selected: boolean;
  onSelect: (layerId: string) => void;
  onToggle: (layerId: string) => void;
  onOpacityChange: (layerId: string, opacity: number) => void;
}

const LayerItem = memo(function LayerItem({
  layer,
  selected,
  onSelect,
  onToggle,
  onOpacityChange,
}: LayerItemProps) {
  return (
    <div className={`layer-item ${selected ? 'is-selected' : ''}`}>
      <button
        type="button"
        className="layer-summary-button"
        onClick={() => onSelect(layer.id)}
        aria-pressed={selected}
      >
        <span className="layer-swatch" style={{ background: layer.color }} />
        <span className="layer-main">
          <strong>{layer.name}</strong>
          <span>
            {layer.geometryType} · {layer.featureCount} 个要素
          </span>
        </span>
      </button>
      <span className="layer-controls">
        <IconTooltipButton
          className="layer-action-button"
          size="small"
          type={layer.visible ? 'primary' : 'default'}
          label={layer.visible ? `隐藏 ${layer.name}` : `显示 ${layer.name}`}
          icon={layer.visible ? <Eye size={14} /> : <EyeOff size={14} />}
          onClick={() => onToggle(layer.id)}
          aria-pressed={layer.visible}
        />
        <Tooltip title={layer.locked ? '图层已锁定' : '图层可编辑'}>
          <Tag
            role="img"
            className="lock-tag icon-only-tag"
            icon={layer.locked ? <Lock size={12} /> : <Unlock size={12} />}
            aria-label={layer.locked ? '图层已锁定' : '图层可编辑'}
          />
        </Tooltip>
      </span>
      <span className="opacity-row">
        <Tooltip title="透明度">
          <SlidersHorizontal size={14} aria-hidden="true" />
        </Tooltip>
        <Slider
          min={0.1}
          max={1}
          step={0.01}
          value={layer.opacity}
          onChange={(value) => onOpacityChange(layer.id, value)}
          ariaLabelForHandle={`${layer.name} 透明度`}
        />
      </span>
    </div>
  );
});

export function LayerPanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const selectLayer = useWorkspaceStore((state) => state.selectLayer);
  const toggleLayer = useWorkspaceStore((state) => state.toggleLayer);
  const setLayerOpacity = useWorkspaceStore((state) => state.setLayerOpacity);

  return (
    <section className="panel-section layer-panel-section">
      <div className="panel-heading">
        <div>
          <p>图层</p>
          <h2>工作空间</h2>
        </div>
        <IconTooltipButton size="small" label="新增图层" icon={<Plus size={15} />} />
      </div>

      <div className="layer-list">
        {layers.map((layer) => (
          <LayerItem
            key={layer.id}
            layer={layer}
            selected={selectedLayerId === layer.id}
            onSelect={selectLayer}
            onToggle={toggleLayer}
            onOpacityChange={setLayerOpacity}
          />
        ))}
      </div>
    </section>
  );
}
