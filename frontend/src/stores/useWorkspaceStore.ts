import { create } from 'zustand';

import type { WorkspaceLayer } from '../types/workspace';

interface WorkspaceState {
  activeTool: string;
  selectedLayerId: string | null;
  layers: WorkspaceLayer[];
  setActiveTool: (tool: string) => void;
  selectLayer: (layerId: string) => void;
  toggleLayer: (layerId: string) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
}

const initialLayers: WorkspaceLayer[] = [
  {
    id: 'project-boundary',
    name: '项目边界',
    geometryType: 'Polygon',
    featureCount: 12,
    visible: true,
    locked: false,
    opacity: 0.78,
    color: '#256f5d',
  },
  {
    id: 'survey-points',
    name: '巡查点位',
    geometryType: 'Point',
    featureCount: 86,
    visible: true,
    locked: false,
    opacity: 1,
    color: '#c15f2e',
  },
  {
    id: 'planning-overlay',
    name: '规划叠图',
    geometryType: 'Mixed',
    featureCount: 4,
    visible: false,
    locked: true,
    opacity: 0.46,
    color: '#3f62b5',
  },
];

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeTool: 'select',
  selectedLayerId: 'project-boundary',
  layers: initialLayers,
  setActiveTool: (tool) => set({ activeTool: tool }),
  selectLayer: (layerId) => set({ selectedLayerId: layerId }),
  toggleLayer: (layerId) =>
    set((state) => ({
      layers: state.layers.map((layer) =>
        layer.id === layerId ? { ...layer, visible: !layer.visible } : layer,
      ),
    })),
  setLayerOpacity: (layerId, opacity) =>
    set((state) => ({
      layers: state.layers.map((layer) =>
        layer.id === layerId ? { ...layer, opacity } : layer,
      ),
    })),
}));
