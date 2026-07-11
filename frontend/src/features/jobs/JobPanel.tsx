import { Progress, Tooltip } from 'antd';
import { Activity, CheckCircle2, Clock3, LoaderCircle, PauseCircle, XCircle } from 'lucide-react';
import { memo, useEffect } from 'react';

import { useJobsStore } from '../../stores/useJobsStore';
import type { ImportJob } from '../../types/imports';

const statusLabels: Record<ImportJob['status'], string> = {
  queued: '等待中',
  running: '执行中',
  interrupted: '已中断',
  done: '已完成',
  failed: '失败',
  unknown: '未知',
};

const statusIcons = {
  queued: Clock3,
  running: LoaderCircle,
  interrupted: PauseCircle,
  done: CheckCircle2,
  failed: XCircle,
  unknown: Activity,
};

interface JobItemProps {
  job: ImportJob;
}

const JobItem = memo(function JobItem({ job }: JobItemProps) {
  const StatusIcon = statusIcons[job.status];
  return (
    <div className={`job-item is-${job.status}`}>
      <div>
        <strong>{job.job_type === 'import-sync' ? '目录同步' : '数据导入'}</strong>
        <Tooltip title={statusLabels[job.status]}>
          <span
            role="img"
            className={`status-icon is-${job.status}`}
            aria-label={statusLabels[job.status]}
          >
            <StatusIcon size={15} aria-hidden="true" />
          </span>
        </Tooltip>
      </div>
      <Progress
        className="job-progress"
        percent={job.progress}
        size="small"
        showInfo={false}
        aria-label={`${job.job_type} 进度 ${job.progress}%`}
      />
      <p>{job.message}</p>
    </div>
  );
});

export function JobPanel() {
  const jobs = useJobsStore((state) => state.jobs);
  const refresh = useJobsStore((state) => state.refresh);
  const hasActiveJobs = jobs.some((job) => job.status === 'queued' || job.status === 'running');

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, refresh]);

  return (
    <section className="panel-section">
      <div className="section-title">
        <Activity size={16} />
        <span>任务</span>
      </div>
      <div className="job-list">
        {jobs.length === 0 && <p className="panel-empty">暂无导入任务</p>}
        {jobs.map((job) => (
          <JobItem key={job.id} job={job} />
        ))}
      </div>
    </section>
  );
}
