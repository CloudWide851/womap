import { Suspense, lazy, useState } from 'react';

import { WorkbenchLayout } from '../layouts/WorkbenchLayout';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import type { AppPageMode } from '../types/workspace';

const SettingsPage = lazy(() =>
  import('../pages/SettingsPage').then((module) => ({ default: module.SettingsPage })),
);

const AttributeInspector = lazy(() =>
  import('../features/properties/AttributeInspector').then((module) => ({
    default: module.AttributeInspector,
  })),
);

export function App() {
  const [page, setPage] = useState<AppPageMode>('workspace');
  const inspectorTarget = useWorkspaceStore((state) => state.inspectorTarget);

  return (
    <div className="app-shell">
      <Suspense fallback={<div className="app-loading" role="status" aria-label="加载中" />}>
        {page === 'settings' ? (
          <SettingsPage onBack={() => setPage('workspace')} />
        ) : (
          <WorkbenchLayout onOpenSettings={() => setPage('settings')} />
        )}
      </Suspense>
      <Suspense fallback={null}>{inspectorTarget && <AttributeInspector />}</Suspense>
    </div>
  );
}
