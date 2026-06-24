import { create } from 'zustand';

import type {
  AttributeInspectorTarget,
  FeatureAttributePreview,
  WorkspaceLayer,
} from '../types/workspace';

interface WorkspaceState {
  activeTool: string;
  selectedLayerId: string | null;
  inspectorTarget: AttributeInspectorTarget | null;
  layers: WorkspaceLayer[];
  featurePreviews: FeatureAttributePreview[];
  setActiveTool: (tool: string) => void;
  selectLayer: (layerId: string) => void;
  openLayerInspector: (layerId: string) => void;
  openFeatureInspector: (layerId: string, featureId: string) => void;
  closeInspector: () => void;
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
    performance: {
      featureCount: 12,
      largeLayer: false,
      indexed: true,
      recommendedMode: 'bbox',
    },
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
    performance: {
      featureCount: 86,
      largeLayer: false,
      indexed: true,
      recommendedMode: 'bbox',
    },
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
    performance: {
      featureCount: 68000,
      largeLayer: true,
      indexed: true,
      recommendedMode: 'tile',
      warning: '超大图层默认按视口加载，避免一次性拉取全部几何。',
    },
  },
];

const featurePreviews: FeatureAttributePreview[] = [
  {
    id: 'feature-boundary-102',
    layerId: 'project-boundary',
    title: '边界图斑 102',
    geometryType: 'Polygon',
    area: '28.64 ha',
    perimeter: '3.42 km',
    bounds: '113.21,23.08,113.33,23.18',
    properties: {
      项目编号: 'WM-2026-102',
      用地类型: '建设用地',
      数据来源: '示例工作空间',
      已索引: true,
      更新批次: 3,
    },
  },
  {
    id: 'feature-point-018',
    layerId: 'survey-points',
    title: '巡查点位 018',
    geometryType: 'Point',
    area: '-',
    perimeter: '-',
    bounds: '113.27,23.13,113.27,23.13',
    properties: {
      点位编号: 'P-018',
      巡查状态: '待复核',
      负责人: '现场组',
      已同步: false,
    },
  },
];

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeTool: 'select',
  selectedLayerId: 'project-boundary',
  inspectorTarget: null,
  layers: initialLayers,
  featurePreviews,
  setActiveTool: (tool) => set({ activeTool: tool }),
  selectLayer: (layerId) => set({ selectedLayerId: layerId }),
  openLayerInspector: (layerId) =>
    set({
      selectedLayerId: layerId,
      inspectorTarget: { kind: 'layer', layerId },
    }),
  openFeatureInspector: (layerId, featureId) =>
    set({
      selectedLayerId: layerId,
      inspectorTarget: { kind: 'feature', layerId, featureId },
    }),
  closeInspector: () => set({ inspectorTarget: null }),
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
