import { Slider, Tag, Tooltip } from 'antd';
import { Eye, EyeOff, Image, Lock, PanelRightOpen, Plus, SlidersHorizontal, Unlock } from 'lucide-react';
import { memo } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { WorkspaceLayer } from '../../types/workspace';

interface LayerItemProps {
  layer: WorkspaceLayer;
  selected: boolean;
  onSelect: (layerId: string) => void;
  onInspect: (layerId: string) => void;
  onToggle: (layerId: string) => void;
  onOpacityChange: (layerId: string, opacity: number) => void;
}

const LayerItem = memo(function LayerItem({
  layer,
  selected,
  onSelect,
  onInspect,
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
        <span className={`layer-swatch ${layer.kind === 'raster' ? 'is-raster' : ''}`} style={{ background: layer.color }}>
          {layer.kind === 'raster' && <Image size={11} aria-hidden="true" />}
        </span>
        <span className="layer-main">
          <strong>{layer.name}</strong>
          <span>
            {layer.kind === 'raster'
              ? `${layer.raster?.width.toLocaleString('zh-CN') ?? 0} × ${layer.raster?.height.toLocaleString('zh-CN') ?? 0} · ${layer.raster?.band_count ?? 0} 波段`
              : `${layer.geometryType} · ${layer.featureCount} 个要素`}
          </span>
        </span>
        <Tag className={`layer-source-tag is-${layer.source ?? 'demo'}`}>
          {layer.source === 'backend' ? '数据' : '示例'}
        </Tag>
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
        <IconTooltipButton
          className="layer-action-button"
          size="small"
          label={`查看 ${layer.name} 属性`}
          icon={<PanelRightOpen size={14} />}
          onClick={() => onInspect(layer.id)}
        />
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
  const openLayerInspector = useWorkspaceStore((state) => state.openLayerInspector);
  const toggleLayer = useWorkspaceStore((state) => state.toggleLayer);
  const setLayerOpacity = useWorkspaceStore((state) => state.setLayerOpacity);
  const notifyCommand = useWorkspaceStore((state) => state.notifyCommand);

  return (
    <section className="panel-section layer-panel-section">
      <div className="panel-heading">
        <div>
          <p>图层</p>
          <h2>工作空间</h2>
        </div>
        <IconTooltipButton
          size="small"
          label="新增图层"
          icon={<Plus size={15} />}
          onClick={() => notifyCommand('add-layer')}
        />
      </div>

      <div className="layer-list">
        {layers.map((layer) => (
          <LayerItem
            key={layer.id}
            layer={layer}
            selected={selectedLayerId === layer.id}
            onSelect={selectLayer}
            onInspect={openLayerInspector}
            onToggle={toggleLayer}
            onOpacityChange={setLayerOpacity}
          />
        ))}
      </div>
    </section>
  );
}
