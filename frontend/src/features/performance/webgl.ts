import type { BrowserWebGLCapability } from '../../types/performance';

type WebGLContext = WebGLRenderingContext | WebGL2RenderingContext;
export type WebGLContextFactory = (version: 1 | 2) => WebGLContext | null;

const unavailableCapability: BrowserWebGLCapability = {
  status: 'unavailable',
  version: null,
  rendererStatus: 'unknown',
  vendor: null,
  renderer: null,
};

function defaultContextFactory(version: 1 | 2): WebGLContext | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  const contextName = version === 2 ? 'webgl2' : 'webgl';
  return canvas.getContext(contextName, {
    antialias: false,
    depth: false,
    failIfMajorPerformanceCaveat: true,
    powerPreference: 'high-performance',
    preserveDrawingBuffer: false,
  }) as WebGLContext | null;
}

function safeRendererText(value: unknown) {
  if (typeof value !== 'string') return null;
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized || /(?:[A-Za-z]:\\|\/(?:home|users?|var|tmp)\/)/i.test(normalized)) return null;
  return normalized.slice(0, 160);
}

export function detectWebGLCapabilities(
  contextFactory: WebGLContextFactory = defaultContextFactory,
): BrowserWebGLCapability {
  let context: WebGLContext | null = null;
  let version: 1 | 2 | null = null;
  try {
    context = contextFactory(2);
    version = context ? 2 : null;
    if (!context) {
      context = contextFactory(1);
      version = context ? 1 : null;
    }
  } catch {
    return unavailableCapability;
  }
  if (!context || version === null) return unavailableCapability;

  const extension = context.getExtension('WEBGL_debug_renderer_info');
  if (!extension) {
    return {
      status: 'available',
      version,
      rendererStatus: 'restricted',
      vendor: null,
      renderer: null,
    };
  }
  const vendor = safeRendererText(context.getParameter(extension.UNMASKED_VENDOR_WEBGL));
  const renderer = safeRendererText(context.getParameter(extension.UNMASKED_RENDERER_WEBGL));
  return {
    status: 'available',
    version,
    rendererStatus: vendor || renderer ? 'available' : 'restricted',
    vendor,
    renderer,
  };
}
