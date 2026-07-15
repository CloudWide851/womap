import { Tooltip } from 'antd';
import {
  AlertCircle,
  CheckCircle2,
  Crosshair,
  Info,
  Layers3,
  MousePointer2,
  Ruler,
  Save,
  ScanLine,
  Server,
  ZoomIn,
} from 'lucide-react';
import type { ReactNode } from 'react';

import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import { useMapStore } from '../stores/useMapStore';
import { useWorkspaceContextStore } from '../stores/useWorkspaceContextStore';
import { useAuthStore } from '../stores/useAuthStore';

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
  const serviceStatus = useAuthStore((state) => state.serviceStatus);
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const layers = useWorkspaceStore((state) => state.layers);
  const notice = useWorkspaceStore((state) => state.notice);
  const coordinate = useMapStore((state) => state.coordinate);
  const zoom = useMapStore((state) => state.zoom);
  const scale = useMapStore((state) => state.scale);
  const crs = useMapStore((state) => state.crs);
  const dirty = useWorkspaceContextStore((state) => state.dirty);
  const saving = useWorkspaceContextStore((state) => state.saving);
  const saveError = useWorkspaceContextStore((state) => state.saveError);
  const selectedLayer = layers.find((layer) => layer.id === selectedLayerId);
  const serviceLabel = {
    checking: '检查中',
    ready: '已连接',
    unavailable: '不可用',
  }[serviceStatus];
  const saveStatus = saveError
    ? { label: '保存失败', tone: 'error', icon: <AlertCircle size={13} aria-hidden="true" /> }
    : saving
      ? { label: '保存中', tone: 'saving', icon: <Save size={13} aria-hidden="true" /> }
      : dirty
        ? { label: '有未保存更改', tone: 'dirty', icon: <Save size={13} aria-hidden="true" /> }
        : { label: '已保存', tone: 'saved', icon: <CheckCircle2 size={13} aria-hidden="true" /> };
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
        {selectedLayer?.name ?? '无'}
      </StatusItem>
      <StatusItem label="后端服务" icon={<Server size={13} aria-hidden="true" />}>
        {serviceLabel}
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
      <Tooltip title={saveError ?? '工作空间保存状态'}>
        <span
          className={`save-state is-${saveStatus.tone}`}
          aria-label={`保存状态 ${saveStatus.label}`}
        >
          {saveStatus.icon}
          <span>{saveStatus.label}</span>
        </span>
      </Tooltip>
    </footer>
  );
}
