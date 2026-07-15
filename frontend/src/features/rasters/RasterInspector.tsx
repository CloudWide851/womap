import { Button, Input, Select, Slider, Switch, Tag, Tooltip } from 'antd';
import {
  BarChart3,
  Download,
  Droplets,
  Focus,
  FunctionSquare,
  Layers3,
  Save,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  deriveRaster,
  exportRasters,
  getRasterHistogram,
  updateRasterStyle,
} from '../../services/api';
import { useJobsStore } from '../../stores/useJobsStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { RasterPixel, RasterStyle } from '../../types/imports';
import type { WorkspaceLayer } from '../../types/workspace';
import { normalizeBackendLayer } from '../layers/backendLayer';
import {
  formatRasterFormula,
  parseRasterFormula,
  supportsRasterWebGLPreview,
} from './formulaParser';

interface RasterInspectorProps {
  layer: WorkspaceLayer;
}

function formatBytes(value: number) {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function Histogram({ values }: { values: number[] }) {
  const maximum = Math.max(1, ...values);
  const bars = values.length > 48
    ? Array.from({ length: 48 }, (_, index) =>
        values
          .slice(Math.floor((index * values.length) / 48), Math.floor(((index + 1) * values.length) / 48))
          .reduce((sum, value) => sum + value, 0),
      )
    : values;
  return (
    <svg className="raster-histogram" viewBox="0 0 240 76" role="img" aria-label="当前波段采样直方图">
      {bars.map((value, index) => {
        const height = (value / maximum) * 68;
        return (
          <rect
            key={`${index}-${value}`}
            x={(index * 240) / Math.max(1, bars.length)}
            y={72 - height}
            width={Math.max(1, 240 / Math.max(1, bars.length) - 1)}
            height={height}
            rx="1"
          />
        );
      })}
    </svg>
  );
}

export function RasterInspector({ layer }: RasterInspectorProps) {
  const metadata = layer.raster;
  const [style, setStyle] = useState<RasterStyle | null>(layer.rasterStyle ?? null);
  const [formulaText, setFormulaText] = useState(
    layer.rasterStyle?.formula
      ? formatRasterFormula(layer.rasterStyle.formula)
      : '(B4-B3)/(B4+B3)',
  );
  const [derivedName, setDerivedName] = useState(`${layer.name} · 派生指数`);
  const [histogram, setHistogram] = useState<number[]>([]);
  const [histogramLabel, setHistogramLabel] = useState('尚未采样');
  const [pixel, setPixel] = useState<RasterPixel | null>(null);
  const [busy, setBusy] = useState(false);
  const showNotice = useWorkspaceStore((state) => state.showNotice);
  const upsertBackendLayer = useWorkspaceStore((state) => state.upsertBackendLayer);
  const upsertJob = useJobsStore((state) => state.upsert);
  const bandOptions = useMemo(
    () => metadata?.bands.map((band) => ({ value: band.index, label: `${band.index} · ${band.name}` })) ?? [],
    [metadata?.bands],
  );
  const histogramBand = style?.bands[0] ?? 1;

  useEffect(() => {
    setStyle(layer.rasterStyle ?? null);
    setDerivedName(`${layer.name} · 派生指数`);
    if (layer.rasterStyle?.formula) {
      setFormulaText(formatRasterFormula(layer.rasterStyle.formula));
    }
  }, [layer.id, layer.name, layer.rasterStyle]);

  useEffect(() => {
    if (!metadata || !style) return;
    let active = true;
    setHistogramLabel('正在按概览采样…');
    void getRasterHistogram(Number(layer.id), histogramBand)
      .then((response) => {
        if (!active) return;
        setHistogram(response.bins);
        setHistogramLabel(
          response.minimum === null
            ? '当前波段没有有效像元'
            : `${response.minimum.toFixed(2)} — ${response.maximum?.toFixed(2)} · ${response.sample_count.toLocaleString('zh-CN')} 样本`,
        );
      })
      .catch(() => active && setHistogramLabel('直方图暂不可用'));
    return () => {
      active = false;
    };
  }, [histogramBand, layer.id, metadata, style]);

  useEffect(() => {
    const handlePixel = (event: Event) => {
      const detail = (event as CustomEvent<RasterPixel>).detail;
      if (detail?.layer_id === Number(layer.id)) setPixel(detail);
    };
    window.addEventListener('womap:raster-pixel-picked', handlePixel);
    return () => window.removeEventListener('womap:raster-pixel-picked', handlePixel);
  }, [layer.id]);

  if (!metadata || !style) return null;

  const updateLocal = (patch: Partial<RasterStyle>) => setStyle((current) => current && { ...current, ...patch });
  const save = async () => {
    let nextStyle = style;
    if (style.mode === 'formula') {
      try {
        const formula = parseRasterFormula(formulaText);
        if (!supportsRasterWebGLPreview(formula)) {
          showNotice({
            tone: 'warning',
            title: '当前公式不能即时预览',
            detail: 'OpenLayers WebGL 不支持 log；仍可生成派生 COG。',
          });
          return;
        }
        nextStyle = { ...style, formula };
      } catch (error) {
        showNotice({
          tone: 'warning',
          title: '波段公式无效',
          detail: error instanceof Error ? error.message : '公式解析失败。',
        });
        return;
      }
    }
    setBusy(true);
    try {
      const updated = await updateRasterStyle(Number(layer.id), nextStyle);
      setStyle(nextStyle);
      upsertBackendLayer(normalizeBackendLayer(updated));
      showNotice({ tone: 'success', title: '栅格样式已保存', detail: '地图已使用新的波段与拉伸配置。' });
    } catch (error) {
      showNotice({
        tone: 'warning',
        title: '栅格样式保存失败',
        detail: error instanceof Error ? error.message : '请检查样式参数。',
      });
    } finally {
      setBusy(false);
    }
  };

  const materialize = async () => {
    try {
      const formula = parseRasterFormula(formulaText);
      const job = await deriveRaster(Number(layer.id), derivedName.trim() || `${layer.name} · 派生`, formula, {
        ...style,
        mode: 'formula',
        formula,
      });
      upsertJob(job);
      showNotice({ tone: 'info', title: '派生栅格已进入队列', detail: '后端将按 COG 数据块计算，不会一次载入整幅影像。' });
    } catch (error) {
      showNotice({ tone: 'warning', title: '波段公式无效', detail: error instanceof Error ? error.message : '公式解析失败。' });
    }
  };

  return (
    <section className="raster-inspector" aria-label={`${layer.name} 栅格分析`}>
      <div className="raster-summary-grid">
        <span><strong>{metadata.width.toLocaleString('zh-CN')} × {metadata.height.toLocaleString('zh-CN')}</strong><small>像素尺寸</small></span>
        <span><strong>{metadata.band_count}</strong><small>波段</small></span>
        <span><strong>{formatBytes(metadata.byte_size)}</strong><small>托管 COG</small></span>
      </div>

      <div className="raster-section-heading"><Layers3 size={15} /><span>渲染</span><Tag>{style.mode.toUpperCase()}</Tag></div>
      <div className="raster-control-grid">
        <label>
          <span>模式</span>
          <Select
            value={style.mode}
            options={[
              { value: 'rgb', label: 'RGB 合成' },
              { value: 'grayscale', label: '单波段灰度' },
              { value: 'classified', label: '分级色带' },
              { value: 'formula', label: '公式预览' },
            ]}
            onChange={(mode) => updateLocal({ mode })}
            classNames={{ popup: { root: 'womap-select-popup' } }}
          />
        </label>
        <label>
          <span>波段</span>
          <Select
            mode={style.mode === 'rgb' ? 'multiple' : undefined}
            maxCount={style.mode === 'rgb' ? 3 : undefined}
            value={style.mode === 'rgb' ? style.bands.slice(0, 3) : style.bands[0]}
            options={bandOptions}
            onChange={(value) => updateLocal({ bands: Array.isArray(value) ? value : [value] })}
            classNames={{ popup: { root: 'womap-select-popup' } }}
          />
        </label>
        <label>
          <span>拉伸</span>
          <Select
            value={style.stretch}
            options={[
              { value: 'percentile', label: '2–98 百分位' },
              { value: 'minmax', label: '最小–最大值' },
              { value: 'none', label: '原始值' },
            ]}
            onChange={(stretch) => updateLocal({ stretch })}
            classNames={{ popup: { root: 'womap-select-popup' } }}
          />
        </label>
        {style.mode === 'classified' && (
          <label>
            <span>色带</span>
            <Select
              value={style.color_ramp}
              options={['magma', 'viridis', 'plasma', 'cividis'].map((value) => ({ value, label: value }))}
              onChange={(color_ramp) => updateLocal({ color_ramp })}
              classNames={{ popup: { root: 'womap-select-popup' } }}
            />
          </label>
        )}
      </div>
      <label className="raster-slider-row">
        <span>Gamma {style.gamma.toFixed(2)}</span>
        <Slider min={0.1} max={3} step={0.05} value={style.gamma} onChange={(gamma) => updateLocal({ gamma })} />
      </label>
      <div className="raster-switch-row">
        <span><Droplets size={14} /> NoData 透明</span>
        <Switch size="small" checked={style.nodata_transparent} onChange={(nodata_transparent) => updateLocal({ nodata_transparent })} />
      </div>
      <Button block type="primary" icon={<Save size={14} />} loading={busy} onClick={() => void save()}>
        应用渲染
      </Button>

      <div className="raster-section-heading"><BarChart3 size={15} /><span>分布</span></div>
      <Histogram values={histogram} />
      <p className="raster-histogram-caption">{histogramLabel}</p>

      <div className="raster-section-heading"><Focus size={15} /><span>像元</span></div>
      <Button
        block
        icon={<Focus size={14} />}
        onClick={() => window.dispatchEvent(new CustomEvent('womap:start-raster-pixel-pick', { detail: { layerId: Number(layer.id) } }))}
      >
        在地图拾取像元
      </Button>
      {pixel && (
        <div className="raster-pixel-result">
          <span>{pixel.x.toFixed(2)}, {pixel.y.toFixed(2)}</span>
          <strong>{pixel.nodata ? 'NoData' : pixel.values.map((value) => value === null ? '—' : Number(value).toFixed(3)).join(' · ')}</strong>
        </div>
      )}

      <div className="raster-section-heading"><FunctionSquare size={15} /><span>波段公式</span></div>
      <Input value={formulaText} onChange={(event) => setFormulaText(event.target.value)} aria-label="波段公式" />
      <p className="raster-formula-hint">即时预览支持 abs、sqrt、min、max、clamp；log 仅生成派生 COG。</p>
      <Input value={derivedName} onChange={(event) => setDerivedName(event.target.value)} aria-label="派生栅格名称" />
      <div className="raster-action-row">
        <Tooltip title="公式只解析为受限 AST，不执行脚本">
          <Button icon={<Sparkles size={14} />} onClick={() => void materialize()}>生成派生层</Button>
        </Tooltip>
        <Button
          icon={<Download size={14} />}
          onClick={() => void exportRasters([Number(layer.id)]).then((job) => {
            upsertJob(job);
            showNotice({ tone: 'info', title: 'COG 导出已进入队列', detail: '完成后可在任务面板下载。' });
          })}
        >
          导出 COG
        </Button>
      </div>
    </section>
  );
}
