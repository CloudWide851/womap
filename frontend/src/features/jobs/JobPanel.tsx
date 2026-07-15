import { Button, Progress, Tooltip } from 'antd';
import { Activity, CheckCircle2, Clock3, Download, LoaderCircle, PauseCircle, XCircle } from 'lucide-react';
import { memo, useEffect } from 'react';

import { useJobsStore } from '../../stores/useJobsStore';
import { useSpatialAnalysisStore } from '../../stores/useSpatialAnalysisStore';
import { downloadRasterExport } from '../../services/api';
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

function jobLabel(jobType: string) {
  if (jobType === 'import-sync') return '目录同步';
  if (jobType === 'import-data') return '数据导入';
  if (jobType === 'workspace-export') return '工作空间导出';
  if (jobType === 'workspace-import') return '工作空间导入';
  if (jobType === 'spatial-analysis') return '空间分析';
  if (jobType === 'spatial-analysis-export') return '分析结果导出';
  if (jobType === 'raster-derive') return '派生栅格';
  if (jobType === 'raster-export') return 'COG 导出';
  return '后台任务';
}

interface JobItemProps {
  job: ImportJob;
}

const JobItem = memo(function JobItem({ job }: JobItemProps) {
  const StatusIcon = statusIcons[job.status];
  const openAnalysis = useSpatialAnalysisStore((state) => state.openHistory);
  const downloadRaster = async () => {
    const result = await downloadRasterExport(job.id);
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = result.filename;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div
      className={`job-item is-${job.status}`}
      role={job.job_type === 'spatial-analysis' ? 'button' : undefined}
      tabIndex={job.job_type === 'spatial-analysis' ? 0 : undefined}
      onClick={() => {
        if (job.job_type === 'spatial-analysis') void openAnalysis(job.id);
      }}
      onKeyDown={(event) => {
        if (job.job_type === 'spatial-analysis' && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          void openAnalysis(job.id);
        }
      }}
    >
      <div>
        <strong>{jobLabel(job.job_type)}</strong>
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
      {job.job_type === 'raster-export' && job.status === 'done' && (
        <Button size="small" icon={<Download size={13} />} onClick={() => void downloadRaster()}>
          下载
        </Button>
      )}
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
        {jobs.length === 0 && <p className="panel-empty">暂无后台任务</p>}
        {jobs.map((job) => (
          <JobItem key={job.id} job={job} />
        ))}
      </div>
    </section>
  );
}
