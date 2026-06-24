import { Tag, Tooltip } from 'antd';
import { Globe2, KeyRound, MapPinned, PlugZap } from 'lucide-react';
import { memo } from 'react';

import { useMapStore } from '../../stores/useMapStore';
import { useSettingsStore } from '../../stores/useSettingsStore';
import type { BasemapProvider } from '../../types/workspace';

interface BasemapOptionProps {
  provider: BasemapProvider;
  selected: boolean;
  onSelect: (providerId: string) => void;
}

const BasemapOption = memo(function BasemapOption({
  provider,
  selected,
  onSelect,
}: BasemapOptionProps) {
  const Icon = provider.apiKeyConfigured ? KeyRound : Globe2;
  return (
    <Tooltip title={`${provider.name}${provider.enabled ? '' : '（未启用）'}`}>
      <button
        type="button"
        className={`basemap-option ${selected ? 'is-selected' : ''}`}
        disabled={!provider.enabled}
        aria-pressed={selected}
        onClick={() => onSelect(provider.id)}
      >
        <Icon size={15} aria-hidden="true" />
        <span>{provider.name}</span>
        {!provider.enabled && (
          <Tag className="icon-only-tag" icon={<PlugZap size={12} />} aria-label="未启用" />
        )}
      </button>
    </Tooltip>
  );
});

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
      <div className="basemap-list" role="group" aria-label="底图选择">
        {basemaps.map((provider) => (
          <BasemapOption
            key={provider.id}
            provider={provider}
            selected={selectedBasemapId === provider.id}
            onSelect={setSelectedBasemap}
          />
        ))}
      </div>
    </section>
  );
}
