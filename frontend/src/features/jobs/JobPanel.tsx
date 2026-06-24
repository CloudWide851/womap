import { Progress, Tag } from 'antd';
import { Activity } from 'lucide-react';

import { useJobsStore } from '../../stores/useJobsStore';

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
          <div className="job-item" key={job.id}>
            <div>
              <strong>{job.jobType}</strong>
              <Tag>{job.status}</Tag>
            </div>
            <Progress percent={job.progress} size="small" showInfo={false} />
            <p>{job.message}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
