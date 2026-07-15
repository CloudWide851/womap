import { Button, Collapse, Drawer, Empty, InputNumber, Progress, Radio, Select, Tag } from 'antd';
import { Download, OctagonX, Play, ScanSearch } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';

function formatDistance(value: number | null) {
  if (value === null) return '--';
  return value >= 1000 ? `${(value / 1000).toFixed(3)} km` : `${value.toFixed(2)} m`;
}

function formatArea(value: number) {
  return `${value.toFixed(2)} m² · ${(value / 10_000).toFixed(4)} ha · ${(value / 1_000_000).toFixed(6)} km²`;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function SpatialAnalysisDrawer() {
  const target = useSpatialAnalysisStore((state) => state.target);
  const open = useSpatialAnalysisStore((state) => state.drawerOpen);
  const distance = useSpatialAnalysisStore((state) => state.distance);
  const unit = useSpatialAnalysisStore((state) => state.unit);
  const scope = useSpatialAnalysisStore((state) => state.scope);
  const job = useSpatialAnalysisStore((state) => state.job);
  const result = useSpatialAnalysisStore((state) => state.result);
  const hits = useSpatialAnalysisStore((state) => state.hits);
  const hasMore = useSpatialAnalysisStore((state) => state.hasMore);
  const busy = useSpatialAnalysisStore((state) => state.busy);
  const error = useSpatialAnalysisStore((state) => state.error);
  const setOpen = useSpatialAnalysisStore((state) => state.setDrawerOpen);
  const setDistance = useSpatialAnalysisStore((state) => state.setDistance);
  const setUnit = useSpatialAnalysisStore((state) => state.setUnit);
  const setScope = useSpatialAnalysisStore((state) => state.setScope);
  const run = useSpatialAnalysisStore((state) => state.run);
  const cancel = useSpatialAnalysisStore((state) => state.cancel);
  const loadMore = useSpatialAnalysisStore((state) => state.loadMore);
  const exportResult = useSpatialAnalysisStore((state) => state.exportResult);
  const [exporting, setExporting] = useState(false);
  const targetLabel = useMemo(
    () =>
      target
        ? String(
            target.properties.name ??
              target.properties['名称'] ??
              target.properties['编号'] ??
              `图斑 ${target.id}`,
          )
        : `图斑 ${result?.target_feature_id ?? '--'}`,
    [result?.target_feature_id, target],
  );
  const running = job?.status === 'queued' || job?.status === 'running';

  const handleExport = async () => {
    setExporting(true);
    try {
      const archive = await exportResult();
      saveBlob(archive.blob, archive.filename);
    } finally {
      setExporting(false);
    }
  };

  return (
    <Drawer
      className="analysis-drawer"
      title={<span className="analysis-drawer-title"><ScanSearch size={17} /> 空间分析</span>}
      open={open}
      width={560}
      destroyOnHidden={false}
      onClose={() => setOpen(false)}
    >
      <section className="analysis-target-card">
        <span>分析目标</span>
        <strong>{targetLabel}</strong>
        <small>{target?.layer.name ?? `图层 ${result?.target_layer_id ?? '--'}`}</small>
      </section>

      <div className="analysis-parameter-grid">
        <label>
          范围
          <InputNumber
            min={0.001}
            max={1_000_000}
            precision={3}
            value={distance}
            onChange={(value) => setDistance(Number(value ?? 0))}
          />
        </label>
        <label>
          单位
          <Select
            value={unit}
            options={[
              { value: 'm', label: '米' },
              { value: 'km', label: '千米' },
              { value: 'ft', label: '英尺' },
              { value: 'mi', label: '英里' },
            ]}
            onChange={setUnit}
            classNames={{ popup: { root: 'womap-select-popup' } }}
          />
        </label>
      </div>
      <Radio.Group
        className="analysis-scope"
        value={scope}
        onChange={(event) => setScope(event.target.value)}
        options={[
          { value: 'all', label: '工作空间全部参与图层' },
          { value: 'visible', label: '仅可见图层' },
        ]}
      />
      <div className="analysis-actions">
        <Button
          type="primary"
          icon={<Play size={15} />}
          loading={busy && !running}
          disabled={!target || distance <= 0 || running}
          onClick={() => void run()}
        >
          开始分析
        </Button>
        {running && (
          <Button icon={<OctagonX size={15} />} danger onClick={() => void cancel()}>
            取消
          </Button>
        )}
        <Button
          icon={<Download size={15} />}
          disabled={job?.status !== 'done'}
          loading={exporting}
          onClick={() => void handleExport()}
        >
          导出结果
        </Button>
      </div>

      {job && (
        <section className="analysis-progress">
          <div><strong>{job.message}</strong><span>{job.detail.stage}</span></div>
          <Progress percent={job.progress} status={job.status === 'failed' ? 'exception' : undefined} />
        </section>
      )}
      {error && <div className="analysis-error" role="alert">{error}</div>}
      {result?.warnings.map((warning) => <div className="analysis-warning" key={warning}>{warning}</div>)}

      {result && (
        <section className="analysis-results">
          <div className="analysis-results-heading">
            <strong>分析汇总</strong>
            <span>{result.groups.reduce((count, group) => count + group.layers.reduce((sum, layer) => sum + layer.hit_count, 0), 0)} 命中</span>
          </div>
          <Collapse
            size="small"
            items={result.groups.map((group) => ({
              key: group.key,
              label: `${group.name} · ${group.layers.length} 图层`,
              children: (
                <div className="analysis-layer-results">
                  {group.layers.map((layer) => (
                    <article key={layer.layer_id} className={`analysis-layer-result ${layer.exists ? 'has-hit' : 'is-empty'}`}>
                      <div>
                        <strong>{layer.layer_name}</strong>
                        <Tag color={layer.exists ? 'geekblue' : 'default'}>{layer.exists ? `${layer.hit_count} 命中` : '不存在'}</Tag>
                      </div>
                      <dl>
                        <div><dt>最近距离</dt><dd>{formatDistance(layer.nearest_distance_m)}</dd></div>
                        {layer.geometry_type.includes('Polygon') && (
                          <>
                            <div><dt>直接相交</dt><dd>{formatArea(layer.direct_area_sqm)}</dd></div>
                            <div><dt>缓冲相交</dt><dd>{formatArea(layer.buffer_area_sqm)}</dd></div>
                            <div><dt>覆盖比例</dt><dd>{layer.coverage_ratio === null ? '--' : `${(layer.coverage_ratio * 100).toFixed(2)}%`}</dd></div>
                          </>
                        )}
                        {layer.geometry_type.includes('Line') && (
                          <div><dt>相交长度</dt><dd>{formatDistance(layer.buffer_length_m)}</dd></div>
                        )}
                        {layer.geometry_type.includes('Point') && (
                          <div><dt>点命中</dt><dd>{layer.point_hit_count}</dd></div>
                        )}
                      </dl>
                    </article>
                  ))}
                </div>
              ),
            }))}
          />

          <div className="analysis-hit-list">
            <strong>命中图斑</strong>
            {hits.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前范围无命中图斑" />
            ) : (
              hits.map((hit) => (
                <div key={`${hit.layer_id}-${hit.feature_id}`} className="analysis-hit-row">
                  <span>{hit.label}</span>
                  <em>{hit.layer_name}</em>
                  <small>{formatDistance(hit.distance_m)}</small>
                </div>
              ))
            )}
            {hasMore && <Button block loading={busy} onClick={() => void loadMore()}>加载更多</Button>}
          </div>
        </section>
      )}
    </Drawer>
  );
}
