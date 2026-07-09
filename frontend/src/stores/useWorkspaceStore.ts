import { create } from 'zustand';

import type {
  AttributeInspectorTarget,
  FeatureFocusRequest,
  FeatureAttributePreview,
  WorkspaceCommand,
  WorkspaceNotice,
  WorkspaceLayer,
  WorkspaceMode,
} from '../types/workspace';

interface WorkspaceState {
  activeTool: string;
  workspaceMode: WorkspaceMode;
  selectedLayerId: string | null;
  selectedFeatureId: string | null;
  featureFocusRequest: FeatureFocusRequest | null;
  inspectorTarget: AttributeInspectorTarget | null;
  notice: WorkspaceNotice | null;
  layers: WorkspaceLayer[];
  featurePreviews: FeatureAttributePreview[];
  setActiveTool: (tool: string) => void;
  setWorkspaceMode: (mode: WorkspaceMode) => void;
  notifyCommand: (command: WorkspaceCommand) => void;
  showNotice: (notice: Omit<WorkspaceNotice, 'id'>) => void;
  selectLayer: (layerId: string) => void;
  focusFeature: (featureId: string) => void;
  openLayerInspector: (layerId: string) => void;
  openFeatureInspector: (layerId: string, featureId: string) => void;
  closeInspector: () => void;
  toggleLayer: (layerId: string) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  reset: () => void;
}

const commandNotices: Record<WorkspaceCommand, Omit<WorkspaceNotice, 'id'>> = {
  'import-data': {
    tone: 'info',
    title: '导入入口已标记',
    detail: '真实导入任务 API 属于阶段 2；当前可使用示例图层检查工作台流程。',
  },
  'save-project': {
    tone: 'info',
    title: '保存入口已标记',
    detail: '项目文件保存属于真实数据接入后的阶段 2 能力；当前状态保留在示例工作台内。',
  },
  'export-results': {
    tone: 'info',
    title: '导出入口已标记',
    detail: '数据与截图导出属于阶段 6；当前不会静默导出空结果。',
  },
  undo: {
    tone: 'warning',
    title: '暂无可撤销操作',
    detail: '撤销历史会在轻量编辑阶段接入；当前没有编辑操作记录。',
  },
  redo: {
    tone: 'warning',
    title: '暂无可重做操作',
    detail: '重做历史会在轻量编辑阶段接入；当前没有可恢复的编辑操作。',
  },
  'add-layer': {
    tone: 'info',
    title: '新增图层入口已标记',
    detail: '新增图层会随导入任务 API 接入开放；当前示例图层仅用于阶段 1 工作台检查。',
  },
};

const toolLabels: Record<string, string> = {
  select: '选择',
  pan: '平移',
  move: '移动',
  rotate: '旋转',
  clip: '裁切',
  split: '分割',
  merge: '合并',
};

const workspaceModeNotices: Record<WorkspaceMode, Omit<WorkspaceNotice, 'id'>> = {
  browse: {
    tone: 'info',
    title: '已进入浏览查看模式',
    detail: '地图保持普通查看状态，可切换图层、底图和查看属性。',
  },
  edit: {
    tone: 'info',
    title: '已进入图斑编辑模式',
    detail: '当前先开放编辑工具态反馈；真实图斑编辑会在轻量编辑阶段接入。',
  },
  swipe: {
    tone: 'info',
    title: '已进入两期影像卷帘模式',
    detail: '左右侧栏已默认收缩，地图聚焦显示前后期底图对比。',
  },
  inspect: {
    tone: 'info',
    title: '已进入属性查看模式',
    detail: '通过图层或图斑入口打开属性检查器，右侧仍保持轻量摘要。',
  },
};

let noticeSequence = 0;

function createNotice(notice: Omit<WorkspaceNotice, 'id'>): WorkspaceNotice {
  noticeSequence += 1;
  return { id: noticeSequence, ...notice };
}

function createToolNotice(tool: string): WorkspaceNotice {
  const label = toolLabels[tool] ?? tool;
  return createNotice({
    tone: 'info',
    title: `已切换到${label}工具`,
    detail: '阶段 1 先完成工具态反馈；真实地图编辑会在轻量编辑阶段接入。',
  });
}

function createWorkspaceModeNotice(mode: WorkspaceMode): WorkspaceNotice {
  return createNotice(workspaceModeNotices[mode]);
}

function createFeatureFocusNotice(feature: FeatureAttributePreview): WorkspaceNotice {
  return createNotice({
    tone: 'info',
    title: `已定位 ${feature.displayCode}`,
    detail: `${feature.title} 已在地图中居中，属性入口保持可用。`,
  });
}

