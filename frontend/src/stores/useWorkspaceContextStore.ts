import { create } from 'zustand';

import { normalizeBackendLayer } from '../features/layers/backendLayer';
import {
  createWorkspace,
  deleteWorkspace,
  getWorkspace,
  getWorkspaceCatalog,
  getWorkspaces,
  updateWorkspace,
} from '../services/api';
import type { BackendLayerSummary } from '../types/imports';
import type {
  WorkspaceCatalog,
  WorkspaceDetail,
  WorkspaceFeatureSelection,
  WorkspaceLayerState,
  WorkspaceSummary,
  WorkspaceWrite,
} from '../types/workspaces';
import { useMapStore } from './useMapStore';
import { useWorkspaceStore } from './useWorkspaceStore';

const ACTIVE_WORKSPACE_KEY = 'womap.active-workspace-id';

interface WorkspaceContextState {
  workspaces: WorkspaceSummary[];
  current: WorkspaceDetail | null;
  catalog: WorkspaceCatalog | null;
  drawerOpen: boolean;
  dirty: boolean;
  loading: boolean;
  error: string | null;
  initialize: () => Promise<void>;
  refreshCatalog: () => Promise<void>;
  switchWorkspace: (workspaceId: number) => Promise<void>;
  saveCurrent: () => Promise<WorkspaceDetail>;
  createBlank: (name: string) => Promise<WorkspaceDetail>;
  saveAs: (name: string) => Promise<WorkspaceDetail>;
  deleteCurrent: () => Promise<void>;
  setDrawerOpen: (open: boolean) => void;
  setMetadata: (metadata: { name?: string; description?: string }) => void;
  setLayerIncluded: (layer: BackendLayerSummary, included: boolean) => void;
  setLayerSelection: (layerId: number, selection: WorkspaceFeatureSelection) => void;
  syncRuntimeLayer: (layerId: string, visible: boolean, opacity: number) => void;
  discardChanges: () => Promise<void>;
  markDirty: () => void;
  reset: () => void;
}

function emptySelection(): WorkspaceFeatureSelection {
  return { mode: 'all', feature_ids: [], source_feature_ids: [] };
}

function applyWorkspace(detail: WorkspaceDetail) {
  useWorkspaceStore.getState().setBackendLayers(
    detail.layers.map((state) =>
      normalizeBackendLayer({
        ...state.layer,
        visible: state.config.visible,
        opacity: state.config.opacity,
      }),
    ),
  );
  useMapStore.getState().setSelectedBasemap(detail.default_basemap);
  useMapStore.getState().setViewState({
    viewCenter: detail.view.center,
    zoom: detail.view.zoom,
  });
  window.dispatchEvent(
    new CustomEvent('womap:apply-workspace-view', {
      detail: { center: detail.view.center, zoom: detail.view.zoom },
    }),
  );
  window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, String(detail.id));
}

function runtimePayload(current: WorkspaceDetail): WorkspaceWrite {
  const runtimeLayers = useWorkspaceStore.getState().layers;
  const runtimeMap = useMapStore.getState();
  return {
    name: current.name,
    description: current.description,
    default_basemap: runtimeMap.selectedBasemapId,
    view: {
      center: runtimeMap.viewCenter,
      zoom: runtimeMap.zoom,
    },
    layers: current.layers.map((state, order) => {
      const runtime = runtimeLayers.find((layer) => layer.id === String(state.layer.id));
      return {
        ...state.config,
        visible: runtime?.visible ?? state.config.visible,
        opacity: runtime?.opacity ?? state.config.opacity,
        order,
        raster_style: runtime?.kind === 'raster' ? runtime.rasterStyle ?? null : null,
      };
    }),
  };
}

