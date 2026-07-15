import { Descriptions } from 'antd';
import { BoxSelect, Layers3, TableProperties, X } from 'lucide-react';
import { memo, useEffect, useRef } from 'react';

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
  const dialogRef = useRef<HTMLElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!target) return;
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusableSelector =
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    window.requestAnimationFrame(() => {
      const first = dialog?.querySelector<HTMLElement>(focusableSelector);
      (first ?? dialog)?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeInspector();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
    };
  }, [closeInspector, target]);

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
        ref={dialogRef}
        className="attribute-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="attribute-inspector-title"
        tabIndex={-1}
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
          <>
            <Descriptions
              className="attribute-description"
              column={1}
              size="small"
              bordered
              items={[
                { key: 'geometry', label: '几何类型', children: layer?.geometryType ?? '-' },
                { key: 'count', label: '要素数量', children: layer?.featureCount ?? 0 },
                { key: 'fields', label: '字段数量', children: layer?.fields.length ?? 0 },
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
            {layer && (
              <section className="attribute-section">
                <div className="section-title">
                  <TableProperties size={16} />
                  <span>字段结构</span>
                </div>
                <div className="attribute-row-list">
                  {layer.fields.map((field) => (
                    <PropertyRow
                      key={field.name}
                      name={field.alias}
                      value={`${field.name} · ${field.type} · ${field.nullable ? '可空' : '必填'} · ${String(field.example)}`}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </aside>
    </>
  );
}
