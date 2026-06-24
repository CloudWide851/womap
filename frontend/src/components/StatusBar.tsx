import { useWorkspaceStore } from '../stores/useWorkspaceStore';

export function StatusBar() {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);

  return (
    <footer className="status-bar">
      <span>坐标 113.2644, 23.1291</span>
      <span>缩放 10</span>
      <span>比例尺 1:5000</span>
      <span>坐标系 EPSG:3857</span>
      <span>当前工具 {activeTool}</span>
      <span>选中图层 {selectedLayerId ?? '无'}</span>
      <span className="save-state">已保存</span>
    </footer>
  );
}
