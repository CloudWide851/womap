import {
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Progress,
  Select,
  Tabs,
  Tag,
  Tooltip,
} from 'antd';
import {
  CheckCircle2,
  Database,
  FolderSync,
  HardDrive,
  PauseCircle,
  RefreshCw,
  Settings,
  TriangleAlert,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  getImportCatalog,
  getImportSettings,
  importDatasets,
  resumeImportJob,
  syncImportSource,
} from '../../services/api';
import { useJobsStore } from '../../stores/useJobsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { CatalogDataset, ImportCatalog, ImportSettings } from '../../types/imports';

interface ImportCenterProps {
  open: boolean;
  onClose: () => void;
  onOpenSettings: () => void;
}

function formatBytes(value: number) {
  if (value <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

const stateLabels = {
  unimported: '待导入',
  imported: '已导入',
  changed: '待更新',
  interrupted: '可继续',
} as const;

export function ImportCenter({ open, onClose, onOpenSettings }: ImportCenterProps) {
  const [settings, setSettings] = useState<ImportSettings | null>(null);
  const [sourceId, setSourceId] = useState('');
  const [catalog, setCatalog] = useState<ImportCatalog | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [crsOverrides, setCrsOverrides] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const jobs = useJobsStore((state) => state.jobs);
  const refreshJobs = useJobsStore((state) => state.refresh);
  const upsertJob = useJobsStore((state) => state.upsert);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const completedJobRef = useRef<string | null>(null);
  const activeJob = useMemo(
    () => jobs.find((job) => job.detail.source_id === sourceId),
    [jobs, sourceId],
  );

  const loadCatalog = async (nextSourceId = sourceId) => {
    if (!nextSourceId) {
      setCatalog(null);
      return;
    }
    setCatalog(await getImportCatalog(nextSourceId));
  };

  useEffect(() => {
    if (!open) return;
    let active = true;
    setError(null);
    void getImportSettings()
      .then((value) => {
        if (!active) return;
        setSettings(value);
        const nextSource = sourceId || value.sources.find((source) => source.enabled)?.id || '';
        setSourceId(nextSource);
        if (nextSource) void loadCatalog(nextSource).catch(() => undefined);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : '数据源加载失败。'));
    void refreshJobs();
    return () => {
      active = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !activeJob || !['queued', 'running'].includes(activeJob.status)) return;
    const timer = window.setInterval(() => void refreshJobs(), 1000);
    return () => window.clearInterval(timer);
  }, [activeJob, open, refreshJobs]);

  useEffect(() => {
    if (!activeJob || activeJob.status !== 'done' || completedJobRef.current === activeJob.id) return;
    completedJobRef.current = activeJob.id;
    void loadCatalog().catch(() => undefined);
    if (activeJob.job_type === 'import-data') {
      window.dispatchEvent(new Event('womap:layers-changed'));
    }
  }, [activeJob]);

  const runAction = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : '操作失败。';
      setError(message);
      showNotice({ tone: 'warning', title: '导入操作失败', detail: message });
    } finally {
      setBusy(false);
    }
  };

  const handleSync = () =>
    runAction(async () => {
      const job = await syncImportSource(sourceId);
      upsertJob(job);
      showNotice({ tone: 'info', title: '开始同步目录', detail: '正在扫描 SHP 与 GDB 数据。' });
    });

  const handleImport = () =>
    runAction(async () => {
      const job = await importDatasets(sourceId, selectedIds, crsOverrides);
      upsertJob(job);
      setSelectedIds([]);
      showNotice({ tone: 'info', title: '开始导入数据', detail: `已选择 ${selectedIds.length} 个图层。` });
    });

  const handleResume = (jobId: string) =>
    runAction(async () => {
      upsertJob(await resumeImportJob(jobId));
    });

  const renderDatasets = (datasets: CatalogDataset[]) => {
    if (datasets.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
    let lastContainer = '';
    return (
      <div className="import-dataset-list">
        {datasets.map((dataset) => {
          const showContainer = dataset.container !== lastContainer;
          lastContainer = dataset.container;
          const selected = selectedIds.includes(dataset.id);
          return (
            <div key={dataset.id}>
              {showContainer && (
                <div className="import-container-heading">
                  {dataset.format === 'gdb' ? <Database size={15} /> : <HardDrive size={15} />}
                  <span>{dataset.container}</span>
                </div>
              )}
              <div className={`import-dataset-row ${dataset.valid ? '' : 'is-invalid'}`}>
                <Checkbox
                  checked={selected}
                  disabled={!dataset.valid || dataset.import_state === 'imported'}
                  onChange={(event) =>
                    setSelectedIds((current) =>
                      event.target.checked
                        ? [...current, dataset.id]
                        : current.filter((id) => id !== dataset.id),
                    )
                  }
                  aria-label={`选择 ${dataset.layer_name}`}
                />
                <span className="import-dataset-main">
                  <strong>{dataset.layer_name}</strong>
                  <span>
                    {dataset.geometry_type} · {dataset.feature_count.toLocaleString('zh-CN')} 个要素
                  </span>
                </span>
                <Tag>{dataset.format.toUpperCase()}</Tag>
                <Tag className={`import-state-tag is-${dataset.import_state}`}>
                  {stateLabels[dataset.import_state]}
                </Tag>
                {dataset.import_state === 'changed' && (
                  <span className="import-replace-hint">成功后替换</span>
                )}
                {(dataset.missing_required.length > 0 || dataset.errors.length > 0) && (
                  <Tooltip title={[...dataset.missing_required, ...dataset.errors].join('；')}>
                    <TriangleAlert size={16} className="import-warning-icon" aria-label="数据校验失败" />
                  </Tooltip>
                )}
                {dataset.missing_optional.length > 0 && dataset.valid && (
                  <Tooltip title={`缺少可选附件：${dataset.missing_optional.join(', ')}`}>
                    <TriangleAlert size={16} className="import-advisory-icon" aria-label="数据附件不完整" />
                  </Tooltip>
                )}
                {dataset.resumable_job_id && (
                  <Button
                    size="small"
                    icon={<PauseCircle size={14} />}
                    onClick={() => handleResume(dataset.resumable_job_id!)}
                  >
                    继续
                  </Button>
                )}
                {!dataset.crs && dataset.valid && dataset.import_state !== 'imported' && (
                  <Input
                    size="small"
                    className="import-crs-input"
                    placeholder="EPSG:4326"
                    value={crsOverrides[dataset.id] ?? ''}
                    onChange={(event) =>
                      setCrsOverrides((current) => ({ ...current, [dataset.id]: event.target.value }))
                    }
                    aria-label={`${dataset.layer_name} 坐标系`}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const pending = catalog?.datasets.filter((item) => item.import_state !== 'imported') ?? [];
  const imported = catalog?.datasets.filter((item) => item.import_state === 'imported') ?? [];
  const source = settings?.sources.find((item) => item.id === sourceId);
  const jobDetail = activeJob?.detail;
  const missingCrsOverride = selectedIds.some((datasetId) => {
    const dataset = catalog?.datasets.find((item) => item.id === datasetId);
    return dataset && !dataset.crs && !crsOverrides[datasetId]?.trim();
  });

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={920}
      title="导入中心"
      className="import-center-modal"
      destroyOnHidden
    >
      <div className="import-center-toolbar">
        <Select
          value={sourceId || undefined}
          placeholder="选择数据源"
          options={settings?.sources.map((item) => ({
            value: item.id,
            label: `${item.name} · ${item.kind === 'smb' ? 'SMB' : '本地'}`,
            disabled: !item.enabled,
          }))}
          onChange={(value) => {
            setSourceId(value);
            setSelectedIds([]);
            void loadCatalog(value).catch((reason) =>
              setError(reason instanceof Error ? reason.message : '目录加载失败。'),
            );
          }}
          classNames={{ popup: { root: 'womap-select-popup' } }}
          aria-label="导入数据源"
        />
        <span className="import-source-status">
          {source?.kind === 'smb' && source.credential_configured ? (
            <><CheckCircle2 size={15} /> 已配置凭据</>
          ) : source ? (
            <><HardDrive size={15} /> {source.kind === 'smb' ? '待配置凭据' : '本地目录'}</>
          ) : (
            '尚未配置数据源'
          )}
        </span>
        <Button icon={<Settings size={15} />} onClick={onOpenSettings}>管理数据源</Button>
        <Button
          type="primary"
          icon={<FolderSync size={15} />}
          disabled={!sourceId}
          loading={busy && activeJob?.job_type === 'import-sync'}
          onClick={handleSync}
        >
          同步目录
        </Button>
      </div>

      {error && <div className="import-error" role="alert">{error}</div>}

      {activeJob && (
        <section className="import-progress-panel" aria-label="导入任务进度">
          <div className="import-progress-heading">
            <strong>{activeJob.job_type === 'import-sync' ? '目录同步' : '数据导入'}</strong>
            <span>{activeJob.message}</span>
            {['interrupted', 'failed'].includes(activeJob.status) && (
              <Button size="small" icon={<PauseCircle size={14} />} onClick={() => handleResume(activeJob.id)}>
                继续导入
              </Button>
            )}
          </div>
          <Progress
            percent={activeJob.progress}
            status={activeJob.status === 'failed' ? 'exception' : activeJob.status === 'done' ? 'success' : 'active'}
          />
          <div className="import-progress-metrics">
            <span>阶段 {jobDetail?.stage ?? '--'}</span>
            <span>图层 {jobDetail?.current_layer ?? '--'}</span>
            <span>要素 {jobDetail?.imported_features ?? 0}/{jobDetail?.total_features ?? 0}</span>
            <span>批次 {jobDetail?.current_batch ?? 0}/{jobDetail?.total_batches ?? 0}</span>
            <span>传输 {formatBytes(jobDetail?.transferred_bytes ?? 0)}/{formatBytes(jobDetail?.total_bytes ?? 0)}</span>
          </div>
          {jobDetail?.warnings.map((warning) => (
            <div key={warning} className="import-progress-warning">{warning}</div>
          ))}
          {jobDetail?.error && <div className="import-error" role="alert">{jobDetail.error}</div>}
        </section>
      )}

      <Tabs
        items={[
          { key: 'pending', label: `未导入 ${pending.length}`, children: renderDatasets(pending) },
          { key: 'imported', label: `已导入 ${imported.length}`, children: renderDatasets(imported) },
        ]}
      />

      <div className="import-center-actions">
        <Button onClick={() => sourceId && void loadCatalog(sourceId)} icon={<RefreshCw size={15} />}>
          刷新状态
        </Button>
        <Button
          type="primary"
          disabled={selectedIds.length === 0 || missingCrsOverride}
          loading={busy && activeJob?.job_type === 'import-data'}
          onClick={handleImport}
        >
          导入所选 {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
        </Button>
      </div>
    </Modal>
  );
}
