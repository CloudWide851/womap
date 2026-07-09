import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { FieldPanel } from '../features/fields/FieldPanel';
import { JobPanel } from '../features/jobs/JobPanel';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { MapToolsPanel } from '../features/map/MapToolsPanel';
import { PerformancePanel } from '../features/performance/PerformancePanel';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

interface WorkbenchLayoutProps {
  onOpenSettings: () => void;
}

export function WorkbenchLayout({ onOpenSettings }: WorkbenchLayoutProps) {
  const panels = useSettingsStore((state) => state.panels);
  const workspaceMode = useWorkspaceStore((state) => state.workspaceMode);
  const swipeFocused = workspaceMode === 'swipe';

  return (
    <div className="workbench">
      <TopToolbar onOpenSettings={onOpenSettings} />
      <div className={`workbench-body ${swipeFocused ? 'is-swipe-focused' : ''}`}>
        <aside className="panel layer-panel" aria-hidden={swipeFocused}>
          {!swipeFocused && (
            <>
              {panels.layers && <LayerPanel />}
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
