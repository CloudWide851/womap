import { Empty, Tag, Tooltip } from 'antd';
import { ListChecks, PanelRightOpen, TableProperties } from 'lucide-react';
import { memo } from 'react';

import { IconTooltipButton } from '../../components/IconTooltipButton';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { WorkspaceField } from '../../types/workspace';

interface FieldRowProps {
  field: WorkspaceField;
}

const FieldRow = memo(function FieldRow({ field }: FieldRowProps) {
  return (
    <article className="field-row" aria-label={`${field.alias} ${field.type}`}>
      <div>
        <strong>{field.alias}</strong>
        <span>{field.name}</span>
      </div>
      <div className="field-row-meta">
        <Tag className="soft-status-tag">{field.type}</Tag>
        <Tag className="soft-status-tag">{field.nullable ? '可空' : '必填'}</Tag>
      </div>
      <p>{field.description}</p>
      <small>示例：{String(field.example)}</small>
    </article>
  );
});

export function FieldPanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const openLayerInspector = useWorkspaceStore((state) => state.openLayerInspector);
  const selectedLayer = layers.find((layer) => layer.id === selectedLayerId);

  return (
    <section className="panel-section field-panel-section">
      <div className="panel-heading">
        <div>
          <p>字段</p>
          <h2>字段概览</h2>
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
        <>
          <div className="field-panel-summary">
            <Tooltip title="字段总数">
              <span>
                <TableProperties size={15} aria-hidden="true" />
                {selectedLayer.fields.length}
              </span>
            </Tooltip>
            <Tooltip title="必填字段">
              <span>
                <ListChecks size={15} aria-hidden="true" />
                {selectedLayer.fields.filter((field) => !field.nullable).length}
              </span>
            </Tooltip>
          </div>
          <div className="field-list" role="list" aria-label={`${selectedLayer.name} 字段列表`}>
            {selectedLayer.fields.map((field) => (
              <div key={field.name} role="listitem">
                <FieldRow field={field} />
              </div>
            ))}
          </div>
        </>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择图层" />
      )}
    </section>
  );
}
