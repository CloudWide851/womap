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
  Image,
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
import type {
  CatalogDataset,
  ImportCatalog,
  ImportJob,
  ImportJobProgressDetail,
  ImportSettings,
  RasterJobProgressDetail,
} from '../../types/imports';

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

function isImportJob(job: ImportJob) {
  return job.job_type === 'import-sync' || job.job_type === 'import-data';
}

function isRasterProgress(
  detail: ImportJob['detail'] | undefined,
): detail is RasterJobProgressDetail {
  return detail?.kind === 'raster-process';
}

function isVectorImportProgress(
  detail: ImportJob['detail'] | undefined,
): detail is ImportJobProgressDetail {
  return detail?.kind === 'import';
}

function importJobSourceId(job: ImportJob) {
  return job.detail.kind === 'import' || job.detail.kind === 'raster-process'
    ? job.detail.source_id
    : null;
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
    () => jobs.filter(isImportJob).find((job) => importJobSourceId(job) === sourceId),
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
      showNotice({ tone: 'info', title: '开始同步目录', detail: '正在识别矢量、GeoTIFF 与多维栅格数据。' });
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

  const renderDatasets = (datasets: CatalogDataset[], emptyDescription: string) => {
    if (datasets.length === 0) {
      return (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyDescription}>
          <Button size="small" icon={<RefreshCw size={14} />} onClick={() => sourceId && void loadCatalog(sourceId)}>
            重新扫描
          </Button>
        </Empty>
      );
    }
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
                  {dataset.dataset_kind === 'raster'
                    ? <Image size={15} />
                    : dataset.format === 'gdb'
                      ? <Database size={15} />
                      : <HardDrive size={15} />}
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
                    {dataset.dataset_kind === 'raster' && dataset.raster
                      ? `${dataset.raster.width.toLocaleString('zh-CN')} × ${dataset.raster.height.toLocaleString('zh-CN')} · ${dataset.raster.band_count} 波段 · ${formatBytes(dataset.raster.byte_size)}`
                      : `${dataset.geometry_type} · ${dataset.feature_count.toLocaleString('zh-CN')} 个要素`}
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
  const rasterProgress = isRasterProgress(jobDetail) ? jobDetail : null;
  const vectorProgress = isVectorImportProgress(jobDetail) ? jobDetail : null;
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
        {settings && (
          <Tooltip title={`栅格托管目录：${settings.raster_store_path}`}>
            <Tag>{settings.raster_quota_gb} GB 栅格配额</Tag>
          </Tooltip>
        )}
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

      {error && (
        <div className="import-error" role="alert">
          <span>{error}</span>
          <Button size="small" onClick={onOpenSettings}>检查数据源</Button>
        </div>
      )}

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
            <span>图层 {rasterProgress?.dataset_name ?? vectorProgress?.current_layer ?? '--'}</span>
            {rasterProgress ? (
              <>
                <span>数据 {formatBytes(rasterProgress.processed_bytes)}/{formatBytes(rasterProgress.total_bytes)}</span>
                <span>块 {rasterProgress.processed_blocks}/{rasterProgress.total_blocks}</span>
                <span>策略 COG · 512px · Overview</span>
              </>
            ) : (
              <>
                <span>要素 {vectorProgress?.imported_features ?? 0}/{vectorProgress?.total_features ?? 0}</span>
                <span>批次 {vectorProgress?.current_batch ?? 0}/{vectorProgress?.total_batches ?? 0}</span>
                <span>传输 {formatBytes(vectorProgress?.transferred_bytes ?? 0)}/{formatBytes(vectorProgress?.total_bytes ?? 0)}</span>
              </>
            )}
          </div>
          {jobDetail?.warnings.map((warning) => (
            <div key={warning} className="import-progress-warning">{warning}</div>
          ))}
          {jobDetail?.error && <div className="import-error" role="alert">{jobDetail.error}</div>}
        </section>
      )}

      {settings && settings.sources.length === 0 ? (
        <section className="import-empty-guide" aria-label="导入准备">
          <FolderSync size={24} aria-hidden="true" />
          <div>
            <strong>先添加一个数据源</strong>
            <span>支持本地目录和 SMB，共享凭据只保存在 Windows Credential Manager。</span>
          </div>
          <Button type="primary" icon={<Settings size={15} />} onClick={onOpenSettings}>
            添加数据源
          </Button>
        </section>
      ) : sourceId && !catalog && !error ? (
        <div className="import-catalog-loading" role="status">正在读取目录清单…</div>
      ) : (
        <Tabs
          items={[
            {
              key: 'pending',
              label: `未导入 ${pending.length}`,
              children: renderDatasets(pending, '没有待导入数据，可重新扫描目录'),
            },
            {
              key: 'imported',
              label: `已导入 ${imported.length}`,
              children: renderDatasets(imported, '尚未导入数据'),
            },
          ]}
        />
      )}

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
