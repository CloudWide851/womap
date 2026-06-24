import { Tooltip } from 'antd';
import { CheckCircle2, Crosshair, Layers3, MousePointer2, Ruler, ScanLine, ZoomIn } from 'lucide-react';
import type { ReactNode } from 'react';

import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { useMapStore } from '../stores/useMapStore';

interface StatusItemProps {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}

function StatusItem({ label, icon, children }: StatusItemProps) {
  return (
    <Tooltip title={label}>
      <span className="status-item" aria-label={`${label} ${children}`}>
        {icon}
        <span>{children}</span>
      </span>
    </Tooltip>
  );
}

export function StatusBar() {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const coordinate = useMapStore((state) => state.coordinate);
  const zoom = useMapStore((state) => state.zoom);
  const scale = useMapStore((state) => state.scale);
  const crs = useMapStore((state) => state.crs);

  return (
    <footer className="status-bar">
      <StatusItem label="坐标" icon={<Crosshair size={13} aria-hidden="true" />}>
        {coordinate[0].toFixed(4)}, {coordinate[1].toFixed(4)}
      </StatusItem>
      <StatusItem label="缩放" icon={<ZoomIn size={13} aria-hidden="true" />}>
        {zoom}
      </StatusItem>
      <StatusItem label="比例尺" icon={<Ruler size={13} aria-hidden="true" />}>
        {scale}
      </StatusItem>
      <StatusItem label="坐标系" icon={<ScanLine size={13} aria-hidden="true" />}>
        {crs}
      </StatusItem>
      <StatusItem label="当前工具" icon={<MousePointer2 size={13} aria-hidden="true" />}>
        {activeTool}
      </StatusItem>
      <StatusItem label="选中图层" icon={<Layers3 size={13} aria-hidden="true" />}>
        {selectedLayerId ?? '无'}
      </StatusItem>
      <Tooltip title="保存状态">
        <span className="save-state" aria-label="保存状态 已保存">
          <CheckCircle2 size={13} aria-hidden="true" />
          <span>已保存</span>
        </span>
      </Tooltip>
    </footer>
  );
}
