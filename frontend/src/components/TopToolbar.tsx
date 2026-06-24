import { Divider } from 'antd';
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
  SplitSquareHorizontal,
  Undo2,
} from 'lucide-react';
import { memo } from 'react';
import type { ComponentType } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from './IconTooltipButton';
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

  return (
    <header className="top-toolbar">
      <div className="brand-lockup">
        <img className="brand-logo" src={womapLogo} alt="" data-testid="brand-logo" />
        <div>
          <strong>WOMAP</strong>
          <span>图斑工坊</span>
        </div>
      </div>

      <nav className="toolbar-actions" aria-label="主工具栏">
        <IconTooltipButton className="tool-icon-button" label="导入数据" icon={<Import size={17} />} />
        <IconTooltipButton className="tool-icon-button" label="保存项目" icon={<Save size={17} />} />
        <IconTooltipButton className="tool-icon-button" label="导出成果" icon={<Download size={17} />} />
        <Divider type="vertical" />
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
        <Divider type="vertical" />
        <IconTooltipButton className="tool-icon-button" label="撤销" icon={<Undo2 size={17} />} />
        <IconTooltipButton className="tool-icon-button" label="重做" icon={<Redo2 size={17} />} />
        <Divider type="vertical" />
        <IconTooltipButton
          className="tool-icon-button"
          label="打开设置"
          icon={<Settings size={17} />}
          onClick={onOpenSettings}
        />
      </nav>
    </header>
  );
}
