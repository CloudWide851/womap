import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useJobsStore } from '../../stores/useJobsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { BackendLayerSummary, ImportJob, RasterStyle } from '../../types/imports';
import type { WorkspaceLayer } from '../../types/workspace';
import { RasterInspector } from './RasterInspector';

const apiMocks = vi.hoisted(() => ({
  deriveRaster: vi.fn(),
  exportRasters: vi.fn(),
  getRasterHistogram: vi.fn(),
  updateRasterStyle: vi.fn(),
}));

vi.mock('../../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/api')>()),
  ...apiMocks,
}));

const style: RasterStyle = {
  schema_version: 'womap.raster-style/v1',
  mode: 'rgb',
  bands: [1, 2, 3],
  stretch: 'percentile',
  min_values: [],
  max_values: [],
  gamma: 1,
  nodata_transparent: true,
  color_ramp: 'magma',
  class_breaks: [],
  class_colors: [],
  formula: null,
};

const raster = {
  width: 4096,
  height: 2048,
  band_count: 4,
  driver: 'GTiff',
  dtypes: ['uint16', 'uint16', 'uint16', 'uint16'],
  nodata: [null, null, null, null],
  resolution: [10, 10],
  byte_size: 64 * 1024 * 1024,
  bands: Array.from({ length: 4 }, (_, index) => ({
    index: index + 1,
    name: `B${index + 1}`,
    dtype: 'uint16',
    nodata: null,
    color_interpretation: 'undefined',
  })),
  asset_url: '/api/v1/rasters/42/asset?v=fingerprint-42',
  fingerprint: 'fingerprint-42',
};

const layer: WorkspaceLayer = {
  id: '42',
  name: '多光谱影像',
  geometryType: 'Raster',
  featureCount: 0,
  visible: true,
  locked: true,
  opacity: 1,
  color: '#4f46e5',
  fields: [],
  performance: {
    featureCount: 0,
    largeLayer: true,
    indexed: true,
    recommendedMode: 'cog-range',
  },
  source: 'backend',
  bounds: { minx: 0, miny: 0, maxx: 40960, maxy: 20480 },
  kind: 'raster',
  raster,
  rasterStyle: style,
};

const backendLayer: BackendLayerSummary = {
  id: 42,
  name: layer.name,
  kind: 'raster',
  geometry_type: 'Raster',
  feature_count: 0,
  crs: 'EPSG:3857',
  bounds: layer.bounds!,
  visible: true,
  locked: true,
  opacity: 1,
  source_type: 'raster',
  fields: [],
  style: { raster: style },
  performance: {
    feature_count: 0,
    large_layer: true,
    indexed: true,
    recommended_mode: 'cog-range',
  },
  provenance: {
    source_id: 'local-1',
    dataset_id: 'raster-42',
    format: 'tif',
    container: 'imagery',
    relative_path: 'imagery/multispectral.tif',
    layer_name: layer.name,
    fingerprint: raster.fingerprint,
  },
  raster,
};

const derivedJob: ImportJob = {
  id: 'raster-process-1',
  job_type: 'raster-process',
  status: 'queued',
  progress: 0,
  message: '任务已进入队列。',
  detail: {
    kind: 'raster-process',
    stage: 'queued',
    operation: 'derive',
    source_id: null,
    dataset_id: 'raster-42',
    layer_id: 42,
    dataset_name: layer.name,
    processed_bytes: 0,
    total_bytes: raster.byte_size,
    processed_blocks: 0,
    total_blocks: 32,
    warnings: [],
    error: null,
  },
  result: {},
};

afterEach(() => {
  cleanup();
  useJobsStore.getState().reset();
  useWorkspaceStore.getState().reset();
  vi.clearAllMocks();
});

describe('RasterInspector', () => {
  it('loads the histogram, saves style, handles pixel events, and queues a derived raster', async () => {
    apiMocks.getRasterHistogram.mockResolvedValue({
      layer_id: 42,
      band: 1,
      bins: [2, 5, 3],
      minimum: 10,
      maximum: 220,
      sample_count: 10,
      percentiles: { p2: 12, p98: 210 },
    });
    apiMocks.updateRasterStyle.mockResolvedValue(backendLayer);
    apiMocks.deriveRaster.mockResolvedValue(derivedJob);

    render(<RasterInspector layer={layer} />);

    expect(await screen.findByText('10.00 — 220.00 · 10 样本')).toBeInTheDocument();
    expect(apiMocks.getRasterHistogram).toHaveBeenCalledWith(42, 1);

    fireEvent.click(screen.getByRole('button', { name: '应用渲染' }));
    await waitFor(() => expect(apiMocks.updateRasterStyle).toHaveBeenCalledWith(42, style));
    expect(useWorkspaceStore.getState().notice?.title).toBe('栅格样式已保存');

    window.dispatchEvent(new CustomEvent('womap:raster-pixel-picked', {
      detail: { layer_id: 42, x: 12608500, y: 2644100, crs: 'EPSG:3857', values: [0.1, null, 0.3], nodata: false },
    }));
    expect(await screen.findByText('0.100 · — · 0.300')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '生成派生层' }));
    await waitFor(() => expect(apiMocks.deriveRaster).toHaveBeenCalled());
    expect(apiMocks.deriveRaster.mock.calls[0][0]).toBe(42);
    expect(apiMocks.deriveRaster.mock.calls[0][1]).toBe('多光谱影像 · 派生指数');
    expect(apiMocks.deriveRaster.mock.calls[0][2]).toMatchObject({ kind: 'binary', operator: '/' });
    expect(useJobsStore.getState().jobs[0]).toEqual(derivedJob);
  });

  it('persists a parsed formula for immediate WebGL preview', async () => {
    const formulaLayer: WorkspaceLayer = {
      ...layer,
      rasterStyle: { ...style, mode: 'formula', formula: null },
    };
    apiMocks.getRasterHistogram.mockResolvedValue({
      layer_id: 42,
      band: 1,
      bins: [1],
      edges: [0, 1],
      minimum: 0,
      maximum: 1,
      sample_count: 1,
      percentiles: { p2: 0, p50: 0.5, p98: 1 },
    });
    apiMocks.updateRasterStyle.mockResolvedValue(backendLayer);

    render(<RasterInspector layer={formulaLayer} />);
    fireEvent.click(screen.getByRole('button', { name: '应用渲染' }));

    await waitFor(() => expect(apiMocks.updateRasterStyle).toHaveBeenCalled());
    expect(apiMocks.updateRasterStyle.mock.calls[0][1]).toMatchObject({
      mode: 'formula',
      formula: { kind: 'binary', operator: '/' },
    });
  });
});
