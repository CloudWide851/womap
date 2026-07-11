import {
  Combine,
  DatabaseZap,
  Download,
  Blend,
  Hand,
  Import,
  MapPinned,
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
import {
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Popover,
  Radio,
  Select,
} from 'antd';
import { lazy, memo, Suspense, useEffect, useMemo, useState } from 'react';
import type { ComponentType } from 'react';

import womapLogo from '../../../logo.svg';
import { IconTooltipButton } from './IconTooltipButton';
import {
  exportLayers,
  getLocalRuntimeSettings,
  updateLocalRuntimeSettings,
} from '../services/api';
import type { LocalRuntimeSettings, LocalRuntimeSettingsUpdate } from '../services/api';
import { formatRemainingTime, useAuthStore } from '../stores/useAuthStore';
import { useMapStore } from '../stores/useMapStore';
import { useSettingsStore } from '../stores/useSettingsStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import type { WorkspaceMode } from '../types/workspace';

const ImportCenter = lazy(() =>
  import('../features/imports/ImportCenter').then((module) => ({ default: module.ImportCenter })),
);

const tools = [
  { key: 'select', label: '选择', icon: MousePointer2 },
  { key: 'pan', label: '平移', icon: Hand },
  { key: 'move', label: '移动', icon: Move },
  { key: 'rotate', label: '旋转', icon: RotateCw },
  { key: 'clip', label: '裁切', icon: Scissors },
  { key: 'split', label: '分割', icon: SplitSquareHorizontal },
  { key: 'merge', label: '合并', icon: Combine },
];

const workspaceModeOptions: Array<{ label: string; value: WorkspaceMode }> = [
  { value: 'browse', label: '浏览查看' },
  { value: 'edit', label: '图斑编辑' },
  { value: 'swipe', label: '两期卷帘' },
  { value: 'inspect', label: '属性查看' },
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

interface LocalConfigDialogProps {
  open: boolean;
  onClose: () => void;
  onNotice: (notice: {
    tone: 'info' | 'success' | 'warning';
    title: string;
    detail: string;
  }) => void;
}

function LocalConfigDialog({ open, onClose, onNotice }: LocalConfigDialogProps) {
  const [form] = Form.useForm<LocalRuntimeSettingsUpdate>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [summary, setSummary] = useState<LocalRuntimeSettings | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    getLocalRuntimeSettings()
      .then((settings) => {
        if (cancelled) {
          return;
        }
        setSummary(settings);
        form.setFieldsValue({
          server: settings.server,
          frontend: settings.frontend,
        });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        onNotice({
          tone: 'warning',
          title: '本地配置加载失败',
          detail: error instanceof Error ? error.message : '设置服务返回未知错误。',
        });
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [form, onNotice, open]);

  const handleSave = async (values: LocalRuntimeSettingsUpdate) => {
    setSaving(true);
    try {
      const savedSettings = await updateLocalRuntimeSettings(values);
      setSummary(savedSettings);
      form.setFieldsValue({
        server: savedSettings.server,
        frontend: savedSettings.frontend,
      });
      onNotice({
        tone: 'success',
        title: '本地配置已写入',
        detail: '已保存到 settings.local.yaml，重启服务后按新端口生效。',
      });
    } catch (error) {
      onNotice({
        tone: 'warning',
        title: '本地配置保存失败',
        detail: error instanceof Error ? error.message : '设置服务返回未知错误。',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      className="local-config-modal"
      title="本地运行配置"
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
    >
      <div className="local-config-summary">
        <span>来源 {summary?.config_source ?? '--'}</span>
        <span>写回 {summary?.local_config_path ?? 'config/settings.local.yaml'}</span>
      </div>
      <Form
        form={form}
        layout="vertical"
        className="local-config-form"
        disabled={loading}
        onFinish={handleSave}
      >
        <div className="local-config-grid">
          <Form.Item
            label="API Host"
            name={['server', 'host']}
            rules={[{ required: true, message: '请输入 API Host' }]}
          >
            <Input placeholder="127.0.0.1" />
          </Form.Item>
          <Form.Item
            label="API Port"
            name={['server', 'port']}
            rules={[{ required: true, message: '请输入 API Port' }]}
          >
            <InputNumber min={1} max={65535} controls={false} />
          </Form.Item>
          <Form.Item
            label="Web Host"
            name={['frontend', 'dev_server', 'host']}
            rules={[{ required: true, message: '请输入 Web Host' }]}
          >
            <Input placeholder="127.0.0.1" />
          </Form.Item>
          <Form.Item
            label="Web Port"
            name={['frontend', 'dev_server', 'port']}
            rules={[{ required: true, message: '请输入 Web Port' }]}
          >
            <InputNumber min={1} max={65535} controls={false} />
          </Form.Item>
        </div>
        <div className="local-config-actions">
          <Button onClick={onClose}>关闭</Button>
          <Button type="primary" htmlType="submit" loading={saving}>
            写入本地配置
          </Button>
        </div>
      </Form>
    </Modal>
  );
}

interface TopToolbarProps {
  onOpenSettings: (section?: 'import-sources') => void;
}

export function TopToolbar({ onOpenSettings }: TopToolbarProps) {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const workspaceMode = useWorkspaceStore((state) => state.workspaceMode);
  const setActiveTool = useWorkspaceStore((state) => state.setActiveTool);
  const setWorkspaceMode = useWorkspaceStore((state) => state.setWorkspaceMode);
  const notifyCommand = useWorkspaceStore((state) => state.notifyCommand);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedBasemapId = useMapStore((state) => state.selectedBasemapId);
  const setSelectedBasemap = useMapStore((state) => state.setSelectedBasemap);
  const setSwipeEnabled = useMapStore((state) => state.setSwipeEnabled);
  const basemaps = useSettingsStore((state) => state.basemaps);
  const collapseSidePanelsForSwipe = useSettingsStore(
    (state) => state.collapseSidePanelsForSwipe,
  );
  const restoreSidePanelsAfterSwipe = useSettingsStore(
    (state) => state.restoreSidePanelsAfterSwipe,
  );
  const mode = useAuthStore((state) => state.mode);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const now = useAuthStore((state) => state.now);
  const logout = useAuthStore((state) => state.logout);
  const remaining = expiresAt ? formatRemainingTime(expiresAt - now) : '--';
  const [exportOpen, setExportOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<'shp' | 'gdb'>('shp');
  const [checkedLayerIds, setCheckedLayerIds] = useState<string[]>([]);
  const basemapOptions = useMemo(
    () =>
      basemaps.map((provider) => ({
        label: provider.name,
        value: provider.id,
        disabled: !provider.enabled,
      })),
    [basemaps],
  );
  const backendLayerIds = useMemo(
    () =>
      checkedLayerIds
        .map((layerId) => Number(layerId))
        .filter((layerId) => Number.isInteger(layerId) && layerId > 0),
    [checkedLayerIds],
  );

  const handleModeChange = (nextMode: WorkspaceMode) => {
    const leavingSwipe = workspaceMode === 'swipe' && nextMode !== 'swipe';
    setWorkspaceMode(nextMode);
    if (nextMode === 'swipe') {
      setSwipeEnabled(true);
      collapseSidePanelsForSwipe();
      return;
    }
    if (leavingSwipe) {
      setSwipeEnabled(false);
      restoreSidePanelsAfterSwipe();
    }
  };

  const handleToolSelect = (toolKey: string) => {
    if (workspaceMode === 'swipe') {
      setSwipeEnabled(false);
      restoreSidePanelsAfterSwipe();
    }
    setWorkspaceMode('edit');
    setActiveTool(toolKey);
  };

  const handleBasemapChange = (basemapId: string) => {
    setSelectedBasemap(basemapId);
    const provider = basemaps.find((item) => item.id === basemapId);
    showNotice({
      tone: 'info',
      title: '底图已切换',
      detail: provider ? provider.name : basemapId,
    });
  };

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
            onClick={() => setImportOpen(true)}
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
          <IconTooltipButton
            className="tool-icon-button"
            label="本地配置"
            icon={<DatabaseZap size={17} />}
            onClick={() => setConfigOpen(true)}
          />
        </span>

        <span className="toolbar-cluster toolbar-cluster-mode" role="group" aria-label="工作模式">
          <Blend size={15} aria-hidden="true" />
          <Select
            size="small"
            className="toolbar-select mode-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="工作模式"
            value={workspaceMode}
            options={workspaceModeOptions}
            onChange={handleModeChange}
          />
        </span>

        <span className="toolbar-cluster toolbar-cluster-basemap" role="group" aria-label="地图底图">
          <MapPinned size={15} aria-hidden="true" />
          <Select
            size="small"
            className="toolbar-select basemap-select"
            classNames={{ popup: { root: 'womap-select-popup' } }}
            aria-label="地图底图"
            value={selectedBasemapId}
            options={basemapOptions}
            onChange={handleBasemapChange}
          />
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
                onClick={() => handleToolSelect(tool.key)}
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
              onClick={() => onOpenSettings()}
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
      <LocalConfigDialog
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onNotice={showNotice}
      />
      <Suspense fallback={null}>
        {importOpen && (
          <ImportCenter
            open={importOpen}
            onClose={() => setImportOpen(false)}
            onOpenSettings={() => {
              setImportOpen(false);
              onOpenSettings('import-sources');
            }}
          />
        )}
      </Suspense>
    </header>
  );
}
