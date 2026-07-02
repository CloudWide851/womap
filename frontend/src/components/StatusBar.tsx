import { Tooltip } from 'antd';
import {
  CheckCircle2,
  Crosshair,
  Info,
  Layers3,
  MousePointer2,
  Ruler,
  ScanLine,
  ZoomIn,
} from 'lucide-react';
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
  const notice = useWorkspaceStore((state) => state.notice);
  const coordinate = useMapStore((state) => state.coordinate);
  const zoom = useMapStore((state) => state.zoom);
  const scale = useMapStore((state) => state.scale);
  const crs = useMapStore((state) => state.crs);
  const toolLabel = {
    select: '选择',
    pan: '平移',
    move: '移动',
    rotate: '旋转',
    clip: '裁切',
    split: '分割',
    merge: '合并',
  }[activeTool] ?? activeTool;

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
        {toolLabel}
      </StatusItem>
      <StatusItem label="选中图层" icon={<Layers3 size={13} aria-hidden="true" />}>
        {selectedLayerId ?? '无'}
      </StatusItem>
      <Tooltip title={notice?.detail ?? '最近操作'}>
        <span
          className={`status-item status-notice is-${notice?.tone ?? 'idle'}`}
          role="status"
          aria-live="polite"
          aria-label={`最近操作 ${notice?.title ?? '就绪'}`}
        >
          <Info size={13} aria-hidden="true" />
          <span>{notice?.title ?? '就绪'}</span>
        </span>
      </Tooltip>
      <Tooltip title="保存状态">
        <span className="save-state" aria-label="保存状态 已保存">
          <CheckCircle2 size={13} aria-hidden="true" />
          <span>已保存</span>
        </span>
      </Tooltip>
    </footer>
  );
}
