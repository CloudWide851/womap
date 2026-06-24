import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { useMapStore } from '../stores/useMapStore';

export function StatusBar() {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const coordinate = useMapStore((state) => state.coordinate);
  const zoom = useMapStore((state) => state.zoom);
  const scale = useMapStore((state) => state.scale);
  const crs = useMapStore((state) => state.crs);

  return (
    <footer className="status-bar">
      <span>坐标 {coordinate[0].toFixed(4)}, {coordinate[1].toFixed(4)}</span>
      <span>缩放 {zoom}</span>
      <span>比例尺 {scale}</span>
      <span>坐标系 {crs}</span>
      <span>当前工具 {activeTool}</span>
      <span>选中图层 {selectedLayerId ?? '无'}</span>
      <span className="save-state">已保存</span>
    </footer>
  );
}
