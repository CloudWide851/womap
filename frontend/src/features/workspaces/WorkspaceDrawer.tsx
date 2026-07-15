import {
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Empty,
  Input,
  Modal,
  Radio,
  Select,
  Tag,
  Upload,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  Archive,
  Download,
  FileInput,
  FolderKanban,
  MapPinCheck,
  Plus,
  Save,
  Trash2,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  downloadWorkspacePackage,
  exportWorkspace,
  getJob,
  getLayerFeatureSummaries,
  importWorkspacePackage,
  previewWorkspacePackage,
} from '../../services/api';
import { useWorkspaceContextStore } from '../../stores/useWorkspaceContextStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { MapFeatureSummary, WorkspacePackagePreview } from '../../types/workspaces';

interface WorkspaceDrawerProps {
  open: boolean;
  onClose: () => void;
}

type CreateKind = 'blank' | 'copy';

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function waitForJob(jobId: string) {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const job = await getJob(jobId);
    if (job.status === 'done') return job;
    if (['failed', 'interrupted'].includes(job.status)) {
      throw new Error(job.message ?? '后台任务未完成。');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error('后台任务等待超时，可在任务面板稍后重试下载。');
}

export function WorkspaceDrawer({ open, onClose }: WorkspaceDrawerProps) {
  const workspaces = useWorkspaceContextStore((state) => state.workspaces);
  const current = useWorkspaceContextStore((state) => state.current);
  const catalog = useWorkspaceContextStore((state) => state.catalog);
  const dirty = useWorkspaceContextStore((state) => state.dirty);
  const loading = useWorkspaceContextStore((state) => state.loading);
  const error = useWorkspaceContextStore((state) => state.error);
  const refreshCatalog = useWorkspaceContextStore((state) => state.refreshCatalog);
  const switchWorkspace = useWorkspaceContextStore((state) => state.switchWorkspace);
  const saveCurrent = useWorkspaceContextStore((state) => state.saveCurrent);
  const createBlank = useWorkspaceContextStore((state) => state.createBlank);
  const saveAs = useWorkspaceContextStore((state) => state.saveAs);
  const deleteCurrent = useWorkspaceContextStore((state) => state.deleteCurrent);
  const discardChanges = useWorkspaceContextStore((state) => state.discardChanges);
  const setMetadata = useWorkspaceContextStore((state) => state.setMetadata);
  const setLayerIncluded = useWorkspaceContextStore((state) => state.setLayerIncluded);
  const setLayerSelection = useWorkspaceContextStore((state) => state.setLayerSelection);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const [pendingWorkspaceId, setPendingWorkspaceId] = useState<number | null>(null);
  const [createKind, setCreateKind] = useState<CreateKind | null>(null);
  const [newName, setNewName] = useState('');
  const [featureOptions, setFeatureOptions] = useState<Record<number, MapFeatureSummary[]>>({});
  const [busyLayerId, setBusyLayerId] = useState<number | null>(null);
  const [packagePreview, setPackagePreview] = useState<WorkspacePackagePreview | null>(null);
  const [packageStrategy, setPackageStrategy] = useState<'copy' | 'replace'>('copy');
  const [packageBusy, setPackageBusy] = useState(false);

  useEffect(() => {
    if (open) void refreshCatalog();
  }, [open, refreshCatalog]);

  useEffect(() => {
    const handlePicked = (event: Event) => {
      const detail = (event as CustomEvent<{ layerId: number; featureId: number }>).detail;
      if (!current || !detail) return;
      const state = current.layers.find((item) => item.layer.id === detail.layerId);
      if (!state) return;
      const nextIds = Array.from(new Set([...state.config.selection.feature_ids, detail.featureId]));
      setLayerSelection(detail.layerId, {
        mode: 'include',
        feature_ids: nextIds,
        source_feature_ids: state.config.selection.source_feature_ids,
      });
    };
    window.addEventListener('womap:workspace-feature-picked', handlePicked);
    return () => window.removeEventListener('womap:workspace-feature-picked', handlePicked);
  }, [current, setLayerSelection]);

  const includedIds = useMemo(
    () => new Set(current?.layers.map((item) => item.layer.id) ?? []),
    [current?.layers],
  );

  const handleWorkspaceChange = (workspaceId: number) => {
    if (!dirty) {
      void switchWorkspace(workspaceId);
      return;
    }
    setPendingWorkspaceId(workspaceId);
  };

  const handleSave = async () => {
    try {
      await saveCurrent();
      showNotice({ tone: 'success', title: '工作空间已保存', detail: 'revision 已更新。' });
    } catch (reason) {
      showNotice({
        tone: 'warning',
        title: '工作空间保存失败',
        detail: reason instanceof Error ? reason.message : '保存服务返回未知错误。',
      });
    }
  };

  const handleCreate = async () => {
    if (!newName.trim() || !createKind) return;
    try {
      if (createKind === 'blank') await createBlank(newName);
      else await saveAs(newName);
      setCreateKind(null);
      setNewName('');
      await refreshCatalog();
    } catch (reason) {
      showNotice({
        tone: 'warning',
        title: '工作空间创建失败',
        detail: reason instanceof Error ? reason.message : '创建服务返回未知错误。',
      });
    }
  };

  const ensureFeatureOptions = async (layerId: number) => {
    if (featureOptions[layerId] || !current) return;
    setBusyLayerId(layerId);
    try {
      const page = await getLayerFeatureSummaries(layerId, current.id);
      setFeatureOptions((state) => ({ ...state, [layerId]: page.items }));
    } catch (reason) {
      showNotice({
        tone: 'warning',
        title: '图斑列表加载失败',
        detail: reason instanceof Error ? reason.message : '图斑服务返回未知错误。',
      });
    } finally {
      setBusyLayerId(null);
    }
  };

  const handleExport = async () => {
    if (!current) return;
    setPackageBusy(true);
    try {
      if (dirty) await saveCurrent();
      const job = await exportWorkspace(current.id);
      showNotice({ tone: 'info', title: '正在生成工作空间包', detail: '完成后会自动下载。' });
      await waitForJob(job.id);
      const result = await downloadWorkspacePackage(job.id);
      saveBlob(result.blob, result.filename);
      showNotice({ tone: 'success', title: '工作空间包已生成', detail: result.filename });
    } catch (reason) {
      showNotice({
        tone: 'warning',
        title: '工作空间包导出失败',
        detail: reason instanceof Error ? reason.message : '导出服务返回未知错误。',
      });
    } finally {
      setPackageBusy(false);
    }
  };

  const uploadProps: UploadProps = {
    accept: '.womap.zip,application/zip',
    showUploadList: false,
    beforeUpload: (file) => {
      setPackageBusy(true);
      void previewWorkspacePackage(file as File)
        .then((preview) => {
          setPackagePreview(preview);
          setPackageStrategy(preview.conflicting_workspace_id ? 'copy' : 'copy');
        })
        .catch((reason) => {
          showNotice({
            tone: 'warning',
            title: '工作空间包预览失败',
            detail: reason instanceof Error ? reason.message : '工作空间包无效。',
          });
        })
        .finally(() => setPackageBusy(false));
      return false;
    },
  };

  const handleImport = async () => {
    if (!packagePreview) return;
    setPackageBusy(true);
    try {
      const job = await importWorkspacePackage(
        packagePreview.upload_token,
        packageStrategy,
        packageStrategy === 'replace' ? packagePreview.conflicting_workspace_id : null,
      );
      showNotice({ tone: 'info', title: '正在导入工作空间包', detail: '数据将先写入 staging。' });
      const done = await waitForJob(job.id);
      const workspaceId = Number(done.result.workspace_id);
      if (Number.isInteger(workspaceId)) await switchWorkspace(workspaceId);
      setPackagePreview(null);
      await refreshCatalog();
      showNotice({ tone: 'success', title: '工作空间包已导入', detail: done.message ?? '导入完成。' });
    } catch (reason) {
      showNotice({
        tone: 'warning',
        title: '工作空间包导入失败',
        detail: reason instanceof Error ? reason.message : '导入服务返回未知错误。',
      });
    } finally {
      setPackageBusy(false);
    }
  };

  return (
    <Drawer
      className="workspace-drawer"
      title={<span className="workspace-drawer-title"><FolderKanban size={17} /> 工作空间</span>}
      open={open}
      onClose={onClose}
      width={540}
      destroyOnHidden
    >
      <div className="workspace-toolbar">
        <Select
          aria-label="当前工作空间"
          value={current?.id}
          loading={loading}
          options={workspaces.map((workspace) => ({
            value: workspace.id,
            label: `${workspace.name}${workspace.is_default ? ' · 默认' : ''}`,
          }))}
          onChange={handleWorkspaceChange}
          classNames={{ popup: { root: 'womap-select-popup' } }}
        />
        <Button icon={<Plus size={15} />} onClick={() => setCreateKind('blank')}>新建</Button>
        <Button icon={<Archive size={15} />} disabled={!current} onClick={() => setCreateKind('copy')}>
          另存为
        </Button>
        <Button type="primary" icon={<Save size={15} />} disabled={!current || !dirty} onClick={handleSave}>
          保存
        </Button>
      </div>

      {error && <div className="workspace-error" role="alert">{error}</div>}
      {current ? (
        <>
          <div className="workspace-meta-grid">
            <label>名称<Input value={current.name} onChange={(event) => setMetadata({ name: event.target.value })} /></label>
            <label>描述<Input value={current.description} onChange={(event) => setMetadata({ description: event.target.value })} /></label>
          </div>
          <div className="workspace-revision-row">
            <span>revision {current.revision}</span>
            <span>{current.workspace_uuid}</span>
            {dirty && <Tag color="gold">未保存</Tag>}
          </div>

          <section className="workspace-section">
            <div className="workspace-section-heading"><strong>数据内容</strong><span>按来源分组</span></div>
            <Collapse
              ghost
              items={(catalog?.groups ?? []).map((group) => ({
                key: group.key,
                label: `${group.label} · ${group.layers.length}`,
                children: (
                  <div className="workspace-layer-picker">
                    {group.layers.map((layer) => {
                      const state = current.layers.find((item) => item.layer.id === layer.id);
                      const selection = state?.config.selection ?? { mode: 'all', feature_ids: [], source_feature_ids: [] };
                      return (
                        <div className="workspace-layer-entry" key={layer.id}>
                          <Checkbox
                            checked={includedIds.has(layer.id)}
                            onChange={(event) => setLayerIncluded(layer, event.target.checked)}
                          >
                            {layer.name} <em>{layer.feature_count}</em>
                          </Checkbox>
                          {state && (
                            <div className="workspace-feature-choice">
                              <Radio.Group
                                size="small"
                                value={selection.mode}
                                onChange={(event) => {
                                  const mode = event.target.value as 'all' | 'include';
                                  setLayerSelection(layer.id, mode === 'all'
                                    ? { mode, feature_ids: [], source_feature_ids: [] }
                                    : { ...selection, mode });
                                  if (mode === 'include') void ensureFeatureOptions(layer.id);
                                }}
                                options={[{ label: '全部图斑', value: 'all' }, { label: '指定图斑', value: 'include' }]}
                              />
                              {selection.mode === 'include' && (
                                <div className="workspace-feature-select-row">
                                  <Select
                                    mode="multiple"
                                    maxTagCount="responsive"
                                    placeholder="选择图斑"
                                    loading={busyLayerId === layer.id}
                                    value={selection.feature_ids}
                                    options={(featureOptions[layer.id] ?? []).map((feature) => ({ value: feature.id, label: feature.label }))}
                                    onFocus={() => void ensureFeatureOptions(layer.id)}
                                    onChange={(featureIds) => setLayerSelection(layer.id, {
                                      mode: 'include',
                                      feature_ids: featureIds,
                                      source_feature_ids: [],
                                    })}
                                    classNames={{ popup: { root: 'womap-select-popup' } }}
                                  />
                                  <Button
                                    icon={<MapPinCheck size={14} />}
                                    onClick={() => window.dispatchEvent(new CustomEvent('womap:start-workspace-feature-pick', { detail: { layerId: layer.id } }))}
                                  >
                                    地图拾取
                                  </Button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ),
              }))}
            />
          </section>

          <section className="workspace-section workspace-package-section">
            <div className="workspace-section-heading"><strong>可移植工作空间包</strong><span>GeoPackage · 不包含凭据与瓦片</span></div>
            <div className="workspace-package-actions">
              <Button icon={<Download size={15} />} loading={packageBusy} onClick={handleExport}>导出 .womap.zip</Button>
              <Upload {...uploadProps}>
                <Button icon={<FileInput size={15} />} loading={packageBusy}>选择包并预览</Button>
              </Upload>
            </div>
            {packagePreview && (
              <div className="workspace-package-preview">
                <strong>{packagePreview.workspace_name}</strong>
                <span>{packagePreview.layer_count} 图层 · {packagePreview.feature_count} 图斑 · {packagePreview.package_version}</span>
                <span>底图 {packagePreview.basemap.name}{packagePreview.basemap_missing ? ' · 需重新绑定' : ''}</span>
                {packagePreview.warnings.map((warning) => <small key={warning}>{warning}</small>)}
                <Radio.Group
                  value={packageStrategy}
                  onChange={(event) => setPackageStrategy(event.target.value)}
                  options={[
                    { label: '创建副本', value: 'copy' },
                    { label: '覆盖同 UUID', value: 'replace', disabled: !packagePreview.conflicting_workspace_id },
                  ]}
                />
                <Button type="primary" loading={packageBusy} onClick={handleImport}>确认导入</Button>
              </div>
            )}
          </section>

          <Button
            danger
            icon={<Trash2 size={15} />}
            disabled={current.is_default}
            onClick={() => Modal.confirm({
              title: '删除当前工作空间？',
              content: '只删除工作空间定义，不删除可能被其他工作空间引用的数据图层。',
              okText: '删除',
              okButtonProps: { danger: true },
              cancelText: '取消',
              onOk: deleteCurrent,
            })}
          >
            删除工作空间
          </Button>
        </>
      ) : <Empty description="暂无工作空间" />}

      <Modal
        open={createKind !== null}
        title={createKind === 'blank' ? '新建工作空间' : '另存为工作空间'}
        okText="创建"
        cancelText="取消"
        okButtonProps={{ disabled: !newName.trim() }}
        onOk={handleCreate}
        onCancel={() => { setCreateKind(null); setNewName(''); }}
      >
        <Input autoFocus maxLength={120} value={newName} placeholder="工作空间名称" onChange={(event) => setNewName(event.target.value)} />
      </Modal>

      <Modal
        open={pendingWorkspaceId !== null}
        title="当前工作空间有未保存修改"
        footer={[
          <Button key="cancel" onClick={() => setPendingWorkspaceId(null)}>取消</Button>,
          <Button key="discard" onClick={() => {
            const target = pendingWorkspaceId;
            setPendingWorkspaceId(null);
            void discardChanges().then(() => {
              if (target !== null) return switchWorkspace(target);
            });
          }}>放弃修改</Button>,
          <Button key="save" type="primary" onClick={() => {
            const target = pendingWorkspaceId;
            setPendingWorkspaceId(null);
            void saveCurrent().then(() => {
              if (target !== null) return switchWorkspace(target);
            });
          }}>保存并切换</Button>,
        ]}
        onCancel={() => setPendingWorkspaceId(null)}
      >
        保存后切换、放弃本地修改，或取消本次操作。
      </Modal>
    </Drawer>
  );
}
