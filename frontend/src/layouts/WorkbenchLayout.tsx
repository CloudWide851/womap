import { StatusBar } from '../components/StatusBar';
import { TopToolbar } from '../components/TopToolbar';
import { LayerPanel } from '../features/layers/LayerPanel';
import { MapCanvas } from '../features/map/MapCanvas';
import { PropertiesPanel } from '../features/properties/PropertiesPanel';

export function WorkbenchLayout() {
  return (
    <div className="workbench">
      <TopToolbar />
      <div className="workbench-body">
        <LayerPanel />
        <MapCanvas />
        <PropertiesPanel />
      </div>
      <StatusBar />
    </div>
  );
}
