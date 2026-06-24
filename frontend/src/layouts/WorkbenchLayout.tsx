import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { BasemapPanel } from '../features/basemaps/BasemapPanel';
import { JobPanel } from '../features/jobs/JobPanel';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { PerformancePanel } from '../features/performance/PerformancePanel';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';
import { PanelSettings } from '../features/settings/PanelSettings';
import { useSettingsStore } from '../stores/useSettingsStore';

export function WorkbenchLayout() {
  const panels = useSettingsStore((state) => state.panels);

  return (
    <div className="workbench">
      <TopToolbar />
      <div className="workbench-body">
        <aside className="panel layer-panel">
          {panels.layers && <LayerPanel />}
          {panels.basemaps && <BasemapPanel />}
          {panels.jobs && <JobPanel />}
        </aside>
        <MapCanvas />
        <aside className="panel properties-panel">
          {panels.properties && <PropertiesPanel />}
          {panels.performance && <PerformancePanel />}
          <PanelSettings />
        </aside>
      </div>
      <StatusBar />
    </div>
  );
}
