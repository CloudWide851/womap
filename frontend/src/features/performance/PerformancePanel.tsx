import { Tooltip } from 'antd';
import {
  BatteryCharging,
  Cpu,
  DatabaseZap,
  Gauge,
  HardDrive,
  Layers3,
  MonitorCog,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { memo, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { usePerformanceStore } from '../../stores/usePerformanceStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { BrowserWebGLCapability, PerformanceCapabilitySummary } from '../../types/performance';
import type { LayerPerformanceState } from '../../types/workspace';
import { detectWebGLCapabilities } from './webgl';

interface PerformanceMetricProps {
  icon: ReactNode;
  label: string;
  value: string | number;
}

const PerformanceMetric = memo(function PerformanceMetric({
  icon,
  label,
  value,
}: PerformanceMetricProps) {
  return (
    <Tooltip title={label}>
      <div className="performance-metric" aria-label={`${label} ${value}`}>
        {icon}
        <span>{value}</span>
      </div>
    </Tooltip>
  );
});

function getStrategyLabel(strategy?: LayerPerformanceState['recommendedMode']) {
  if (strategy === 'tile') {
    return '瓦片';
  }
  if (strategy === 'table') {
    return '分页';
  }
  return 'bbox';
}

function profileLabel(profile?: PerformanceCapabilitySummary['profile']['resolved']) {
  if (profile === 'high') return '高性能';
  if (profile === 'balanced') return '均衡';
  if (profile === 'low') return '低配';
  return '检查中';
}

function webglLabel(capability: BrowserWebGLCapability) {
  if (capability.status === 'checking') return '检查中';
  if (capability.status === 'unavailable') return '不可用';
  return capability.version === 2 ? 'WebGL 2' : 'WebGL 1';
}

function memoryLabel(bytes: number | null | undefined) {
  return bytes == null ? '未知' : `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
}

function nativeComputeLabel(gpu?: PerformanceCapabilitySummary['gpu']) {
  if (!gpu) return '检查中';
  if (gpu.gateStatus === 'passed' && gpu.effectiveBackend === 'cupy') return 'GPU 已启用';
  if (gpu.gateStatus === 'fallback') return 'GPU 失败后 CPU 回退';
  if (gpu.gateStatus === 'rejected') return '基准未通过';
  if (gpu.gateStatus === 'missing') return '本机基准缺失';
  if (gpu.gateStatus === 'unavailable') {
    return gpu.cupyStatus === 'unavailable' ? 'CuPy 未安装' : 'GPU 环境不可用';
  }
  return 'CPU 配置';
}

function powerLabel(power?: PerformanceCapabilitySummary['power']) {
  if (!power || power.status !== 'available') return '未获取';
  if (power.mode === 'performance') return '高性能';
  if (power.mode === 'balanced') return '均衡';
  if (power.mode === 'power_saver') return '节能';
  return '未知';
}

export function PerformancePanel() {
  const layers = useWorkspaceStore((state) => state.layers);
  const selectedLayerId = useWorkspaceStore((state) => state.selectedLayerId);
  const layer = layers.find((item) => item.id === selectedLayerId);
  const capabilities = usePerformanceStore((state) => state.capabilities);
  const capabilityError = usePerformanceStore((state) => state.error);
  const loadCapabilities = usePerformanceStore((state) => state.load);
  const [webgl, setWebgl] = useState<BrowserWebGLCapability>({
    status: 'checking',
    version: null,
    rendererStatus: 'unknown',
    vendor: null,
    renderer: null,
  });

  useEffect(() => {
    setWebgl(detectWebGLCapabilities());
    void loadCapabilities();
  }, [loadCapabilities]);

  const capabilityWarning =
    capabilityError ??
    capabilities?.warning ??
    (webgl.status === 'unavailable' ? '浏览器 WebGL 不可用，地图将无法使用 GPU 渲染。' : null);
  const rendererLabel =
    webgl.rendererStatus === 'available'
      ? (webgl.renderer ?? webgl.vendor ?? '已开放')
      : webgl.rendererStatus === 'restricted'
        ? '隐私限制'
        : '未知';

  return (
    <section className="map-toolbox-section map-toolbox-performance" aria-label="性能内容">
      <div className="section-title">
        <Gauge size={16} />
        <span>性能</span>
      </div>
      <div className="performance-grid">
        <PerformanceMetric
          icon={<Layers3 size={16} aria-hidden="true" />}
          label="当前要素"
          value={layer?.performance.featureCount ?? 0}
        />
        <PerformanceMetric
          icon={<DatabaseZap size={16} aria-hidden="true" />}
          label="加载策略"
          value={getStrategyLabel(layer?.performance.recommendedMode)}
        />
        <PerformanceMetric
          icon={<HardDrive size={16} aria-hidden="true" />}
          label="资源档位"
          value={profileLabel(capabilities?.profile.resolved)}
        />
        <PerformanceMetric
          icon={<MonitorCog size={16} aria-hidden="true" />}
          label="地图 GPU"
          value={webglLabel(webgl)}
        />
      </div>
      <div className="performance-diagnostics" aria-label="性能诊断摘要">
        <div>
          <Cpu size={14} aria-hidden="true" />
          <span>CPU / 可用内存</span>
          <strong>
            {capabilities
              ? `${capabilities.cpuLogicalCores} 线程 / ${memoryLabel(capabilities.availableMemoryBytes)}`
              : '检查中'}
          </strong>
        </div>
        <div>
          <MonitorCog size={14} aria-hidden="true" />
          <span>WebGL 渲染器</span>
          <strong title={rendererLabel}>{rendererLabel}</strong>
        </div>
        <div>
          <Gauge size={14} aria-hidden="true" />
          <span>原生计算</span>
          <strong>{nativeComputeLabel(capabilities?.gpu)}</strong>
        </div>
        <div>
          <DatabaseZap size={14} aria-hidden="true" />
          <span>GDAL 生效预算</span>
          <strong>
            {capabilities
              ? `${capabilities.profile.gdalThreads} 线程 / ${capabilities.profile.gdalCacheMiB} MiB`
              : '检查中'}
          </strong>
        </div>
        <div>
          <BatteryCharging size={14} aria-hidden="true" />
          <span>系统电源</span>
          <strong>{powerLabel(capabilities?.power)}</strong>
        </div>
      </div>
      {capabilities && capabilities.recommendations.length > 0 ? (
        <div className="performance-recommendations" aria-label="系统性能建议">
          {capabilities.recommendations.map((recommendation) => (
            <details key={recommendation.code} open={recommendation.severity === 'warning'}>
              <summary>
                {recommendation.severity === 'warning' ? (
                  <TriangleAlert size={13} aria-hidden="true" />
                ) : (
                  <ShieldCheck size={13} aria-hidden="true" />
                )}
                <span>{recommendation.action}</span>
              </summary>
              <dl>
                <div>
                  <dt>依据</dt>
                  <dd>{recommendation.evidence}</dd>
                </div>
                <div>
                  <dt>影响</dt>
                  <dd>{recommendation.expectedEffect}</dd>
                </div>
                <div>
                  <dt>权限</dt>
                  <dd>{recommendation.adminRequired ? '需要管理员权限' : '无需管理员权限'}</dd>
                </div>
                {recommendation.restoreAction ? (
                  <div>
                    <dt>恢复</dt>
                    <dd>{recommendation.restoreAction}</dd>
                  </div>
                ) : null}
              </dl>
            </details>
          ))}
        </div>
      ) : null}
      <div
        className={`performance-hint ${layer?.performance.warning || capabilityWarning ? 'is-warning' : 'is-ok'}`}
        role="status"
      >
        {layer?.performance.warning || capabilityWarning ? (
          <TriangleAlert size={16} aria-hidden="true" />
        ) : (
          <ShieldCheck size={16} aria-hidden="true" />
        )}
        <span>
          {layer?.performance.warning ??
            capabilityWarning ??
            'WebGL 负责地图渲染；原生 GPU 计算仍受正确性与 1.5× 端到端门槛保护。'}
        </span>
      </div>
    </section>
  );
}
