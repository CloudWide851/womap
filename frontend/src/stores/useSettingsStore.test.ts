import { describe, expect, it } from 'vitest';

import { useMapStore } from './useMapStore';
import { useSettingsStore } from './useSettingsStore';

describe('map settings stores', () => {
  it('keeps provider and panel state separated from workspace state', () => {
    const settings = useSettingsStore.getState();
    const map = useMapStore.getState();

    expect(settings.basemaps.some((provider) => provider.id === 'amap-vector')).toBe(true);
    expect(settings.panels.layers).toBe(true);
    expect(map.selectedBasemapId).toBe('amap-vector');
  });

  it('toggles panel visibility', () => {
    const before = useSettingsStore.getState().panels.performance;

    useSettingsStore.getState().togglePanel('performance');

    expect(useSettingsStore.getState().panels.performance).toBe(!before);
    useSettingsStore.getState().togglePanel('performance');
  });
});
