type ClientMetricName =
  | 'geojson_request'
  | 'geojson_body_parse'
  | 'geojson_read_features'
  | 'geojson_source_update';

const MAX_SAMPLES = 256;
const samples = new Map<ClientMetricName, number[]>();
const raster = { requests: 0, bytes: 0, cacheReuses: 0, firstUsableBlockMs: null as number | null };

export function recordClientMetric(name: ClientMetricName, durationMs: number) {
  const values = samples.get(name) ?? [];
  values.push(Math.max(0, durationMs));
  if (values.length > MAX_SAMPLES) values.splice(0, values.length - MAX_SAMPLES);
  samples.set(name, values);
}

function percentile(values: number[], quantile: number) {
  if (values.length === 0) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.min(ordered.length - 1, Math.floor((ordered.length - 1) * quantile))];
}

export function getClientPerformanceSummary() {
  const phases = Object.fromEntries(
    Array.from(samples.entries()).map(([name, values]) => [
      name,
      {
        samples: values.length,
        p50Ms: Number(percentile(values, 0.5).toFixed(3)),
        p95Ms: Number(percentile(values, 0.95).toFixed(3)),
        maxMs: Number(Math.max(...values, 0).toFixed(3)),
      },
    ]),
  );
  return { phases, raster: { ...raster } };
}

export function observeRasterResources() {
  if (typeof PerformanceObserver === 'undefined') return () => undefined;
  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (!(entry instanceof PerformanceResourceTiming)) continue;
      if (!entry.name.includes('/api/v1/rasters/') || !entry.name.includes('/asset')) continue;
      raster.requests += 1;
      raster.bytes += Math.max(0, entry.transferSize || entry.encodedBodySize || 0);
      if (entry.transferSize === 0 && entry.decodedBodySize > 0) raster.cacheReuses += 1;
      if (raster.firstUsableBlockMs === null) raster.firstUsableBlockMs = entry.duration;
    }
  });
  try {
    observer.observe({ type: 'resource', buffered: true });
  } catch {
    observer.disconnect();
  }
  return () => observer.disconnect();
}

export function resetClientPerformanceMetrics() {
  samples.clear();
  raster.requests = 0;
  raster.bytes = 0;
  raster.cacheReuses = 0;
  raster.firstUsableBlockMs = null;
}
