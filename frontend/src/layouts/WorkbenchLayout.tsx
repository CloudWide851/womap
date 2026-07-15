import { Activity, Layers3, PanelRight, PanelRightClose } from 'lucide-react';
import { lazy, Suspense, useEffect, useState } from 'react';

import { IconTooltipButton } from '../components/IconTooltipButton';
import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { FieldPanel } from '../features/fields/FieldPanel';
import { JobPanel } from '../features/jobs/JobPanel';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { FeatureNavigator } from '../features/map/FeatureNavigator';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';
import { useMapStore } from '../stores/useMapStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { useWorkspaceContextStore } from '../stores/useWorkspaceContextStore';

const SpatialAnalysisDrawer = lazy(() =>
  import('../features/spatial-analysis/SpatialAnalysisDrawer').then((module) => ({
    default: module.SpatialAnalysisDrawer,
  })),
);

interface WorkbenchLayoutProps {
  onOpenSettings: (section?: 'import-sources') => void;
}

export function WorkbenchLayout({ onOpenSettings }: WorkbenchLayoutProps) {
  const panels = useSettingsStore((state) => state.panels);
  const swipeFocused = useMapStore((state) => state.imagerySwipe.enabled);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const viewCenter = useMapStore((state) => state.viewCenter);
  const zoom = useMapStore((state) => state.zoom);
  const layers = useWorkspaceStore((state) => state.layers);
  const currentWorkspace = useWorkspaceContextStore((state) => state.current);
  const initializeWorkspaces = useWorkspaceContextStore((state) => state.initialize);
  const refreshCatalog = useWorkspaceContextStore((state) => state.refreshCatalog);
  const switchWorkspace = useWorkspaceContextStore((state) => state.switchWorkspace);
  const syncRuntimeLayer = useWorkspaceContextStore((state) => state.syncRuntimeLayer);
  const markDirty = useWorkspaceContextStore((state) => state.markDirty);
  const [activeDock, setActiveDock] = useState<'layers' | 'jobs'>('layers');
  const [dockOpen, setDockOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);

  useEffect(() => {
    const query = window.matchMedia('(max-width: 820px)');
    const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) setInspectorOpen(false);
    };
    handleChange(query);
    query.addEventListener('change', handleChange);
    return () => query.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    void initializeWorkspaces();
  }, [initializeWorkspaces]);

  useEffect(() => {
    const handleLayersChanged = () => {
      const current = useWorkspaceContextStore.getState().current;
      if (current?.is_default && !useWorkspaceContextStore.getState().dirty) {
        void switchWorkspace(current.id);
      } else {
        void refreshCatalog();
      }
    };
    window.addEventListener('womap:layers-changed', handleLayersChanged);
    return () => {
      window.removeEventListener('womap:layers-changed', handleLayersChanged);
    };
  }, [refreshCatalog, switchWorkspace]);

  useEffect(() => {
    for (const layer of layers.filter((item) => item.source === 'backend')) {
      syncRuntimeLayer(layer.id, layer.visible, layer.opacity);
    }
  }, [layers, syncRuntimeLayer]);

  useEffect(() => {
    if (!currentWorkspace) return;
    const changed =
      currentWorkspace.default_basemap !== selectedBasemapId ||
      currentWorkspace.view.zoom !== zoom ||
      currentWorkspace.view.center[0] !== viewCenter[0] ||
      currentWorkspace.view.center[1] !== viewCenter[1];
    if (changed) markDirty();
  }, [currentWorkspace, markDirty, selectedBasemapId, viewCenter, zoom]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!useWorkspaceContextStore.getState().dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  return (
    <div className="workbench">
      <TopToolbar onOpenSettings={onOpenSettings} />
      <div
        className={`workbench-body ${swipeFocused ? 'is-swipe-focused' : ''} ${dockOpen ? '' : 'is-dock-collapsed'} ${inspectorOpen ? '' : 'is-inspector-collapsed'}`}
      >
        <nav className="activity-rail" aria-label="工作台面板">
          <IconTooltipButton
            className={activeDock === 'layers' && dockOpen ? 'is-active' : ''}
            label="图层与图斑"
            placement="right"
            icon={<Layers3 size={18} />}
            onClick={() => {
              setActiveDock('layers');
              setDockOpen((open) => activeDock !== 'layers' || !open);
              if (window.matchMedia('(max-width: 820px)').matches) setInspectorOpen(false);
            }}
            aria-pressed={activeDock === 'layers' && dockOpen}
          />
          <IconTooltipButton
            className={activeDock === 'jobs' && dockOpen ? 'is-active' : ''}
            label="后台任务"
            placement="right"
            icon={<Activity size={18} />}
            onClick={() => {
              setActiveDock('jobs');
              setDockOpen((open) => activeDock !== 'jobs' || !open);
              if (window.matchMedia('(max-width: 820px)').matches) setInspectorOpen(false);
            }}
            aria-pressed={activeDock === 'jobs' && dockOpen}
          />
          <span className="activity-rail-spacer" />
          <IconTooltipButton
            className={inspectorOpen ? 'is-active' : ''}
            label={inspectorOpen ? '收起检查器' : '打开检查器'}
            placement="right"
            icon={inspectorOpen ? <PanelRightClose size={18} /> : <PanelRight size={18} />}
            onClick={() => {
              setInspectorOpen((open) => !open);
              if (window.matchMedia('(max-width: 820px)').matches) setDockOpen(false);
            }}
            aria-pressed={inspectorOpen}
          />
        </nav>
        <aside className="panel layer-panel resource-dock" aria-hidden={swipeFocused || !dockOpen}>
          {!swipeFocused && dockOpen && (
            <>
              <header className="dock-header">
                <span>{activeDock === 'layers' ? '资源' : '任务'}</span>
                <small>{activeDock === 'layers' ? '图层与定位序列' : '处理队列与导出'}</small>
              </header>
              {activeDock === 'layers' && panels.layers && <LayerPanel />}
              {activeDock === 'layers' && panels.layers && <FeatureNavigator />}
              {activeDock === 'jobs' && panels.jobs && <JobPanel />}
            </>
          )}
        </aside>
        <MapCanvas />
        <aside className="panel properties-panel context-inspector" aria-hidden={swipeFocused || !inspectorOpen}>
          {!swipeFocused && inspectorOpen && (
            <>
              <header className="dock-header">
                <span>检查器</span>
                <small>上下文、样式与数据</small>
              </header>
              {panels.properties && <PropertiesPanel />}
              {panels.fields && <FieldPanel />}
            </>
          )}
        </aside>
      </div>
      <StatusBar />
      <Suspense fallback={null}>
        <SpatialAnalysisDrawer />
      </Suspense>
    </div>
  );
}
