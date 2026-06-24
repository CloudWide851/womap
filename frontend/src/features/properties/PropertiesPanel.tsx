import { Descriptions, Empty, Segmented } from 'antd';

import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

export function PropertiesPanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const selectedLayer = layers.find((layer) => layer.id === selectedLayerId);

  return (
    <aside className="panel properties-panel">
      <div className="panel-heading">
        <div>
          <p>属性</p>
          <h2>{selectedLayer ? selectedLayer.name : '未选择'}</h2>
        </div>
      </div>

      <Segmented block options={['图层', '图斑', '编辑']} defaultValue="图层" />

      {selectedLayer ? (
        <Descriptions
          className="property-table"
          column={1}
          size="small"
          bordered
          items={[
            { key: 'type', label: '几何类型', children: selectedLayer.geometryType },
            { key: 'count', label: '要素数量', children: selectedLayer.featureCount },
            { key: 'visible', label: '显示状态', children: selectedLayer.visible ? '显示' : '隐藏' },
            { key: 'locked', label: '编辑状态', children: selectedLayer.locked ? '锁定' : '可编辑' },
            { key: 'opacity', label: '透明度', children: `${Math.round(selectedLayer.opacity * 100)}%` },
          ]}
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择图层" />
      )}
    </aside>
  );
}
