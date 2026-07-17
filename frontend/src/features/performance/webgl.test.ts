import { describe, expect, it, vi } from 'vitest';

import { detectWebGLCapabilities } from './webgl';

function contextWithRenderer(extensionAvailable = true) {
  const extension = extensionAvailable
    ? { UNMASKED_VENDOR_WEBGL: 100, UNMASKED_RENDERER_WEBGL: 101 }
    : null;
  return {
    getExtension: vi.fn(() => extension),
    getParameter: vi.fn((parameter: number) =>
      parameter === 100 ? 'Example Vendor' : 'Example GPU Renderer',
    ),
  } as unknown as WebGLRenderingContext;
}

describe('detectWebGLCapabilities', () => {
  it('prefers WebGL 2 and reports an allowlisted renderer', () => {
    const context = contextWithRenderer();
    const factory = vi.fn((version: 1 | 2) => (version === 2 ? context : null));

    const result = detectWebGLCapabilities(factory);

    expect(factory).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      status: 'available',
      version: 2,
      rendererStatus: 'available',
      vendor: 'Example Vendor',
      renderer: 'Example GPU Renderer',
    });
  });

  it('treats privacy-restricted renderer data as a supported state', () => {
    const context = contextWithRenderer(false);

    const result = detectWebGLCapabilities(() => context);

    expect(result.status).toBe('available');
    expect(result.rendererStatus).toBe('restricted');
    expect(result.renderer).toBeNull();
  });

  it('falls back to WebGL 1 and then to unavailable', () => {
    const context = contextWithRenderer();
    expect(detectWebGLCapabilities((version) => (version === 1 ? context : null)).version).toBe(1);
    expect(detectWebGLCapabilities(() => null).status).toBe('unavailable');
    expect(
      detectWebGLCapabilities(() => {
        throw new Error('driver probe failed');
      }).status,
    ).toBe('unavailable');
  });
});
