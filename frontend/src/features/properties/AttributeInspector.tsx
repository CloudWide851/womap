import { Descriptions } from 'antd';
import { BoxSelect, Layers3, TableProperties, X } from 'lucide-react';
import { memo } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

interface PropertyRowProps {
  name: string;
  value: string | number | boolean;
}

const PropertyRow = memo(function PropertyRow({ name, value }: PropertyRowProps) {
  return (
    <div className="attribute-row">
      <span>{name}</span>
      <strong>{String(value)}</strong>
    </div>
  );
});

export function AttributeInspector() {
  const target = useWorkspaceStore((state) => state.inspectorTarget);
  const closeInspector = useWorkspaceStore((state) => state.closeInspector);
  const layers = useWorkspaceStore((state) => state.layers);
  const featurePreviews = useWorkspaceStore((state) => state.featurePreviews);

  if (!target) {
    return null;
  }

  const layer = layers.find((item) => item.id === target.layerId);
  const feature =
    target.kind === 'feature'
      ? featurePreviews.find((item) => item.id === target.featureId)
      : undefined;
  const title = feature?.title ?? layer?.name ?? '属性';
  const icon =
    target.kind === 'feature' ? (
      <BoxSelect size={18} aria-hidden="true" />
    ) : (
      <Layers3 size={18} aria-hidden="true" />
    );

  return (
    <>
      <button
        type="button"
        className="attribute-inspector-backdrop"
        aria-label="关闭属性浮层"
        onClick={closeInspector}
      />
      <aside
        className="attribute-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="attribute-inspector-title"
      >
        <header className="attribute-inspector-header">
          <span className="attribute-inspector-icon">{icon}</span>
          <div>
            <p>{target.kind === 'feature' ? '图斑属性' : '图层属性'}</p>
            <h2 id="attribute-inspector-title">{title}</h2>
          </div>
          <IconTooltipButton
            className="attribute-close-button"
            label="关闭属性检查器"
            icon={<X size={16} />}
            onClick={closeInspector}
          />
        </header>

        {feature ? (
          <>
            <Descriptions
              className="attribute-description"
              column={1}
              size="small"
              bordered
              items={[
                { key: 'layer', label: '所属图层', children: layer?.name ?? '-' },
                { key: 'geometry', label: '几何类型', children: feature.geometryType },
                { key: 'area', label: '面积', children: feature.area },
                { key: 'perimeter', label: '周长', children: feature.perimeter },
                { key: 'bounds', label: '范围', children: feature.bounds },
              ]}
            />
            <section className="attribute-section">
              <div className="section-title">
                <TableProperties size={16} />
                <span>字段</span>
              </div>
              <div className="attribute-row-list">
                {Object.entries(feature.properties).map(([name, value]) => (
                  <PropertyRow key={name} name={name} value={value} />
                ))}
              </div>
            </section>
          </>
        ) : (
          <Descriptions
            className="attribute-description"
            column={1}
            size="small"
            bordered
            items={[
              { key: 'geometry', label: '几何类型', children: layer?.geometryType ?? '-' },
              { key: 'count', label: '要素数量', children: layer?.featureCount ?? 0 },
              { key: 'visible', label: '显示状态', children: layer?.visible ? '显示' : '隐藏' },
              { key: 'locked', label: '编辑状态', children: layer?.locked ? '锁定' : '可编辑' },
              {
                key: 'opacity',
                label: '透明度',
                children: layer ? `${Math.round(layer.opacity * 100)}%` : '-',
              },
              {
                key: 'strategy',
                label: '加载策略',
                children: layer?.performance.recommendedMode ?? '-',
              },
            ]}
          />
        )}
      </aside>
    </>
  );
}
