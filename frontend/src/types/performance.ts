export type CapabilityStatus = 'available' | 'unavailable' | 'restricted' | 'unknown';

export interface PerformanceCapabilitySummary {
  profile: {
    requested: 'auto' | 'low' | 'balanced' | 'high';
    resolved: 'low' | 'balanced' | 'high';
    enforcement: 'diagnostic';
    gdalThreads: number;
    gdalCacheMiB: number;
  };
  runtimeMode: 'development' | 'production';
  cpuLogicalCores: number;
  totalMemoryBytes: number | null;
  availableMemoryBytes: number | null;
  gpu: {
    count: number;
    label: string;
    cupyStatus: CapabilityStatus;
    executionEnabled: boolean;
    executionReason: string;
  };
  queue: {
    status: CapabilityStatus;
    queued: number | null;
    running: number | null;
  };
  warning: string | null;
}

export interface BrowserWebGLCapability {
  status: 'checking' | 'available' | 'unavailable';
  version: 1 | 2 | null;
  rendererStatus: 'available' | 'restricted' | 'unknown';
  vendor: string | null;
  renderer: string | null;
}
