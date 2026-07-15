import { lazy, Suspense, useEffect } from 'react';

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
      <div className={`workbench-body ${swipeFocused ? 'is-swipe-focused' : ''}`}>
        <aside className="panel layer-panel" aria-hidden={swipeFocused}>
          {!swipeFocused && (
            <>
              {panels.layers && <LayerPanel />}
              {panels.layers && <FeatureNavigator />}
              {panels.jobs && <JobPanel />}
            </>
          )}
        </aside>
        <MapCanvas />
        <aside className="panel properties-panel" aria-hidden={swipeFocused}>
          {!swipeFocused && (
            <>
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
