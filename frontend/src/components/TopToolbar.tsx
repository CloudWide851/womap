import { Button, Divider, Tooltip } from 'antd';
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
  SplitSquareHorizontal,
  Undo2,
} from 'lucide-react';

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

export function TopToolbar() {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const setActiveTool = useWorkspaceStore((state) => state.setActiveTool);

  return (
    <header className="top-toolbar">
      <div className="brand-lockup">
        <span className="brand-mark">W</span>
        <div>
          <strong>WOMAP</strong>
          <span>图斑工坊</span>
        </div>
      </div>

      <nav className="toolbar-actions" aria-label="主工具栏">
        <Tooltip title="导入数据">
          <Button icon={<Import size={17} />} />
        </Tooltip>
        <Tooltip title="保存项目">
          <Button icon={<Save size={17} />} />
        </Tooltip>
        <Tooltip title="导出成果">
          <Button icon={<Download size={17} />} />
        </Tooltip>
        <Divider type="vertical" />
        {tools.map((tool) => {
          const Icon = tool.icon;
          return (
            <Tooltip key={tool.key} title={tool.label}>
              <Button
                type={activeTool === tool.key ? 'primary' : 'default'}
                icon={<Icon size={17} />}
                onClick={() => setActiveTool(tool.key)}
                aria-label={tool.label}
              />
            </Tooltip>
          );
        })}
        <Divider type="vertical" />
        <Tooltip title="撤销">
          <Button icon={<Undo2 size={17} />} />
        </Tooltip>
        <Tooltip title="重做">
          <Button icon={<Redo2 size={17} />} />
        </Tooltip>
      </nav>
    </header>
  );
}
