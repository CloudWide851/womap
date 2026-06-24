import { create } from 'zustand';

import type { JobState } from '../types/workspace';

interface JobsState {
  jobs: JobState[];
}

export const useJobsStore = create<JobsState>(() => ({
  jobs: [
    {
      id: 'preview-viewport',
      jobType: '视口预览',
      status: 'running',
      progress: 42,
      message: '按 bbox 查询，使用 GiST 空间索引。',
    },
    {
      id: 'feature-cache',
      jobType: '缓存',
      status: 'queued',
      progress: 0,
      message: '等待下一次地图视口变化。',
    },
  ],
}));
