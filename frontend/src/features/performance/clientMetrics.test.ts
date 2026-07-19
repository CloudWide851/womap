import { beforeEach, describe, expect, it } from 'vitest';

import {
  getClientPerformanceSummary,
  recordClientMetric,
  resetClientPerformanceMetrics,
} from './clientMetrics';

beforeEach(() => resetClientPerformanceMetrics());

describe('bounded client performance metrics', () => {
  it('keeps aggregate latency samples without request URLs or geometry', () => {
    for (let index = 0; index < 300; index += 1) {
      recordClientMetric('geojson_body_parse', index);
    }

    const summary = getClientPerformanceSummary();

    expect(summary.phases.geojson_body_parse.samples).toBe(256);
    expect(summary.phases.geojson_body_parse.p95Ms).toBeGreaterThan(0);
    expect(JSON.stringify(summary)).not.toContain('/api/');
    expect(JSON.stringify(summary)).not.toContain('coordinates');
  });
});
