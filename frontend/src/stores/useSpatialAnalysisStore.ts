import { create } from 'zustand';

import {
  cancelSpatialAnalysis,
  createSpatialAnalysis,
  downloadSpatialAnalysis,
  exportSpatialAnalysis,
  getJob,
  getLayerFeatureDetail,
  getSpatialAnalysis,
  getSpatialAnalysisHits,
} from '../services/api';
import type { ImportJob } from '../types/imports';
import type {
  AnalysisScope,
  AnalysisUnit,
  RealMapFeatureDetail,
  SpatialAnalysisHit,
  SpatialAnalysisResult,
} from '../types/spatialAnalysis';
import { useJobsStore } from './useJobsStore';
import { useMapStore } from './useMapStore';
import { useSettingsStore } from './useSettingsStore';
import { useWorkspaceContextStore } from './useWorkspaceContextStore';
import { useWorkspaceStore } from './useWorkspaceStore';

interface SpatialAnalysisState {
  target: RealMapFeatureDetail | null;
  drawerOpen: boolean;
  distance: number;
  unit: AnalysisUnit;
  scope: AnalysisScope;
  job: ImportJob | null;
  result: SpatialAnalysisResult | null;
  hits: SpatialAnalysisHit[];
  nextCursor: string | null;
  hasMore: boolean;
  busy: boolean;
  error: string | null;
  enter: () => void;
  exit: () => void;
  selectFeature: (layerId: number, featureId: number) => Promise<void>;
  setDrawerOpen: (open: boolean) => void;
  setDistance: (distance: number) => void;
  setUnit: (unit: AnalysisUnit) => void;
  setScope: (scope: AnalysisScope) => void;
  run: () => Promise<void>;
  cancel: () => Promise<void>;
  loadMore: () => Promise<void>;
  openHistory: (jobId: string) => Promise<void>;
  exportResult: () => Promise<{ blob: Blob; filename: string }>;
  reset: () => void;
}

const initialState = {
  target: null,
  drawerOpen: false,
  distance: 100,
  unit: 'm' as AnalysisUnit,
  scope: 'all' as AnalysisScope,
  job: null,
  result: null,
  hits: [] as SpatialAnalysisHit[],
  nextCursor: null,
  hasMore: false,
  busy: false,
  error: null,
};

async function pollAnalysis(jobId: string) {
  try {
    const result = await getSpatialAnalysis(jobId);
    useJobsStore.getState().upsert(result.job);
    useSpatialAnalysisStore.setState({ job: result.job, result, error: null });
    if (result.job.status === 'done') {
      const page = await getSpatialAnalysisHits(jobId);
      useSpatialAnalysisStore.setState({
        hits: page.items,
        nextCursor: page.next_cursor,
        hasMore: page.has_more,
        busy: false,
      });
      return;
    }
    if (['failed', 'interrupted'].includes(result.job.status)) {
      useSpatialAnalysisStore.setState({ busy: false, error: result.job.message });
      return;
    }
    window.setTimeout(() => void pollAnalysis(jobId), 1000);
  } catch (error) {
    useSpatialAnalysisStore.setState({
      busy: false,
      error: error instanceof Error ? error.message : '空间分析状态加载失败。',
    });
  }
}

export const useSpatialAnalysisStore = create<SpatialAnalysisState>((set, get) => ({
  ...initialState,
  enter: () => {
    useMapStore.getState().setSwipeEnabled(false);
    useSettingsStore.getState().restoreSidePanelsAfterSwipe();
    useWorkspaceStore.getState().setWorkspaceMode('analysis');
    set({ ...initialState });
  },
  exit: () => {
    useWorkspaceStore.getState().setWorkspaceMode('browse');
    set({ ...initialState });
  },
  selectFeature: async (layerId, featureId) => {
    const workspace = useWorkspaceContextStore.getState().current;
    if (!workspace) throw new Error('当前没有活动工作空间。');
    set({ busy: true, error: null });
    try {
      const target = await getLayerFeatureDetail(layerId, featureId, workspace.id);
      useWorkspaceStore.getState().selectLayer(String(layerId));
      set({ target, busy: false, result: null, hits: [], nextCursor: null, hasMore: false });
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : '图斑详情加载失败。' });
      throw error;
    }
  },
  setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
  setDistance: (distance) => set({ distance }),
  setUnit: (unit) => set({ unit }),
  setScope: (scope) => set({ scope }),
  run: async () => {
    const workspace = useWorkspaceContextStore.getState().current;
    const { target, distance, unit, scope } = get();
    if (!workspace || !target) throw new Error('请先在地图中选择分析目标图斑。');
    set({ busy: true, drawerOpen: true, error: null, result: null, hits: [] });
    try {
      const job = await createSpatialAnalysis({
        workspace_id: workspace.id,
        target_layer_id: target.layer_id,
        target_feature_id: target.id,
        distance,
        unit,
        scope,
      });
      useJobsStore.getState().upsert(job);
      set({ job });
      window.setTimeout(() => void pollAnalysis(job.id), 250);
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : '空间分析提交失败。' });
      throw error;
    }
  },
  cancel: async () => {
    const job = get().job;
    if (!job) return;
    const canceled = await cancelSpatialAnalysis(job.id);
    useJobsStore.getState().upsert(canceled);
    set({ job: canceled, busy: false });
  },
  loadMore: async () => {
    const { job, nextCursor, hasMore, hits } = get();
    if (!job || !hasMore) return;
    set({ busy: true });
    try {
      const page = await getSpatialAnalysisHits(job.id, nextCursor);
      set({
        hits: [...hits, ...page.items],
        nextCursor: page.next_cursor,
        hasMore: page.has_more,
        busy: false,
      });
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : '命中结果加载失败。' });
    }
  },
  openHistory: async (jobId) => {
    set({ busy: true, drawerOpen: true, error: null });
    try {
      const result = await getSpatialAnalysis(jobId);
      const page = result.job.status === 'done' ? await getSpatialAnalysisHits(jobId) : null;
      set({
        job: result.job,
        result,
        hits: page?.items ?? [],
        nextCursor: page?.next_cursor ?? null,
        hasMore: page?.has_more ?? false,
        busy: false,
      });
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : '分析历史加载失败。' });
    }
  },
  exportResult: async () => {
    const job = get().job;
    if (!job || job.status !== 'done') throw new Error('空间分析完成后才能导出。');
    const exportJob = await exportSpatialAnalysis(job.id);
    useJobsStore.getState().upsert(exportJob);
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const status = await getJob(exportJob.id);
      useJobsStore.getState().upsert(status);
      if (status.status === 'done') return downloadSpatialAnalysis(status.id);
      if (['failed', 'interrupted'].includes(status.status)) {
        throw new Error(status.message ?? '分析结果导出失败。');
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error('分析结果导出等待超时。');
  },
  reset: () => set({ ...initialState }),
}));