function createInitialLayers(): WorkspaceLayer[] {
  return [
    {
      id: 'project-boundary',
      name: '项目边界',
      geometryType: 'Polygon',
      featureCount: 12,
      visible: true,
      locked: false,
      opacity: 0.78,
      color: '#4f46d8',
      fields: [
        {
          name: 'project_code',
          alias: '项目编号',
          type: 'string',
          nullable: false,
          example: 'WM-2026-102',
          description: '项目内部编号，用于交付和系统录入。',
        },
        {
          name: 'land_type',
          alias: '用地类型',
          type: 'string',
          nullable: false,
          example: '建设用地',
          description: '项目边界对应的用地分类。',
        },
        {
          name: 'area_ha',
          alias: '面积(公顷)',
          type: 'number',
          nullable: false,
          example: 28.64,
          description: '按当前示例几何计算的面积。',
        },
      ],
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
      color: '#c45b35',
      fields: [
        {
          name: 'point_code',
          alias: '点位编号',
          type: 'string',
          nullable: false,
          example: 'P-018',
          description: '巡查点位的现场编号。',
        },
        {
          name: 'status',
          alias: '巡查状态',
          type: 'string',
          nullable: false,
          example: '待复核',
          description: '点位当前处理状态。',
        },
        {
          name: 'synced',
          alias: '已同步',
          type: 'boolean',
          nullable: false,
          example: false,
          description: '点位是否已进入后续系统。',
        },
      ],
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
      color: '#5c6bcf',
      fields: [
        {
          name: 'overlay_name',
          alias: '叠图名称',
          type: 'string',
          nullable: false,
          example: '控规范围',
          description: '规划叠图或混合图层名称。',
        },
        {
          name: 'source_year',
          alias: '来源年份',
          type: 'number',
          nullable: true,
          example: 2026,
          description: '规划资料来源年份。',
        },
        {
          name: 'locked',
          alias: '锁定',
          type: 'boolean',
          nullable: false,
          example: true,
          description: '是否禁止编辑，仅允许查看。',
        },
      ],
      performance: {
        featureCount: 68000,
        largeLayer: true,
        indexed: true,
        recommendedMode: 'tile',
        warning: '超大图层默认按视口加载，避免一次性拉取全部几何。',
      },
    },
  ];
}

function createFeaturePreviews(): FeatureAttributePreview[] {
  return [
    {
      id: 'feature-boundary-102',
      layerId: 'project-boundary',
      displayCode: 'B-102',
      title: '边界图斑 102',
      geometryType: 'Polygon',
      area: '28.64 ha',
      perimeter: '3.42 km',
      bounds: '113.21,23.08,113.33,23.18',
      mapBounds: [113.21, 23.08, 113.33, 23.18],
      properties: {
        项目编号: 'WM-2026-102',
        用地类型: '建设用地',
        数据来源: '示例工作空间',
        已索引: true,
        更新批次: 3,
      },
    },
    {
      id: 'feature-boundary-108',
      layerId: 'project-boundary',
      displayCode: 'B-108',
      title: '边界图斑 108',
      geometryType: 'Polygon',
      area: '11.92 ha',
      perimeter: '1.86 km',
      bounds: '113.30,23.16,113.38,23.22',
      mapBounds: [113.3, 23.16, 113.38, 23.22],
      properties: {
        项目编号: 'WM-2026-108',
        用地类型: '农用地',
        数据来源: '示例工作空间',
        已索引: true,
        更新批次: 4,
      },
    },
    {
      id: 'feature-point-018',
      layerId: 'survey-points',
      displayCode: 'P-018',
      title: '巡查点位 018',
      geometryType: 'Point',
      area: '-',
      perimeter: '-',
      bounds: '113.27,23.13,113.27,23.13',
      mapBounds: [113.27, 23.13, 113.27, 23.13],
      properties: {
        点位编号: 'P-018',
        巡查状态: '待复核',
        负责人: '现场组',
        已同步: false,
      },
    },
    {
      id: 'feature-point-031',
      layerId: 'survey-points',
      displayCode: 'P-031',
      title: '巡查点位 031',
      geometryType: 'Point',
      area: '-',
      perimeter: '-',
      bounds: '113.34,23.2,113.34,23.2',
      mapBounds: [113.34, 23.2, 113.34, 23.2],
      properties: {
        点位编号: 'P-031',
        巡查状态: '已复核',
        负责人: '资料组',
        已同步: true,
      },
    },
  ];
}

function createInitialState() {
  return {
    activeTool: 'select',
    workspaceMode: 'browse' as WorkspaceMode,
    selectedLayerId: 'project-boundary',
    selectedFeatureId: 'feature-boundary-102',
    featureFocusRequest: null,
    inspectorTarget: null,
    notice: null,
    layers: createInitialLayers(),
    featurePreviews: createFeaturePreviews(),
  };
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  ...createInitialState(),
  setActiveTool: (tool) => set({ activeTool: tool, notice: createToolNotice(tool) }),
  setWorkspaceMode: (mode) =>
    set({
      workspaceMode: mode,
      notice: createWorkspaceModeNotice(mode),
    }),
  notifyCommand: (command) => set({ notice: createNotice(commandNotices[command]) }),
  showNotice: (notice) => set({ notice: createNotice(notice) }),
  selectLayer: (layerId) =>
    set((state) => {
      const firstFeature = state.featurePreviews.find((feature) => feature.layerId === layerId);
      return {
        selectedLayerId: layerId,
        selectedFeatureId: firstFeature?.id ?? null,
      };
    }),
  focusFeature: (featureId) =>
    set((state) => {
      const feature = state.featurePreviews.find((item) => item.id === featureId);
      if (!feature) {
        return {
          notice: createNotice({
            tone: 'warning',
            title: '图斑不可定位',
            detail: '当前示例工作空间中没有找到该图斑。',
          }),
        };
      }
      return {
        selectedLayerId: feature.layerId,
        selectedFeatureId: feature.id,
        featureFocusRequest: {
          featureId: feature.id,
          sequence: (state.featureFocusRequest?.sequence ?? 0) + 1,
        },
        notice: createFeatureFocusNotice(feature),
      };
    }),
  openLayerInspector: (layerId) =>
    set({
      selectedLayerId: layerId,
      inspectorTarget: { kind: 'layer', layerId },
    }),
  openFeatureInspector: (layerId, featureId) =>
    set((state) => ({
      selectedLayerId: layerId,
      selectedFeatureId: featureId,
      featureFocusRequest: {
        featureId,
        sequence: (state.featureFocusRequest?.sequence ?? 0) + 1,
      },
      inspectorTarget: { kind: 'feature', layerId, featureId },
    })),
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
  reset: () => set(createInitialState()),
}));
