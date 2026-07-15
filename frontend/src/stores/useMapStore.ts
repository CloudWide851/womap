import { create } from 'zustand';

import { convertCoordinate as convertCoordinateValue } from '../features/map/coordinateTransforms';
import type { CoordinateCrs, MapRuntimeState } from '../types/workspace';

interface MapState extends MapRuntimeState {
  setSelectedBasemap: (basemapId: string) => void;
  setViewState: (
    state: Partial<Pick<MapRuntimeState, 'coordinate' | 'viewCenter' | 'zoom' | 'scale'>>,
  ) => void;
  setCoordinateInput: (axis: 'x' | 'y', value: string) => void;
  setCoordinateCrs: (field: 'source' | 'target', crs: CoordinateCrs) => void;
  convertCoordinate: () => void;
  setSwipeEnabled: (enabled: boolean) => void;
  setSwipeBasemap: (field: 'beforeBasemapId' | 'afterBasemapId', basemapId: string) => void;
  setSwipePosition: (position: number) => void;
  reset: () => void;
}

function createInitialState(): MapRuntimeState {
  return {
    coordinate: [113.2644, 23.1291],
    viewCenter: [12608500, 2644100],
    zoom: 10,
    scale: '1:5000',
    crs: 'EPSG:3857',
    selectedBasemapId: 'amap-vector',
    coordinateConversion: {
      input: {
        x: '113.264400',
        y: '23.129100',
        source: 'EPSG:4326',
        target: 'EPSG:3857',
      },
      result: null,
      error: null,
    },
    imagerySwipe: {
      enabled: false,
      beforeBasemapId: 'amap-vector',
      afterBasemapId: 'tencent-vector',
      position: 50,
    },
  };
}

export const useMapStore = create<MapState>((set) => ({
  ...createInitialState(),
  setSelectedBasemap: (basemapId) => set({ selectedBasemapId: basemapId }),
  setViewState: (state) => set(state),
  setCoordinateInput: (axis, value) =>
    set((state) => ({
      coordinateConversion: {
        ...state.coordinateConversion,
        input: {
          ...state.coordinateConversion.input,
          [axis]: value,
        },
        error: null,
      },
    })),
  setCoordinateCrs: (field, crs) =>
    set((state) => ({
      coordinateConversion: {
        ...state.coordinateConversion,
        input: {
          ...state.coordinateConversion.input,
          [field]: crs,
        },
        error: null,
      },
    })),
  convertCoordinate: () =>
    set((state) => {
      try {
        return {
          coordinateConversion: {
            ...state.coordinateConversion,
            result: convertCoordinateValue(state.coordinateConversion.input),
            error: null,
          },
        };
      } catch (error) {
        return {
          coordinateConversion: {
            ...state.coordinateConversion,
            result: null,
            error: error instanceof Error ? error.message : '坐标转换失败。',
          },
        };
      }
    }),
  setSwipeEnabled: (enabled) =>
    set((state) => ({
      imagerySwipe: {
        ...state.imagerySwipe,
        enabled,
      },
    })),
  setSwipeBasemap: (field, basemapId) =>
    set((state) => ({
      imagerySwipe: {
        ...state.imagerySwipe,
        [field]: basemapId,
      },
    })),
  setSwipePosition: (position) =>
    set((state) => ({
      imagerySwipe: {
        ...state.imagerySwipe,
        position: Math.min(100, Math.max(0, Math.round(position))),
      },
    })),
  reset: () => set(createInitialState()),
}));
