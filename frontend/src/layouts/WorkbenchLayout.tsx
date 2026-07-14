import { useEffect } from 'react';

import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { FieldPanel } from '../features/fields/FieldPanel';
import { JobPanel } from '../features/jobs/JobPanel';
import { normalizeBackendLayer } from '../features/layers/backendLayer';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { FeatureNavigator } from '../features/map/FeatureNavigator';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';
import { useMapStore } from '../stores/useMapStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { getLayers } from '../services/api';

interface WorkbenchLayoutProps {
  onOpenSettings: (section?: 'import-sources') => void;
}

export function WorkbenchLayout({ onOpenSettings }: WorkbenchLayoutProps) {
  const panels = useSettingsStore((state) => state.panels);
  const swipeFocused = useMapStore((state) => state.imagerySwipe.enabled);
  const setBackendLayers = useWorkspaceStore((state) => state.setBackendLayers);

  useEffect(() => {
    let active = true;
    const loadLayers = (event?: Event) => {
      const existingIds = new Set(
        useWorkspaceStore.getState().layers
          .filter((layer) => layer.source === 'backend')
          .map((layer) => layer.id),
      );
      void getLayers()
      .then((layers) => {
        if (!active) return;
        const normalizedLayers = layers.map(normalizeBackendLayer);
        setBackendLayers(normalizedLayers);
        if (event) {
          const addedLayers = normalizedLayers.filter((layer) => !existingIds.has(layer.id));
          const newestLayer = addedLayers[addedLayers.length - 1];
          if (newestLayer?.bounds) {
            window.dispatchEvent(
              new CustomEvent('womap:focus-backend-layer', {
                detail: { name: newestLayer.name, bounds: newestLayer.bounds },
              }),
            );
          }
        }
      })
      .catch(() => undefined);
    };
    loadLayers();
    window.addEventListener('womap:layers-changed', loadLayers);
    return () => {
      active = false;
      window.removeEventListener('womap:layers-changed', loadLayers);
    };
  }, [setBackendLayers]);

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
    </div>
  );
}
