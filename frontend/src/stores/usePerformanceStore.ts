import { create } from 'zustand';

import { getPerformanceCapabilities } from '../services/api';
import type { PerformanceCapabilitySummary } from '../types/performance';

interface PerformanceState {
  capabilities: PerformanceCapabilitySummary | null;
  error: string | null;
  loading: boolean;
  load: (force?: boolean) => Promise<void>;
  reset: () => void;
}

let pending: Promise<void> | null = null;
let activeController: AbortController | null = null;

export const usePerformanceStore = create<PerformanceState>((set, get) => ({
  capabilities: null,
  error: null,
  loading: false,
  load: async (force = false) => {
    if (!force && get().capabilities) return;
    if (pending) return pending;
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    set({ loading: true });
    pending = getPerformanceCapabilities(controller.signal)
      .then((capabilities) => {
        if (!controller.signal.aborted) set({ capabilities, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        set({ error: error instanceof Error ? error.message : '性能能力加载失败' });
      })
      .finally(() => {
        if (activeController === controller) activeController = null;
        pending = null;
        set({ loading: false });
      });
    return pending;
  },
  reset: () => {
    activeController?.abort();
    activeController = null;
    pending = null;
    set({ capabilities: null, error: null, loading: false });
  },
}));