export const useWorkspaceContextStore = create<WorkspaceContextState>((set, get) => ({
  workspaces: [],
  current: null,
  catalog: null,
  drawerOpen: false,
  dirty: false,
  loading: false,
  error: null,
  initialize: async () => {
    set({ loading: true, error: null });
    try {
      const workspaces = await getWorkspaces();
      const storedId = Number(window.localStorage.getItem(ACTIVE_WORKSPACE_KEY));
      const selected =
        workspaces.find((workspace) => workspace.id === storedId) ??
        workspaces.find((workspace) => workspace.is_default) ??
        workspaces[0];
      const current = selected ? await getWorkspace(selected.id) : null;
      if (current) applyWorkspace(current);
      set({ workspaces, current, dirty: false, loading: false });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : '工作空间初始化失败。',
      });
    }
  },
  refreshCatalog: async () => {
    const catalog = await getWorkspaceCatalog();
    set({ catalog });
  },
  switchWorkspace: async (workspaceId) => {
    set({ loading: true, error: null });
    try {
      const current = await getWorkspace(workspaceId);
      applyWorkspace(current);
      set({ current, dirty: false, loading: false });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : '工作空间切换失败。',
      });
      throw error;
    }
  },
  saveCurrent: async () => {
    const current = get().current;
    if (!current) throw new Error('当前没有可保存的工作空间。');
    const saved = await updateWorkspace(current.id, {
      ...runtimePayload(current),
      revision: current.revision,
    });
    applyWorkspace(saved);
    const workspaces = await getWorkspaces();
    set({ current: saved, workspaces, dirty: false });
    return saved;
  },
  createBlank: async (name) => {
    const runtimeMap = useMapStore.getState();
    const saved = await createWorkspace({
      name: name.trim(),
      description: '',
      default_basemap: runtimeMap.selectedBasemapId,
      view: { center: runtimeMap.viewCenter, zoom: runtimeMap.zoom },
      layers: [],
    });
    applyWorkspace(saved);
    const workspaces = await getWorkspaces();
    set({ current: saved, workspaces, dirty: false });
    return saved;
  },
  saveAs: async (name) => {
    const current = get().current;
    if (!current) throw new Error('当前没有可复制的工作空间。');
    const saved = await createWorkspace({ ...runtimePayload(current), name: name.trim() });
    applyWorkspace(saved);
    const workspaces = await getWorkspaces();
    set({ current: saved, workspaces, dirty: false });
    return saved;
  },
  deleteCurrent: async () => {
    const current = get().current;
    if (!current) return;
    await deleteWorkspace(current.id);
    const workspaces = await getWorkspaces();
    const fallback = workspaces.find((workspace) => workspace.is_default) ?? workspaces[0];
    if (!fallback) {
      set({ workspaces, current: null, dirty: false });
      return;
    }
    const detail = await getWorkspace(fallback.id);
    applyWorkspace(detail);
    set({ workspaces, current: detail, dirty: false });
  },
  setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
  setMetadata: (metadata) =>
    set((state) => ({
      current: state.current ? { ...state.current, ...metadata } : null,
      dirty: Boolean(state.current),
    })),
  setLayerIncluded: (layer, included) =>
    set((state) => {
      if (!state.current) return state;
      const existing = state.current.layers.some((item) => item.layer.id === layer.id);
      if (included === existing) return state;
      const layers: WorkspaceLayerState[] = included
        ? [
            ...state.current.layers,
            {
              layer,
              config: {
                layer_id: layer.id,
                dataset_id: layer.provenance?.dataset_id ?? null,
                visible: true,
                opacity: layer.opacity,
                order: state.current.layers.length,
                selection: emptySelection(),
                raster_style: layer.kind === 'raster' ? layer.style.raster ?? null : null,
              },
            },
          ]
        : state.current.layers.filter((item) => item.layer.id !== layer.id);
      return { current: { ...state.current, layers }, dirty: true };
    }),
  setLayerSelection: (layerId, selection) =>
    set((state) => ({
      current: state.current
        ? {
            ...state.current,
            layers: state.current.layers.map((item) =>
              item.layer.id === layerId
                ? { ...item, config: { ...item.config, selection } }
                : item,
            ),
          }
        : null,
      dirty: Boolean(state.current),
    })),
  syncRuntimeLayer: (layerId, visible, opacity) =>
    set((state) => {
      if (!state.current) return state;
      const id = Number(layerId);
      const target = state.current.layers.find((item) => item.layer.id === id);
      if (!target || (target.config.visible === visible && target.config.opacity === opacity)) {
        return state;
      }
      return {
        current: {
          ...state.current,
          layers: state.current.layers.map((item) =>
            item.layer.id === id
              ? { ...item, config: { ...item.config, visible, opacity } }
              : item,
          ),
        },
        dirty: true,
      };
    }),
  discardChanges: async () => {
    const current = get().current;
    if (current) await get().switchWorkspace(current.id);
  },
  markDirty: () => set({ dirty: true }),
  reset: () =>
    set({
      workspaces: [],
      current: null,
      catalog: null,
      drawerOpen: false,
      dirty: false,
      loading: false,
      error: null,
    }),
}));
