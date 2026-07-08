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
import { Button, Checkbox, Popover, Radio } from 'antd';
import { memo, useMemo, useState } from 'react';
import type { ComponentType } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from './IconTooltipButton';
import { exportLayers } from '../services/api';
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
  const notifyCommand = useWorkspaceStore((state) => state.notifyCommand);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const layers = useWorkspaceStore((state) => state.layers);
  const mode = useAuthStore((state) => state.mode);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const now = useAuthStore((state) => state.now);
  const logout = useAuthStore((state) => state.logout);
  const remaining = expiresAt ? formatRemainingTime(expiresAt - now) : '--';
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<'shp' | 'gdb'>('shp');
  const [checkedLayerIds, setCheckedLayerIds] = useState<string[]>([]);
  const backendLayerIds = useMemo(
    () =>
      checkedLayerIds
        .map((layerId) => Number(layerId))
        .filter((layerId) => Number.isInteger(layerId) && layerId > 0),
    [checkedLayerIds],
  );

  const handleExportOpenChange = (open: boolean) => {
    setExportOpen(open);
    if (open && checkedLayerIds.length === 0) {
      setCheckedLayerIds(layers.filter((layer) => layer.visible).map((layer) => layer.id));
    }
  };

  const handleExport = async () => {
    if (checkedLayerIds.length === 0) {
      showNotice({
        tone: 'warning',
        title: '请选择导出图层',
        detail: '至少勾选一个后端图层后再导出 SHP 或 GDB。',
      });
      return;
    }
    if (backendLayerIds.length === 0) {
      showNotice({
        tone: 'warning',
        title: '暂无后端图层可导出',
        detail: '当前工作台只有本地示例图层；导入或加载后端数据后才能生成 SHP/GDB 成果。',
      });
      return;
    }

    setExporting(true);
    showNotice({
      tone: 'info',
      title: `正在导出 ${exportFormat.toUpperCase()}`,
      detail: `已提交 ${backendLayerIds.length} 个后端图层，完成后会下载 zip 文件。`,
    });

    try {
      const result = await exportLayers(exportFormat, backendLayerIds);
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(url);
      setExportOpen(false);
      showNotice({
        tone: 'success',
        title: `${exportFormat.toUpperCase()} 导出完成`,
        detail: result.filename,
      });
    } catch (error) {
      showNotice({
        tone: 'warning',
        title: `${exportFormat.toUpperCase()} 导出失败`,
        detail: error instanceof Error ? error.message : '导出服务返回未知错误。',
      });
    } finally {
      setExporting(false);
    }
  };

  const exportPanel = (
    <div className="export-popover" aria-label="导出设置">
      <div className="export-popover-header">
        <strong>导出成果</strong>
        <span>选择后端图层与格式</span>
      </div>
      <Checkbox.Group
        className="export-layer-list"
        value={checkedLayerIds}
        onChange={(values) => setCheckedLayerIds(values.map(String))}
      >
        {layers.map((layer) => (
          <Checkbox key={layer.id} value={layer.id} className="export-layer-option">
            <span>{layer.name}</span>
            <em>{layer.geometryType}</em>
          </Checkbox>
        ))}
      </Checkbox.Group>
      <Radio.Group
        className="export-format-toggle"
        optionType="button"
        buttonStyle="solid"
        value={exportFormat}
        onChange={(event) => setExportFormat(event.target.value)}
      >
        <Radio.Button value="shp">SHP</Radio.Button>
        <Radio.Button value="gdb">GDB</Radio.Button>
      </Radio.Group>
      <div className="export-actions">
        <Button size="small" onClick={() => setExportOpen(false)}>
          取消
        </Button>
        <Button size="small" type="primary" loading={exporting} onClick={handleExport}>
          导出 {exportFormat.toUpperCase()}
        </Button>
      </div>
    </div>
  );

  return (
    <header className="top-toolbar">
      <div className="brand-lockup brand-logo-only">
        <img className="brand-logo" src={womapLogo} alt="WOMAP" data-testid="brand-logo" />
      </div>

      <nav className="toolbar-actions" aria-label="主工具栏">
        <span className="toolbar-cluster toolbar-cluster-file" role="group" aria-label="文件操作">
          <IconTooltipButton
            className="tool-icon-button"
            label="导入数据"
            icon={<Import size={17} />}
            onClick={() => notifyCommand('import-data')}
          />
          <IconTooltipButton
            className="tool-icon-button"
            label="保存项目"
            icon={<Save size={17} />}
            onClick={() => notifyCommand('save-project')}
          />
          <Popover
            trigger="click"
            open={exportOpen}
            onOpenChange={handleExportOpenChange}
            content={exportPanel}
            placement="bottomLeft"
          >
            <Button
              className="tool-icon-button"
              aria-label="导出成果"
              title="导出成果"
              icon={<Download size={17} />}
            />
          </Popover>
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
          <IconTooltipButton
            className="tool-icon-button"
            label="撤销"
            icon={<Undo2 size={17} />}
            onClick={() => notifyCommand('undo')}
          />
          <IconTooltipButton
            className="tool-icon-button"
            label="重做"
            icon={<Redo2 size={17} />}
            onClick={() => notifyCommand('redo')}
          />
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
