import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { BackendLayerSummary, ImportJob } from '../../types/imports';
import type { RealMapFeatureDetail, SpatialAnalysisResult } from '../../types/spatialAnalysis';
import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';
import { SpatialAnalysisDrawer } from './SpatialAnalysisDrawer';

const layer: BackendLayerSummary = {
  id: 7,
  name: '宗地面',
  kind: 'vector',
  geometry_type: 'Polygon',
  feature_count: 3,
  crs: 'EPSG:3857',
  bounds: {},
  visible: true,
  locked: false,
  opacity: 1,
  source_type: 'gdb',
  fields: [],
  style: {},
  performance: {
    feature_count: 3,
    large_layer: false,
    indexed: true,
    recommended_mode: 'bbox',
  },
  provenance: {
    source_id: 'source-a',
    dataset_id: 'dataset-a',
    format: 'gdb',
    container: 'survey.gdb',
    relative_path: 'survey.gdb/宗地面',
    layer_name: '宗地面',
    fingerprint: 'fingerprint-a',
  },
  raster: null,
};

const target: RealMapFeatureDetail = {
  id: 44,
  layer_id: 7,
  source_feature_id: 'parcel-44',
  geometry: { type: 'Polygon', coordinates: [] },
  properties: { 名称: '目标宗地' },
  bbox: {},
  area: 5000,
  perimeter: 300,
  revision: 1,
  layer,
};

const doneJob: ImportJob = {
  id: 'analysis-1',
  job_type: 'spatial-analysis',
  status: 'done',
  progress: 100,
  message: '空间分析完成',
  detail: {
    kind: 'spatial-analysis',
    stage: 'done',
    workspace_id: 1,
    target_feature_id: 44,
    processed_layers: 2,
    total_layers: 2,
    matched_features: 1,
    warnings: [],
    error: null,
  },
};

const result: SpatialAnalysisResult = {
  job: doneJob,
  workspace_id: 1,
  target_layer_id: 7,
  target_feature_id: 44,
  distance: 2,
  unit: 'km',
  distance_meters: 2000,
  scope: 'visible',
  target_geometry: target.geometry,
  buffer_geometry: null,
  groups: [
    {
      key: 'gdb:source-a:survey.gdb',
      name: 'survey.gdb',
      source_type: 'gdb',
      layers: [
        {
          layer_id: 7,
          layer_name: '宗地面',
          geometry_type: 'Polygon',
          exists: true,
          hit_count: 1,
          nearest_distance_m: 12,
          direct_intersection_count: 0,
          buffer_intersection_count: 1,
          direct_area_sqm: 0,
          buffer_area_sqm: 300,
          direct_length_m: 0,
          buffer_length_m: 0,
          point_hit_count: 0,
          coverage_ratio: 0.06,
        },
        {
          layer_id: 8,
          layer_name: '无命中点',
          geometry_type: 'Point',
          exists: false,
          hit_count: 0,
          nearest_distance_m: null,
          direct_intersection_count: 0,
          buffer_intersection_count: 0,
          direct_area_sqm: 0,
          buffer_area_sqm: 0,
          direct_length_m: 0,
          buffer_length_m: 0,
          point_hit_count: 0,
          coverage_ratio: null,
        },
      ],
    },
  ],
  stale: true,
  warnings: ['宗地面数据已更新，结果可能陈旧。'],
};

afterEach(() => {
  useSpatialAnalysisStore.getState().reset();
  cleanup();
});

describe('SpatialAnalysisDrawer', () => {
  it('shows parameters, typed metrics, no-hit groups, stale warning, and an empty hit page', () => {
    useSpatialAnalysisStore.setState({
      target,
      drawerOpen: true,
      distance: 2,
      unit: 'km',
      scope: 'visible',
      job: doneJob,
      result,
      hits: [],
      hasMore: false,
      busy: false,
    });

    render(<SpatialAnalysisDrawer />);

    expect(screen.getByText('目标宗地')).toBeInTheDocument();
    expect(screen.getByText('千米')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '仅可见图层' })).toBeChecked();
    expect(screen.getByText('1 命中')).toBeInTheDocument();
    expect(screen.getByText('宗地面数据已更新，结果可能陈旧。')).toBeInTheDocument();
    expect(screen.getByText('当前范围无命中图斑')).toBeInTheDocument();

    fireEvent.click(screen.getByText('survey.gdb · 2 图层'));

    expect(screen.getAllByText('宗地面')).toHaveLength(2);
    expect(screen.getByText('300.00 m² · 0.0300 ha · 0.000300 km²')).toBeInTheDocument();
    expect(screen.getByText('6.00%')).toBeInTheDocument();
    expect(screen.getByText('无命中点')).toBeInTheDocument();
    expect(screen.getByText('不存在')).toBeInTheDocument();
    expect(screen.getByText('点命中')).toBeInTheDocument();
  });
});
