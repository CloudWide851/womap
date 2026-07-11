import { useEffect } from 'react';

import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { FieldPanel } from '../features/fields/FieldPanel';
import { JobPanel } from '../features/jobs/JobPanel';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { FeatureNavigator } from '../features/map/FeatureNavigator';
import { MapToolsPanel } from '../features/map/MapToolsPanel';
import { PerformancePanel } from '../features/performance/PerformancePanel';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { getLayers } from '../services/api';
import type {
  GeometryType,
  WorkspaceField,
  WorkspaceFieldType,
  WorkspaceLayer,
} from '../types/workspace';

interface WorkbenchLayoutProps {
  onOpenSettings: (section?: 'import-sources') => void;
}

export function WorkbenchLayout({ onOpenSettings }: WorkbenchLayoutProps) {
  const panels = useSettingsStore((state) => state.panels);
  const workspaceMode = useWorkspaceStore((state) => state.workspaceMode);
  const swipeFocused = workspaceMode === 'swipe';
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
        const normalizedLayers: WorkspaceLayer[] = layers.map((layer) => ({
            id: String(layer.id),
            name: layer.name,
            geometryType: normalizeGeometryType(layer.geometry_type),
            featureCount: layer.feature_count,
            visible: layer.visible,
            locked: layer.locked,
            opacity: layer.opacity,
            color: layer.style.color ?? '#4656a8',
            fields: layer.fields.map((field) => normalizeField(field)),
            performance: {
              featureCount: layer.feature_count,
              largeLayer: layer.performance.large_layer,
              indexed: layer.performance.indexed,
              recommendedMode: 'bbox',
              warning: layer.performance.warning,
            },
            source: 'backend' as const,
            bounds: layer.bounds,
          }));
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
              <MapToolsPanel />
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
              {panels.performance && <PerformancePanel />}
            </>
          )}
        </aside>
      </div>
      <StatusBar />
    </div>
  );
}

function normalizeGeometryType(value: string): GeometryType {
  if (value.includes('Point')) return 'Point';
  if (value.includes('Line')) return 'LineString';
  if (value.includes('Polygon')) return 'Polygon';
  return 'Mixed';
}

function normalizeField(field: { name: string; type?: string }): WorkspaceField {
  const rawType = field.type?.toLowerCase() ?? 'string';
  const type: WorkspaceFieldType = rawType.includes('int') || rawType.includes('float')
    ? 'number'
    : rawType.includes('bool')
      ? 'boolean'
      : rawType.includes('date') || rawType.includes('time')
        ? 'date'
        : 'string';
  return {
    name: field.name,
    alias: field.name,
    type,
    nullable: true,
    example: '',
    description: '导入字段',
  };
}
