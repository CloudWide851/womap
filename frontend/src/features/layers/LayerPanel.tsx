import { Button, Slider, Switch, Tag } from 'antd';
import { Eye, EyeOff, Lock, Unlock } from 'lucide-react';

import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

export function LayerPanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const selectLayer = useWorkspaceStore((state) => state.selectLayer);
  const toggleLayer = useWorkspaceStore((state) => state.toggleLayer);
  const setLayerOpacity = useWorkspaceStore((state) => state.setLayerOpacity);

  return (
    <aside className="panel layer-panel">
      <div className="panel-heading">
        <div>
          <p>图层</p>
          <h2>工作空间</h2>
        </div>
        <Button size="small">新增</Button>
      </div>

      <div className="layer-list">
        {layers.map((layer) => (
          <button
            type="button"
            key={layer.id}
            className={`layer-item ${selectedLayerId === layer.id ? 'is-selected' : ''}`}
            onClick={() => selectLayer(layer.id)}
          >
            <span className="layer-swatch" style={{ background: layer.color }} />
            <span className="layer-main">
              <strong>{layer.name}</strong>
              <span>
                {layer.geometryType} · {layer.featureCount} 个要素
              </span>
            </span>
            <span className="layer-controls" onClick={(event) => event.stopPropagation()}>
              <Switch
                size="small"
                checked={layer.visible}
                checkedChildren={<Eye size={12} />}
                unCheckedChildren={<EyeOff size={12} />}
                onChange={() => toggleLayer(layer.id)}
              />
              <Tag
                className="lock-tag"
                icon={layer.locked ? <Lock size={12} /> : <Unlock size={12} />}
              >
                {layer.locked ? '锁定' : '可编'}
              </Tag>
            </span>
            <span className="opacity-row" onClick={(event) => event.stopPropagation()}>
              <span>透明度</span>
              <Slider
                min={0.1}
                max={1}
                step={0.01}
                value={layer.opacity}
                onChange={(value) => setLayerOpacity(layer.id, value)}
              />
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
