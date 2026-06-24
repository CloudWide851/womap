import { Radio, Tag } from 'antd';
import { MapPinned } from 'lucide-react';

import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';

export function BasemapPanel() {
  const basemaps = useSettingsStore((state) => state.basemaps);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const setSelectedBasemap = useMapStore((state) => state.setSelectedBasemap);

  return (
    <section className="panel-section">
      <div className="section-title">
        <MapPinned size={16} />
        <span>底图</span>
      </div>
      <Radio.Group
        className="basemap-list"
        value={selectedBasemapId}
        onChange={(event) => setSelectedBasemap(event.target.value)}
      >
        {basemaps.map((provider) => (
          <Radio.Button key={provider.id} value={provider.id} disabled={!provider.enabled}>
            <span>{provider.name}</span>
            {!provider.enabled && <Tag>未启用</Tag>}
          </Radio.Button>
        ))}
      </Radio.Group>
    </section>
  );
}
