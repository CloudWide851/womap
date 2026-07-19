export type CapabilityStatus = 'available' | 'unavailable' | 'restricted' | 'unknown';
export type SystemPowerMode = 'balanced' | 'performance' | 'power_saver' | 'unknown';
export type GpuGateStatus =
  | 'disabled'
  | 'unavailable'
  | 'missing'
  | 'rejected'
  | 'passed'
  | 'fallback';

export interface PerformanceCapabilitySummary {
  profile: {
    requested: 'auto' | 'low' | 'balanced' | 'high';
    resolved: 'low' | 'balanced' | 'high';
    enforcement: 'active';
    gdalThreads: number;
    gdalCacheMiB: number;
    gdalDatasetPoolSize: number;
    formulaWindowBudgetMiB: number;
    scratchReserveGiB: number;
    databasePoolSize: number;
    databaseMaxOverflow: number;
  };
  browser: {
    vectorLimit: number;
    bboxDebounceMs: number;
    webglTextureCache: number;
    geotiffCacheSize: number;
    incrementalSourceUpdates: boolean;
    browseSimplifyMaxTolerance: number;
  };
  cache: {
    enabled: boolean;
    ttlSeconds: number;
    maxEntryKiB: number;
  };
  runtimeMode: 'development' | 'production';
  cpuLogicalCores: number;
  totalMemoryBytes: number | null;
  availableMemoryBytes: number | null;
  power: {
    status: CapabilityStatus;
    mode: SystemPowerMode;
  };
  gpu: {
    count: number;
    label: string;
    cupyStatus: CapabilityStatus;
    executionEnabled: boolean;
    executionReason: string;
    effectiveBackend: 'cpu' | 'cupy';
    gateStatus: GpuGateStatus;
    benchmarkSpeedup: number | null;
  };
  queue: {
    status: CapabilityStatus;
    queued: number | null;
    running: number | null;
  };
  recommendations: PerformanceRecommendationSummary[];
  warning: string | null;
}

export interface PerformanceRecommendationSummary {
  code: string;
  severity: 'info' | 'warning';
  scope: 'process' | 'user' | 'system';
  adminRequired: boolean;
  evidence: string;
  expectedEffect: string;
  action: string;
  restoreAction: string | null;
}

export interface BrowserWebGLCapability {
  status: 'checking' | 'available' | 'unavailable';
  version: 1 | 2 | null;
  rendererStatus: 'available' | 'restricted' | 'unknown';
  vendor: string | null;
  renderer: string | null;
}
