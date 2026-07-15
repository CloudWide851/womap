import { Button } from 'antd';
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  FolderCog,
  FolderInput,
  RefreshCw,
  Save,
} from 'lucide-react';

import { useAuthStore } from '../../stores/useAuthStore';
import { useWorkspaceContextStore } from '../../stores/useWorkspaceContextStore';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';

interface GettingStartedPanelProps {
  onOpenSettings: () => void;
}

export function GettingStartedPanel({ onOpenSettings }: GettingStartedPanelProps) {
  const serviceStatus = useAuthStore((state) => state.serviceStatus);
  const refreshPolicy = useAuthStore((state) => state.refreshPolicy);
  const layers = useWorkspaceStore((state) => state.layers);
  const currentWorkspace = useWorkspaceContextStore((state) => state.current);
  const dirty = useWorkspaceContextStore((state) => state.dirty);
  const saving = useWorkspaceContextStore((state) => state.saving);
  const saveCurrent = useWorkspaceContextStore((state) => state.saveCurrent);

  if (layers.some((layer) => layer.source === 'backend')) return null;

  return (
    <section className="getting-started-panel" aria-labelledby="getting-started-title">
      <div className="getting-started-heading">
        <span>首次使用</span>
        <h2 id="getting-started-title">四步加入自己的地图数据</h2>
      </div>
      <ol className="getting-started-steps">
        <li className={serviceStatus === 'ready' ? 'is-complete' : ''}>
          {serviceStatus === 'ready' ? (
            <CheckCircle2 size={14} aria-hidden="true" />
          ) : serviceStatus === 'unavailable' ? (
            <AlertCircle size={14} aria-hidden="true" />
          ) : (
            <Circle size={14} aria-hidden="true" />
          )}
          <span>
            <strong>连接 WOMAP 服务</strong>
            <small>
              {serviceStatus === 'ready'
                ? '服务已就绪'
                : serviceStatus === 'checking'
                  ? '正在检查连接'
                  : '服务不可用'}
            </small>
          </span>
          <Button
            size="small"
            icon={<RefreshCw size={14} />}
            disabled={serviceStatus === 'ready'}
            loading={serviceStatus === 'checking'}
            onClick={() => void refreshPolicy()}
          >
            {serviceStatus === 'ready' ? '已连接' : '重试'}
          </Button>
        </li>
        <li>
          <Circle size={14} aria-hidden="true" />
          <span><strong>配置数据源</strong><small>本地目录或 SMB</small></span>
          <Button size="small" icon={<FolderCog size={14} />} onClick={onOpenSettings}>配置</Button>
        </li>
        <li>
          <Circle size={14} aria-hidden="true" />
          <span><strong>同步并导入</strong><small>识别矢量与栅格</small></span>
          <Button
            size="small"
            type="primary"
            icon={<FolderInput size={14} />}
            onClick={() => window.dispatchEvent(new Event('womap:open-import-center'))}
          >
            导入
          </Button>
        </li>
        <li className={currentWorkspace && !dirty ? 'is-complete' : ''}>
          {currentWorkspace && !dirty ? (
            <CheckCircle2 size={14} aria-hidden="true" />
          ) : (
            <Circle size={14} aria-hidden="true" />
          )}
          <span><strong>保存工作空间</strong><small>保留图层与视图</small></span>
          <Button
            size="small"
            icon={<Save size={14} />}
            disabled={!currentWorkspace || !dirty}
            loading={saving}
            onClick={() => void saveCurrent().catch(() => undefined)}
          >
            保存
          </Button>
        </li>
      </ol>
      <p>“示例”图层只用于熟悉界面，不会作为后端成果导出。</p>
    </section>
  );
}
