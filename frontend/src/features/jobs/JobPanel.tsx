import { Progress, Tooltip } from 'antd';
import { Activity, CheckCircle2, Clock3, LoaderCircle, XCircle } from 'lucide-react';
import { memo } from 'react';

import { useJobsStore } from '../../stores/useJobsStore';
import type { JobState } from '../../types/workspace';

const statusLabels: Record<JobState['status'], string> = {
  queued: '等待中',
  running: '执行中',
  done: '已完成',
  failed: '失败',
  unknown: '未知',
};

const statusIcons = {
  queued: Clock3,
  running: LoaderCircle,
  done: CheckCircle2,
  failed: XCircle,
  unknown: Activity,
};

interface JobItemProps {
  job: JobState;
}

const JobItem = memo(function JobItem({ job }: JobItemProps) {
  const StatusIcon = statusIcons[job.status];
  return (
    <div className={`job-item is-${job.status}`}>
      <div>
        <strong>{job.jobType}</strong>
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
        aria-label={`${job.jobType} 进度 ${job.progress}%`}
      />
      <p>{job.message}</p>
    </div>
  );
});

export function JobPanel() {
  const jobs = useJobsStore((state) => state.jobs);

  return (
    <section className="panel-section">
      <div className="section-title">
        <Activity size={16} />
        <span>任务</span>
      </div>
      <div className="job-list">
        {jobs.map((job) => (
          <JobItem key={job.id} job={job} />
        ))}
      </div>
    </section>
  );
}
