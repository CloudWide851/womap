import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ImportCenter } from './ImportCenter';
import { useJobsStore } from '../../stores/useJobsStore';

const queuedJob = {
  id: 'import-data-1',
  job_type: 'import-data',
  status: 'queued' as const,
  progress: 0,
  message: '任务已进入队列。',
  detail: {
    stage: 'queued',
    source_id: 'local-1',
    dataset_id: null,
    dataset_name: null,
    current_layer: null,
    current_file: null,
    imported_features: 0,
    total_features: 0,
    current_batch: 0,
    total_batches: 0,
    transferred_bytes: 0,
    total_bytes: 0,
    warnings: [],
    error: null,
  },
  result: {},
};

const apiMocks = vi.hoisted(() => ({
  getJobs: vi.fn(),
  getImportSettings: vi.fn(),
  getImportCatalog: vi.fn(),
  syncImportSource: vi.fn(),
  importDatasets: vi.fn(),
  resumeImportJob: vi.fn(),
}));

vi.mock('../../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/api')>()),
  ...apiMocks,
}));

afterEach(() => {
  cleanup();
  useJobsStore.getState().reset();
  vi.clearAllMocks();
});

describe('ImportCenter', () => {
  it('shows pending/imported tabs and submits selected datasets', async () => {
    apiMocks.getImportSettings.mockResolvedValue({
      cache_path: '.womap-data/import-cache',
      batch_size: 2000,
      sources: [
        {
          id: 'local-1',
          name: '本地资料',
          kind: 'local',
          root_path: 'D:/GIS',
          server: '',
          share: '',
          base_path: '',
          username: '',
          domain: '',
          port: 445,
          encrypt: true,
          enabled: true,
          credential_configured: false,
        },
      ],
    });
    apiMocks.getImportCatalog.mockResolvedValue({
      source_id: 'local-1',
      scanned_at: '2026-07-11T00:00:00Z',
      warnings: [],
      datasets: [
        {
          id: 'pending-1',
          source_id: 'local-1',
          format: 'shp',
          container: 'parcel',
          relative_path: 'parcel/parcel.shp',
          layer_name: 'parcel',
          geometry_type: 'Polygon',
          feature_count: 120,
          crs: 'EPSG:4490',
          bounds: [],
          fields: [],
          fingerprint: 'new',
          valid: true,
          missing_required: [],
          missing_optional: ['.sbn', '.sbx'],
          errors: [],
          import_state: 'unimported',
          resumable_job_id: null,
        },
        {
          id: 'done-1',
          source_id: 'local-1',
          format: 'gdb',
          container: 'base.gdb',
          relative_path: 'base.gdb',
          layer_name: 'roads',
          geometry_type: 'LineString',
          feature_count: 20,
          crs: 'EPSG:3857',
          bounds: [],
          fields: [],
          fingerprint: 'old',
          valid: true,
          missing_required: [],
          missing_optional: [],
          errors: [],
          import_state: 'imported',
          resumable_job_id: null,
        },
      ],
    });
    apiMocks.importDatasets.mockResolvedValue(queuedJob);
    apiMocks.syncImportSource.mockResolvedValue({ ...queuedJob, id: 'import-sync-1', job_type: 'import-sync' });

    render(<ImportCenter open onClose={vi.fn()} onOpenSettings={vi.fn()} />);

    expect((await screen.findAllByText('parcel')).length).toBeGreaterThan(0);
    expect(screen.getByText('未导入 1')).toBeInTheDocument();
    expect(screen.getByText('已导入 1')).toBeInTheDocument();
    expect(screen.getByLabelText('数据附件不完整')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('选择 parcel'));
    fireEvent.click(screen.getByRole('button', { name: '导入所选 (1)' }));

    await waitFor(() =>
      expect(apiMocks.importDatasets).toHaveBeenCalledWith('local-1', ['pending-1'], {}),
    );
  });

  it('shows background errors and resumes an interrupted import', async () => {
    apiMocks.getImportSettings.mockResolvedValue({
      cache_path: '.womap-data/import-cache',
      batch_size: 2000,
      sources: [
        {
          id: 'local-1',
          name: '本地资料',
          kind: 'local',
          root_path: 'D:/GIS',
          server: '',
          share: '',
          base_path: '',
          username: '',
          domain: '',
          port: 445,
          encrypt: true,
          enabled: true,
          credential_configured: false,
        },
      ],
    });
    apiMocks.getImportCatalog.mockResolvedValue({
      source_id: 'local-1',
      scanned_at: '2026-07-11T00:00:00Z',
      warnings: [],
      datasets: [],
    });
    const failedJob = {
      ...queuedJob,
      status: 'failed' as const,
      progress: 45,
      message: '任务失败。',
      detail: {
        ...queuedJob.detail,
        stage: 'failed',
        warnings: ['缺少可选附件 .sbn'],
        error: '数据库连接中断',
      },
    };
    apiMocks.getJobs.mockResolvedValue([failedJob]);
    apiMocks.resumeImportJob.mockResolvedValue({ ...failedJob, status: 'queued', detail: queuedJob.detail });

    render(<ImportCenter open onClose={vi.fn()} onOpenSettings={vi.fn()} />);

    expect(await screen.findByText('数据库连接中断')).toBeInTheDocument();
    expect(screen.getByText('缺少可选附件 .sbn')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '继续导入' }));

    await waitFor(() => expect(apiMocks.resumeImportJob).toHaveBeenCalledWith('import-data-1'));
  });

  it('requires a CRS override before importing data without projection metadata', async () => {
    apiMocks.getImportSettings.mockResolvedValue({
      cache_path: '.womap-data/import-cache',
      batch_size: 2000,
      sources: [
        {
          id: 'local-1',
          name: '本地资料',
          kind: 'local',
          root_path: 'D:/GIS',
          server: '',
          share: '',
          base_path: '',
          username: '',
          domain: '',
          port: 445,
          encrypt: true,
          enabled: true,
          credential_configured: false,
        },
      ],
    });
    apiMocks.getImportCatalog.mockResolvedValue({
      source_id: 'local-1',
      scanned_at: '2026-07-11T00:00:00Z',
      warnings: [],
      datasets: [
        {
          id: 'missing-crs',
          source_id: 'local-1',
          format: 'shp',
          container: 'parcel',
          relative_path: 'parcel/parcel.shp',
          layer_name: 'parcel',
          geometry_type: 'Polygon',
          feature_count: 10,
          crs: null,
          bounds: [],
          fields: [],
          fingerprint: 'new',
          valid: true,
          missing_required: [],
          missing_optional: [],
          errors: [],
          import_state: 'unimported',
          resumable_job_id: null,
        },
      ],
    });

    render(<ImportCenter open onClose={vi.fn()} onOpenSettings={vi.fn()} />);

    await screen.findByLabelText('选择 parcel');
    fireEvent.click(screen.getByLabelText('选择 parcel'));
    expect(screen.getByRole('button', { name: '导入所选 (1)' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('parcel 坐标系'), { target: { value: 'EPSG:4326' } });
    expect(screen.getByRole('button', { name: '导入所选 (1)' })).toBeEnabled();
  });
});
