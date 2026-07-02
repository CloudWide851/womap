import {
  Combine,
  Download,
  Hand,
  Import,
  MousePointer2,
  Move,
  Redo2,
  RotateCw,
  Save,
  Scissors,
  Settings,
  ShieldCheck,
  SplitSquareHorizontal,
  Undo2,
  LogOut,
} from 'lucide-react';
import { memo } from 'react';
import type { ComponentType } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from './IconTooltipButton';
import { formatRemainingTime, useAuthStore } from '../stores/useAuthStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';

const tools = [
  { key: 'select', label: '选择', icon: MousePointer2 },
  { key: 'pan', label: '平移', icon: Hand },
  { key: 'move', label: '移动', icon: Move },
  { key: 'rotate', label: '旋转', icon: RotateCw },
  { key: 'clip', label: '裁切', icon: Scissors },
  { key: 'split', label: '分割', icon: SplitSquareHorizontal },
  { key: 'merge', label: '合并', icon: Combine },
];

interface ToolbarToolButtonProps {
  active: boolean;
  icon: ComponentType<{ size?: number }>;
  label: string;
  onClick: () => void;
}

const ToolbarToolButton = memo(function ToolbarToolButton({
  active,
  icon: Icon,
  label,
  onClick,
}: ToolbarToolButtonProps) {
  return (
    <IconTooltipButton
      className="tool-icon-button"
      type={active ? 'primary' : 'default'}
      icon={<Icon size={17} />}
      label={label}
      onClick={onClick}
      aria-pressed={active}
    />
  );
});

interface TopToolbarProps {
  onOpenSettings: () => void;
}

export function TopToolbar({ onOpenSettings }: TopToolbarProps) {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const setActiveTool = useWorkspaceStore((state) => state.setActiveTool);
  const mode = useAuthStore((state) => state.mode);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const now = useAuthStore((state) => state.now);
  const logout = useAuthStore((state) => state.logout);
  const remaining = expiresAt ? formatRemainingTime(expiresAt - now) : '--';

  return (
    <header className="top-toolbar">
      <div className="brand-lockup brand-logo-only">
        <img className="brand-logo" src={womapLogo} alt="WOMAP" data-testid="brand-logo" />
      </div>

      <nav className="toolbar-actions" aria-label="主工具栏">
        <span className="toolbar-cluster toolbar-cluster-file" role="group" aria-label="文件操作">
          <IconTooltipButton className="tool-icon-button" label="导入数据" icon={<Import size={17} />} />
          <IconTooltipButton className="tool-icon-button" label="保存项目" icon={<Save size={17} />} />
          <IconTooltipButton className="tool-icon-button" label="导出成果" icon={<Download size={17} />} />
        </span>

        <span className="toolbar-cluster toolbar-cluster-edit" role="group" aria-label="编辑工具">
          {tools.map((tool) => {
            const Icon = tool.icon;
            return (
              <ToolbarToolButton
                key={tool.key}
                active={activeTool === tool.key}
                icon={Icon}
                label={tool.label}
                onClick={() => setActiveTool(tool.key)}
              />
            );
          })}
        </span>

        <span className="toolbar-cluster toolbar-cluster-history" role="group" aria-label="历史操作">
          <IconTooltipButton className="tool-icon-button" label="撤销" icon={<Undo2 size={17} />} />
          <IconTooltipButton className="tool-icon-button" label="重做" icon={<Redo2 size={17} />} />
        </span>

        <span className="toolbar-spacer" aria-hidden="true" />

        <span className="toolbar-cluster toolbar-cluster-session" role="group" aria-label="工作台状态">
          <IconTooltipButton
            className="tool-icon-button"
            label="打开设置"
            icon={<Settings size={17} />}
            onClick={onOpenSettings}
          />
          <span className="session-chip" aria-label={`当前${mode === 'long' ? '长' : '短'}会话 ${remaining}`}>
            <ShieldCheck size={15} aria-hidden="true" />
            {mode === 'long' ? '长' : '短'} {remaining}
          </span>
          <IconTooltipButton
            className="tool-icon-button"
            label="退出登录"
            icon={<LogOut size={17} />}
            onClick={logout}
          />
        </span>
      </nav>
    </header>
  );
}
