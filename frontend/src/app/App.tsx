import { Suspense, lazy, useEffect, useState } from 'react';

import { WorkbenchLayout } from '../layouts/WorkbenchLayout';
import { AUTH_UNAUTHORIZED_EVENT } from '../services/api';
import { useAuthStore } from '../stores/useAuthStore';
import { useWorkspaceStore } from '../stores/useWorkspaceStore';
import type { AppPageMode } from '../types/workspace';

const loadLoginPage = () => import('../pages/LoginPage');
const loadSettingsPage = () => import('../pages/SettingsPage');
const loadAttributeInspector = () => import('../features/properties/AttributeInspector');

const LoginPage = lazy(() =>
  loadLoginPage().then((module) => ({ default: module.LoginPage })),
);

const SettingsPage = lazy(() =>
  loadSettingsPage().then((module) => ({ default: module.SettingsPage })),
);

const AttributeInspector = lazy(() =>
  loadAttributeInspector().then((module) => ({
    default: module.AttributeInspector,
  })),
);

export function App() {
  const [page, setPage] = useState<AppPageMode>('workspace');
  const [settingsSection, setSettingsSection] = useState<'import-sources' | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const authenticated = useAuthStore((state) => state.authenticated);
  const initialized = useAuthStore((state) => state.initialized);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const policyRefreshSeconds = useAuthStore((state) => state.policy.policyRefreshSeconds);
  const initialize = useAuthStore((state) => state.initialize);
  const refreshPolicy = useAuthStore((state) => state.refreshPolicy);
  const handleUnauthorized = useAuthStore((state) => state.handleUnauthorized);
  const tick = useAuthStore((state) => state.tick);
  const inspectorTarget = useWorkspaceStore((state) => state.inspectorTarget);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  useEffect(() => {
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [handleUnauthorized]);

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    const refreshTimer = window.setInterval(() => {
      tick();
      void refreshPolicy();
    }, policyRefreshSeconds * 1000);
    const expiryTimer =
      expiresAt === null
        ? null
        : window.setTimeout(() => tick(), Math.max(0, expiresAt - Date.now()));

    return () => {
      window.clearInterval(refreshTimer);
      if (expiryTimer !== null) {
        window.clearTimeout(expiryTimer);
      }
    };
  }, [authenticated, expiresAt, policyRefreshSeconds, refreshPolicy, tick]);

  useEffect(() => {
    if (!authenticated) {
      setWorkspaceReady(false);
      setPage('workspace');
      return;
    }

    const mountTimer = window.setTimeout(() => setWorkspaceReady(true), 0);
    const idleTimer = window.setTimeout(() => {
      void loadSettingsPage();
      void loadAttributeInspector();
    }, 300);

    return () => {
      window.clearTimeout(mountTimer);
      window.clearTimeout(idleTimer);
    };
  }, [authenticated]);

  return (
    <div className="app-shell">
      <Suspense fallback={<div className="app-loading" role="status" aria-label="加载中" />}>
        {!initialized ? (
          <div className="app-loading" role="status" aria-label="正在连接本地服务" />
        ) : !authenticated ? (
          <LoginPage />
        ) : !workspaceReady ? (
          <div className="app-loading" role="status" aria-label="加载中" />
        ) : page === 'settings' ? (
          <SettingsPage
            focusSection={settingsSection}
            onBack={() => {
              setPage('workspace');
              setSettingsSection(null);
            }}
          />
        ) : (
          <WorkbenchLayout
            onOpenSettings={(section) => {
              setSettingsSection(section ?? null);
              setPage('settings');
            }}
          />
        )}
      </Suspense>
      <Suspense fallback={null}>{inspectorTarget && <AttributeInspector />}</Suspense>
    </div>
  );
}
