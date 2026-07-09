import { afterEach, describe, expect, it } from 'vitest';

import { useMapStore } from './useMapStore';
import { useSettingsStore } from './useSettingsStore';

describe('map settings stores', () => {
  afterEach(() => {
    useSettingsStore.getState().reset();
    useMapStore.getState().reset();
  });

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

  it('collapses side panels for imagery swipe and restores the previous panel state', () => {
    useSettingsStore.getState().togglePanel('performance');
    const before = useSettingsStore.getState().panels;

    useSettingsStore.getState().collapseSidePanelsForSwipe();

    expect(useSettingsStore.getState().panels.layers).toBe(false);
    expect(useSettingsStore.getState().panels.properties).toBe(false);
    expect(useSettingsStore.getState().swipePanelSnapshot).toEqual(before);

    useSettingsStore.getState().restoreSidePanelsAfterSwipe();

    expect(useSettingsStore.getState().panels).toEqual(before);
    expect(useSettingsStore.getState().swipePanelSnapshot).toBeNull();
  });
});
