import { create } from 'zustand';

import type { MapRuntimeState } from '../types/workspace';

interface MapState extends MapRuntimeState {
  setSelectedBasemap: (basemapId: string) => void;
  setViewState: (state: Partial<Pick<MapRuntimeState, 'coordinate' | 'zoom' | 'scale'>>) => void;
}

export const useMapStore = create<MapState>((set) => ({
  coordinate: [113.2644, 23.1291],
  zoom: 10,
  scale: '1:5000',
  crs: 'EPSG:3857',
  selectedBasemapId: 'amap-vector',
  setSelectedBasemap: (basemapId) => set({ selectedBasemapId: basemapId }),
  setViewState: (state) => set(state),
}));
