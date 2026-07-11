import { create } from 'zustand';

import { getJobs } from '../services/api';
import type { ImportJob } from '../types/imports';

interface JobsState {
  jobs: ImportJob[];
  loading: boolean;
  refresh: () => Promise<void>;
  upsert: (job: ImportJob) => void;
  reset: () => void;
}

export const useJobsStore = create<JobsState>((set) => ({
  jobs: [],
  loading: false,
  refresh: async () => {
    set({ loading: true });
    try {
      const jobs = await getJobs();
      if (Array.isArray(jobs)) set({ jobs });
    } catch {
      // Keep the last known task state while the local API is unavailable.
    } finally {
      set({ loading: false });
    }
  },
  upsert: (job) =>
    set((state) => ({ jobs: [job, ...state.jobs.filter((item) => item.id !== job.id)] })),
  reset: () => set({ jobs: [], loading: false }),
}));
